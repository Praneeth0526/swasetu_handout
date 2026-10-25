# -*- coding: utf-8 -*-
"""
Tests for Fix 4 (Rank 4): Form Inclusivity & Dismantling the 'Bazaar Tout' Trap
Ensures:
1. Document upload accepts JPG, PNG, and PDF up to 5MB (not just PDF <= 100KB with ERR_VAL_47).
2. Widows are not blocked by mandatory deceased-husband employer fields.
3. Indian date format DD/MM/YYYY is prioritized over US format, and ISO YYYY-MM-DD is accepted.
"""

import werkzeug
if not hasattr(werkzeug, "__version__"):
    import importlib.metadata
    try:
        werkzeug.__version__ = importlib.metadata.version("werkzeug")
    except Exception:
        werkzeug.__version__ = "3.1.0"

import io
import unittest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from app.app import app


class TestFormInclusivity(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_upload_accepts_jpg_image_over_100kb(self):
        """
        Original code rejected non-PDFs and files > 100KB with ERR_VAL_47.
        The UI tells users: 'JPG or PDF, maximum size 5 MB'.
        Uploading a 250KB JPG must be accepted.
        """
        with self.client.session_transaction() as sess:
            sess["verified_mobile"] = "9876543210"

        # 250KB dummy JPG payload
        jpg_data = b"\xff\xd8\xff" + b"\x00" * (250 * 1024)
        data = {
            "document": (io.BytesIO(jpg_data), "age_proof.jpg")
        }

        resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
        # Should redirect to declaration (302), NOT re-render upload.html with ERR_VAL_47
        self.assertEqual(resp.status_code, 302, "JPG upload was not accepted!")
        self.assertEqual(resp.location, "/declaration")

    def test_upload_error_message_is_human_readable_not_err_val_47(self):
        """
        When an invalid file or oversized file is uploaded, the error must not
        be the cryptic code 'ERR_VAL_47'.
        """
        with self.client.session_transaction() as sess:
            sess["verified_mobile"] = "9876543210"

        # 6MB file (exceeds 5MB limit)
        oversized_data = b"\x00" * (6 * 1024 * 1024)
        data = {
            "document": (io.BytesIO(oversized_data), "huge_doc.pdf")
        }

        resp = self.client.post("/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("ERR_VAL_47", resp.get_data(as_text=True))

    @patch("app.app.send_sms")
    @patch("app.app.get_db")
    def test_widow_without_husband_employer_is_accepted(self, mock_get_db, mock_sms):
        """
        Original code strictly required husband_employer for widows:
        if marital == 'Widowed': if not husband_name or not husband_employer: ...
        A widow whose husband passed away decades ago must NOT be blocked.
        """
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [
            (0,),   # duplicate check
            (105,), # insert returning id
            (0,),   # portal user count check
            ("SSP26000105", "Radha Devi", "9876543210", date(1952, 8, 15),
             "Sonari", "Sonari", "1234567890", "SBIN0001234", datetime.now(), "PENDING")
        ]

        with self.client.session_transaction() as sess:
            sess["verified_mobile"] = "9876543210"
            sess["form_data"] = {
                "applicant_name": "Radha Devi",
                "village": "Sonari",
                "block": "Sonari",
                "gender": "Female",
                "marital_status": "Widowed",
                "husband_name": "Late Ramesh",
                "husband_employer": "", # Blank!
                "bank_account": "1234567890",
                "ifsc": "SBIN0001234",
                "dob": "15/08/1952"
            }
            sess["doc_path"] = "/tmp/test.pdf"

        resp = self.client.post("/declaration")
        # Should succeed and render confirmation (200), not redirect to step 1 (302)
        self.assertEqual(resp.status_code, 200, "Widow without husband_employer was rejected!")
        self.assertIn("Application Submitted", resp.get_data(as_text=True))

    @patch("app.app.send_sms")
    @patch("app.app.get_db")
    def test_date_parsing_prioritizes_indian_dd_mm_yyyy_format(self, mock_get_db, mock_sms):
        """
        Original code tried ('%m/%d/%Y', '%d/%m/%Y').
        Input '05/06/1950' was interpreted as May 6, 1950 instead of June 5, 1950!
        Input '1950-06-05' failed completely.
        Fix 4 must prioritize DD/MM/YYYY and support ISO format.
        """
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.side_effect = [
            (0,),   # duplicate check
            (106,), # insert returning id
            (0,),   # portal user count check
            ("SSP26000106", "Gopal Das", "9876543210", date(1950, 6, 5),
             "Sonari", "Sonari", "1234567890", "SBIN0001234", datetime.now(), "PENDING")
        ]

        with self.client.session_transaction() as sess:
            sess["verified_mobile"] = "9876543210"
            sess["form_data"] = {
                "applicant_name": "Gopal Das",
                "village": "Sonari",
                "block": "Sonari",
                "gender": "Male",
                "marital_status": "Married",
                "bank_account": "1234567890",
                "ifsc": "SBIN0001234",
                "dob": "05/06/1950" # 5th June 1950
            }
            sess["doc_path"] = "/tmp/test.pdf"

        resp = self.client.post("/declaration")
        self.assertEqual(resp.status_code, 200)

        # Verify parsed DOB stored in the database insert query
        insert_args = mock_cur.execute.call_args_list[1][0][1]
        stored_dob = insert_args[3]
        self.assertEqual(stored_dob, date(1950, 6, 5),
                         f"Date parsed incorrectly: expected June 5, 1950, got {stored_dob}")


if __name__ == "__main__":
    unittest.main()
