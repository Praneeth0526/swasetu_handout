# -*- coding: utf-8 -*-
"""
Tests for Fix 3 (Rank 3): Privacy Shield & Access Control
Prevents privilege escalation on admin approve/reject,
eliminates BOLA/IDOR on citizen application views and PDF downloads,
and neutralizes SQL injection on password reset.
"""

import werkzeug
if not hasattr(werkzeug, "__version__"):
    import importlib.metadata
    try:
        werkzeug.__version__ = importlib.metadata.version("werkzeug")
    except Exception:
        werkzeug.__version__ = "3.1.0"

import unittest
from unittest.mock import patch, MagicMock
from app.app import app


class TestSecurityAccessControl(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    @patch("app.app.get_db")
    def test_citizen_cannot_approve_application_privilege_escalation(self, mock_get_db):
        """
        VULNERABILITY SEC-01:
        A regular citizen logged into the status portal has session['logged_in'] = True.
        Prior to Fix 3, /admin/approve/<id> only checks session.get('logged_in'),
        allowing any citizen to approve or reject applications!
        Fix 3 must enforce that only session.get('admin') can approve.
        """
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = "9876543210"
            # Explicitly NOT an admin:
            sess["admin"] = False

        resp = self.client.post("/admin/approve/101")
        # Must be 403 Forbidden
        self.assertEqual(resp.status_code, 403, "Citizen was able to invoke /admin/approve!")

    @patch("app.app.get_db")
    def test_citizen_cannot_reject_application_privilege_escalation(self, mock_get_db):
        """
        VULNERABILITY SEC-01:
        Same for /admin/reject/<id>. Must return 403 Forbidden for non-admin users.
        """
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = "9876543210"
            sess["admin"] = False

        resp = self.client.post("/admin/reject/101")
        self.assertEqual(resp.status_code, 403, "Citizen was able to invoke /admin/reject!")

    @patch("app.app.get_db")
    def test_bola_idor_citizen_cannot_view_other_citizens_application(self, mock_get_db):
        """
        VULNERABILITY SEC-02:
        /application/<id> checks session['logged_in'], but never verifies that
        the application belongs to the logged-in citizen!
        Fix 3 must return 403 Forbidden or redirect if mobile does not match.
        """
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Application belongs to 9999999999 (Victim)
        mock_cur.fetchone.return_value = (
            "SSP26999999", "Victim Name", "9999999999", "1950-01-01",
            "Village A", "Block B", "1234567890", "SBIN0001", "PENDING",
            "2026-01-01", None
        )

        # Attacker is logged in as 9876543210 (Different Citizen)
        with self.client.session_transaction() as sess:
            sess["logged_in"] = True
            sess["portal_mobile"] = "9876543210"
            sess["admin"] = False

        resp = self.client.get("/application/101")
        # Should be forbidden to view other citizens' records
        self.assertIn(resp.status_code, (403, 404, 302),
                      "BOLA Vulnerability: Citizen viewed another citizen's PII!")

    def test_unauthenticated_user_cannot_download_ack_pdf(self):
        """
        VULNERABILITY SEC-03:
        /ack/<id>.pdf has zero authentication in the original code.
        Anyone on the internet can scrape all 100,000 acknowledgment PDFs.
        Fix 3 must require authentication.
        """
        resp = self.client.get("/ack/101.pdf")
        self.assertIn(resp.status_code, (401, 403, 302),
                      "Unauthenticated user was able to access /ack/101.pdf!")

    @patch("app.app.get_db")
    def test_sql_injection_on_password_reset_prevented(self, mock_get_db):
        """
        VULNERABILITY SEC-05:
        reset_password() uses string formatting:
        cur.execute("SELECT mobile FROM portal_users WHERE mobile = '%s'" % mobile)
        Fix 3 must use parameterized query: cur.execute(..., (mobile,))
        """
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        injection_payload = "' OR '1'='1"
        self.client.post("/status/reset", data={"mobile": injection_payload})

        # Check call arguments of execute: must NOT contain the literal unescaped payload in the query string
        for call_args in mock_cur.execute.call_args_list:
            query = call_args[0][0]
            self.assertNotIn("'%s'" % injection_payload, query,
                             "Raw SQL string formatting detected on password reset!")
            # Parameterized query tuple must be passed
            if len(call_args[0]) > 1:
                params = call_args[0][1]
                self.assertIn(injection_payload, params)


if __name__ == "__main__":
    unittest.main()
