# -*- coding: utf-8 -*-
"""
Tests for Citizen MCP Server (/mcp/citizen).
Verifies standard streamable HTTP transport, protocol methods, data minimization,
mandatory confirmation envelope for submissions, and error recovery.
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


class TestCitizenMCPEndpoint:
    """Test HTTP transport, tool discovery, and execution on /mcp/citizen."""

    def test_get_citizen_info(self, client):
        """GET /mcp/citizen should return endpoint metadata and available tools."""
        res = client.get("/mcp/citizen")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "sewasetu-citizen-mcp"
        assert "check_application_status" in data["tools"]
        assert "submit_pension_application" in data["tools"]
        assert len(data["tools"]) >= 5

    def test_get_citizen_health(self, client):
        """GET /mcp/citizen/health should return 200 OK."""
        res = client.get("/mcp/citizen/health")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "healthy"

    def test_mcp_initialize(self, client):
        """Standard MCP initialize handshake."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-agent", "version": "1.0"}
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        assert data["id"] == 1
        assert "serverInfo" in data["result"]
        assert data["result"]["serverInfo"]["name"] == "sewasetu-citizen-mcp"

    def test_mcp_tools_list(self, client):
        """Standard MCP tools/list returns citizen tools with schema definitions."""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "check_application_status" in tool_names
        assert "estimate_pension_eligibility" in tool_names
        assert "submit_pension_application" in tool_names
        assert "get_scheme_guidelines" in tool_names
        assert "track_or_file_grievance" in tool_names

    def test_tool_estimate_pension_eligibility_qualified(self, client):
        """Test eligibility calculation for 65-year old Purvanchal resident."""
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "estimate_pension_eligibility",
                "arguments": {
                    "dob": "15/08/1955",
                    "is_purvanchal_resident": True,
                    "annual_income_inr": 60000
                }
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["is_eligible"] is True
        assert result_content["age_calculated"] >= 60

    def test_tool_estimate_pension_eligibility_underage(self, client):
        """Test eligibility rejection for applicant under statutory age 60."""
        payload = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "estimate_pension_eligibility",
                "arguments": {
                    "dob": "01/01/1985",
                    "is_purvanchal_resident": True
                }
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["is_eligible"] is False
        assert any("statutory minimum age" in r.lower() for r in result_content["evaluations"])

    def test_tool_submit_pension_application_requires_confirmation_envelope(self, client):
        """Automated agents must NOT submit applications without explicit user confirmation."""
        payload = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "submit_pension_application",
                "arguments": {
                    "applicant_name": "Shri Ram Das",
                    "mobile": "9876543210",
                    "dob": "01/01/1950",
                    "gender": "Male",
                    "marital_status": "Married",
                    "block": "Kalyanpur",
                    "village": "Ward 3",
                    "bank_account": "123456789012",
                    "ifsc": "SBIN0001234",
                    "consent_confirmed": False
                }
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["action_required"] == "CONFIRMATION_REQUIRED"
        assert "explicit confirmation" in result_content["message"].lower()

    @patch("app.mcp.citizen_server.get_db")
    @patch("app.mcp.citizen_server.send_sms")
    def test_tool_submit_pension_application_with_consent(self, mock_sms, mock_get_db, client):
        """Successful application submission when consent_confirmed is True."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        # Check existing application -> None
        # RETURNING id -> 101
        # Check portal_users -> (0,)
        mock_cur.fetchone.side_effect = [None, (101,), (0,)]

        payload = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "submit_pension_application",
                "arguments": {
                    "applicant_name": "Shri Ram Das",
                    "mobile": "9876543210",
                    "dob": "01/01/1950",
                    "gender": "Male",
                    "marital_status": "Married",
                    "block": "Kalyanpur",
                    "village": "Ward 3",
                    "bank_account": "123456789012",
                    "ifsc": "SBIN0001234",
                    "consent_confirmed": True
                }
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["success"] is True
        assert result_content["status"] == "PENDING"
        assert "application_no" in result_content
        assert result_content["statutory_rtps_sla_days"] == 15

    @patch("app.mcp.citizen_server.get_db")
    def test_tool_check_application_status_masks_pii(self, mock_get_db, client):
        """Ensure check_application_status masks sensitive citizen bank account & mobile."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        # (id, application_no, applicant_name, mobile, dob, village, block, bank_account, ifsc, status, submitted_at, decided_at, decided_by)
        mock_cur.fetchone.return_value = (
            50, "SSP26000050", "Sunita Devi", "9876543210", date(1955, 3, 10),
            "Sonapur", "Kalyanpur", "123456789012", "SBIN0001234", "PENDING",
            datetime.now(), None, None
        )

        payload = {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "check_application_status",
                "arguments": {
                    "mobile": "9876543210"
                }
            }
        }
        res = client.post("/mcp/citizen", json=payload)
        assert res.status_code == 200
        data = res.get_json()
        result_content = json.loads(data["result"]["content"][0]["text"])
        assert result_content["status"] == "PENDING"
        assert result_content["found"] is True
        # Verify Mobile is masked: XXXXXX3210
        assert "XXXX" in result_content["masked_mobile"]
        assert "9876543210" not in json.dumps(result_content["masked_mobile"])
        # Verify Bank Account is masked
        assert "XXXX" in result_content["masked_bank_account"]
        assert "123456789012" not in json.dumps(result_content["masked_bank_account"])
