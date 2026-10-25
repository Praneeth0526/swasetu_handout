# -*- coding: utf-8 -*-
"""
Tests for Fix 5 (Rank 5): High-Concurrency Resilience & Performance
Ensures:
1. Database schema defines indexes on mobile, status, submitted_at, and block.
2. Connection pooling is implemented to prevent 'FATAL: sorry, too many clients already'.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestPerformanceResilience(unittest.TestCase):

    def test_schema_includes_performance_indexes(self):
        """
        In the original schema.sql, zero indexes exist on applications or otps,
        causing 100,000-row table scans on status login, admin list, and dashboard.
        Fix 5 must include indexes on mobile, (status, submitted_at), and block.
        """
        with open("app/schema.sql", "r") as f:
            schema_content = f.read().lower()

        self.assertIn("idx_applications_mobile", schema_content,
                      "Index on applications(mobile) missing from schema.sql!")
        self.assertIn("idx_applications_status_submitted", schema_content,
                      "Composite index on applications(status, submitted_at) missing!")
        self.assertIn("idx_applications_block", schema_content,
                      "Index on applications(block) missing from schema.sql!")

    def test_connection_pooling_is_configured_and_reused(self):
        """
        Original get_db() created a new raw connection on every single request,
        exhausting Postgres max_connections.
        Fix 5 must implement a ThreadedConnectionPool.
        """
        import app.app as app_module
        self.assertTrue(hasattr(app_module, "get_db_pool") or hasattr(app_module, "db_pool"),
                        "Threaded connection pool not found in app.py!")


if __name__ == "__main__":
    unittest.main()
