# -*- coding: utf-8 -*-
"""
Tests for Fix 1 (Rank 1): RTPS Statutory Deemed-Approval Restoration
Right to Public Services Act requires applications pending > 15 days
to be automatically deemed approved.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


class TestDeemedApproval(unittest.TestCase):

    def test_module_loads_config_without_file_not_found(self):
        """
        Prior to Fix 1, importing or running deemed_approval.py crashes with:
        FileNotFoundError: [Errno 2] No such file or directory: '.../config/settings.ini'
        Fix 1 must load from app.ini (or environment) without crashing.
        """
        try:
            import app.scripts.deemed_approval as da
            self.assertTrue(hasattr(da, "main") or hasattr(da, "process_deemed_approvals"))
            self.assertEqual(da.SLA_DAYS, 15)
        except FileNotFoundError as e:
            self.fail(f"deemed_approval failed to find config file: {e}")

    @patch("requests.post")
    @patch("psycopg2.connect")
    def test_deemed_approval_transitions_overdue_applications(self, mock_connect, mock_post):
        """
        Verify that applications pending past the 15-day SLA are updated
        to DEEMED_APPROVED and notified via SMS gateway.
        """
        import app.scripts.deemed_approval as da

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate 2 overdue applications returned by the query
        mock_cur.fetchall.return_value = [
            ("SSP26001001", "9876543210"),
            ("SSP26001002", "9876543211"),
        ]

        # Execute
        approved_count = da.main() if hasattr(da, "main") else da.process_deemed_approvals()

        # Check DB update was executed with DEEMED_APPROVED and RTPS-AUTO
        self.assertTrue(mock_cur.execute.called)
        query = mock_cur.execute.call_args[0][0]
        self.assertIn("DEEMED_APPROVED", query)
        self.assertIn("RTPS-AUTO", query)
        self.assertIn("status = 'PENDING'", query)

        # Check commit was called
        mock_conn.commit.assert_called_once()

        # Check SMS notifications were triggered
        self.assertEqual(mock_post.call_count, 2)
        call_urls = [call[0][0] for call in mock_post.call_args_list]
        for url in call_urls:
            self.assertIn("/api/send", url)


if __name__ == "__main__":
    unittest.main()
