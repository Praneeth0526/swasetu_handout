# -*- coding: utf-8 -*-
"""
Tests for Administrator MCP Server (/mcp/admin).
Verifies strict bearer authentication, audit logging, unmasked data access for officials,
human-in-the-loop review decisions, and RTPS deemed-approval sweeps.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from app.app import app, ASSESSOR_PASSWORD


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestAdminMCPEndpoint:
    """Test HTTP transport, tool discovery, execution, and auth on /mcp/admin."""

    def test_get_admin_unauthorized(self, client):
        """GET /mcp/admin without credentials must return 401 Unauthorized."""
        res = client.get("/mcp/admin")
        assert res.status_code == 401
        assert "WWW-Authenticate" in res.headers

    def test_get_admin_authorized_assessor(self, client):
        """GET /mcp/admin with assessor bearer token returns 200 with tools."""
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.get("/mcp/admin", headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "sewasetu-admin-mcp"
        assert data["authenticated_user"] == "assessor_admin"
        assert len(data["tools"]) >= 5
        assert "review_application" in data["tools"]
        assert "run_rtps_deemed_approval_batch" in data["tools"]

    def test_get_admin_health(self, client):
        """GET /mcp/admin/health returns 200 without authentication."""
        res = client.get("/mcp/admin/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "sewasetu-admin-mcp"

    def test_mcp_initialize(self, client):
        """Initialize method should work for protocol discovery."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}
        }
        res = client.post("/mcp/admin", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        assert data["result"]["serverInfo"]["name"] == "sewasetu-admin-mcp"

    def test_mcp_tools_list_authenticated(self, client):
        """Authenticated tools/list returns administrator tools."""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        tool_names = [t["name"] for t in data["result"]["tools"]]
        assert "list_pending_applications" in tool_names
        assert "get_application_details" in tool_names
        assert "review_application" in tool_names
        assert "run_rtps_deemed_approval_batch" in tool_names
        assert "get_district_dashboard_metrics" in tool_names

    @patch("app.mcp.admin_server.get_db")
    def test_tool_list_pending_applications(self, mock_get_db, client):
        """List pending applications with SLA overdue flags."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            (10, "SSP26000010", "Ram Lal", "9876543210", "Kalyanpur", "Ward 1", datetime(2026, 2, 1), 25)
        ]

        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "list_pending_applications",
                "arguments": {"block": "Kalyanpur", "overdue_only": True}
            }
        }
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["count"] == 1
        app_item = result_content["applications"][0]
        assert app_item["application_no"] == "SSP26000010"
        assert app_item["rtps_overdue"] is True
        assert app_item["days_pending"] == 25

    @patch("app.mcp.admin_server.get_db")
    def test_tool_get_application_details_unmasked(self, mock_get_db, client):
        """Retrieve full unmasked details for authorized department officer review."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (
            10, "SSP26000010", "Ram Lal", "9876543210", datetime(1950, 5, 10), "Male",
            "Married", "Ward 1", "Kalyanpur", "123456789012", "SBIN0001234", "doc.pdf",
            "PENDING", datetime(2026, 3, 1), None, None
        )

        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "get_application_details",
                "arguments": {"application_id": 10}
            }
        }
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["found"] is True
        # Full unmasked data for admin
        assert result_content["bank_account"] == "123456789012"
        assert result_content["mobile"] == "9876543210"

    @patch("app.mcp.admin_server.get_db")
    @patch("app.mcp.admin_server.send_sms")
    def test_tool_review_application_approve_with_justification(self, mock_sms, mock_get_db, client):
        """Review application requires justification and dispatches SMS."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (10, "SSP26000010", "9876543210", "PENDING")

        payload = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "review_application",
                "arguments": {
                    "application_id": 10,
                    "decision": "APPROVED",
                    "justification": "All statutory age and residency criteria verified by BDO inspection."
                }
            }
        }
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["success"] is True
        assert result_content["decision"] == "APPROVED"
        assert result_content["decided_by"] == "assessor_admin"
        mock_sms.assert_called_once()

    @patch("app.mcp.admin_server.process_deemed_approvals")
    def test_tool_run_rtps_deemed_approval_batch(self, mock_sweep, client):
        """Trigger RTPS statutory deemed approval sweep via MCP."""
        mock_sweep.return_value = (42, ["SSP26000001", "SSP26000002"])

        payload = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "run_rtps_deemed_approval_batch",
                "arguments": {"dry_run": False}
            }
        }
        headers = {"Authorization": f"Bearer {ASSESSOR_PASSWORD}"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["success"] is True
        assert result_content["deemed_approved_count"] == 42
        mock_sweep.assert_called_once()
