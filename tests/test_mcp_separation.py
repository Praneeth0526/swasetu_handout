# -*- coding: utf-8 -*-
"""
Security Separation & Boundary Isolation Tests for Sewa Setu MCP Servers.
Verifies that:
1. Unauthenticated callers CANNOT access Administrator MCP tools.
2. Invalid or citizen tokens CANNOT invoke administrative methods.
3. Citizen MCP endpoint CANNOT invoke admin tools (tools not found).
4. Citizen tool data minimization is strictly preserved (no unmasked PII).
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date

from app.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestMCPSeparationAndNegativeSecurity:
    """Rigorous negative tests verifying isolation between Citizen and Admin MCP surfaces."""

    def test_admin_tools_list_rejected_without_auth(self, client):
        """Unauthenticated tools/list on /mcp/admin must be strictly rejected with HTTP 403."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        res = client.post("/mcp/admin", json=payload)
        assert res.status_code == 403
        data = res.get_json()
        assert "error" in data
        assert data["error"]["code"] == -32000
        assert "Unauthorized" in data["error"]["message"]

    def test_admin_tools_list_rejected_with_invalid_token(self, client):
        """Invalid bearer token on /mcp/admin must be rejected with HTTP 403."""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        headers = {"Authorization": "Bearer invalid_citizen_token_12345"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == -32000

    def test_admin_tool_execution_rejected_without_auth(self, client):
        """Calling review_application without auth on /mcp/admin must be rejected with HTTP 403."""
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "review_application",
                "arguments": {
                    "application_id": 999,
                    "decision": "APPROVED",
                    "justification": "Exploit attempt"
                }
            }
        }
        res = client.post("/mcp/admin", json=payload)
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == -32000

    def test_admin_tool_execution_rejected_with_wrong_header(self, client):
        """Calling run_rtps_deemed_approval_batch with invalid token must fail."""
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "run_rtps_deemed_approval_batch",
                "arguments": {"dry_run": False}
            }
        }
        headers = {"Authorization": "Bearer citizen_user_attempting_privilege_escalation"}
        res = client.post("/mcp/admin", json=payload, headers=headers)
        assert res.status_code == 403
        data = res.get_json()
        assert data["error"]["code"] == -32000

    def test_citizen_endpoint_rejects_admin_tools(self, client):
        """Citizen MCP endpoint must return -32601 Method/Tool not found for admin tools."""
        admin_tools_to_test = [
            "review_application",
            "run_rtps_deemed_approval_batch",
            "list_pending_applications",
            "get_district_dashboard_metrics"
        ]
        for tool_name in admin_tools_to_test:
            payload = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": {}
                }
            }
            res = client.post("/mcp/citizen", json=payload)
            assert res.status_code == 200
            data = res.get_json()
            assert "error" in data
            assert data["error"]["code"] == -32601
            assert "not found on Citizen MCP server" in data["error"]["message"]

    def test_get_admin_metadata_rejects_invalid_bearer(self, client):
        """GET /mcp/admin with invalid credentials returns 401."""
        headers = {"Authorization": "Bearer bogus_token"}
        res = client.get("/mcp/admin", headers=headers)
        assert res.status_code == 401
        data = res.get_json()
        assert data["error"]["code"] == -32000

    @patch("app.mcp.citizen_server.get_db")
    def test_citizen_status_never_reveals_raw_bank_or_mobile(self, mock_get_db, client):
        """PII Data Minimization: Citizen endpoint never leaks raw 12-digit bank account or full mobile."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = (
            77, "SSP26000077", "Shanti Devi", "9812345678", date(1952, 1, 1),
            "Sonapur", "Sonapur Sadar", "62991029384756", "SBIN0000001", "APPROVED",
            datetime.now(), datetime.now(), "officer_1"
        )

        payload = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {
                "name": "check_application_status",
                "arguments": {"mobile": "9812345678"}
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        raw_text = res.get_data(as_text=True)
        # Raw phone number must not appear in full
        assert "9812345678" not in raw_text
        assert "XXXXXX5678" in raw_text
        # Raw bank account number must not appear in full
        assert "62991029384756" not in raw_text
        assert "XXXXXXXXXX4756" in raw_text
