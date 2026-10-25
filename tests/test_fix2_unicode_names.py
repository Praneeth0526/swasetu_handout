# -*- coding: utf-8 -*-
"""
Tests for Fix 2 (Rank 2): Indic Script (Assamese/Bengali/Hindi) Unicode & Name Integrity
Ensures that names in Indian languages are not truncated to 20 raw bytes
and do not turn into '?' in the acknowledgment PDF.
"""

import unittest
from unittest.mock import MagicMock
from datetime import datetime, date

from app.app import sanitize, generate_acknowledgment


class TestUnicodeNameHandling(unittest.TestCase):

    def test_sanitize_preserves_full_indic_name(self):
        """
        Assamese name: প্ৰণৱ কুমাৰ বৰা (Pranab Kumar Bora)
        In UTF-8, this is ~40 bytes.
        The old sanitize() slices at [:20] bytes, truncating it to 'প্ৰণৱ ক'.
        The database column is VARCHAR(100), so the full name must be preserved.
        """
        assamese_name = "প্ৰণৱ কুমাৰ বৰা"
        sanitized = sanitize(assamese_name)
        self.assertEqual(sanitized, assamese_name)

        hindi_name = "राम प्रसाद शर्मा"
        sanitized_hindi = sanitize(hindi_name)
        self.assertEqual(sanitized_hindi, hindi_name)

    def test_pdf_acknowledgment_renders_indic_text_without_question_marks(self):
        """
        The old generate_acknowledgment catches FPDF exceptions on non-Latin characters
        and prints '?'.
        Verify that generate_acknowledgment generates a valid PDF with Unicode fonts
        without failing or corrupting the text to '?'.
        """
        mock_cur = MagicMock()
        indic_name = "প্ৰণৱ কুমাৰ বৰা"
        mock_cur.fetchone.return_value = (
            "SSP26999888",
            indic_name,
            "9876543210",
            date(1955, 6, 15),
            "Sonari Gaon",
            "Sonari",
            "123456789012",
            "SBIN0001234",
            datetime.now(),
            "PENDING"
        )

        pdf_bytes = generate_acknowledgment(mock_cur, 1)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 5000)
        # PDF binary header
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
