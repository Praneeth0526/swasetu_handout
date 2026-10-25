# -*- coding: utf-8 -*-
"""
Tests for Fix 2 (Rank 2): Indic Script (Assamese/Bengali/Hindi) Unicode & Name Integrity
Ensures that names in Indian languages are not truncated to 20 raw bytes
and do not turn into '?' in the acknowledgment PDF.
"""

import unittest
from unittest.mock import MagicMock, patch
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

    @patch("app.app.FPDF")
    def test_pdf_acknowledgment_renders_indic_text_without_question_marks(self, mock_fpdf_cls):
        """
        The old generate_acknowledgment catches FPDF exceptions on non-Latin characters
        and prints '?'.
        Verify that generate_acknowledgment handles Indic names without falling back to '?'.
        """
        mock_pdf = MagicMock()
        mock_fpdf_cls.return_value = mock_pdf

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

        # In unpatched app.py, cell() with Helvetica raises UnicodeEncodeError for Indic text,
        # which triggers `except Exception: pdf.cell(0, 8, "?", border=1, ln=1)`
        def cell_side_effect(*args, **kwargs):
            text = args[2] if len(args) > 2 else kwargs.get("txt", "")
            if text == indic_name:
                raise UnicodeEncodeError("latin-1", text, 0, 1, "ordinal not in range(256)")
            return MagicMock()

        mock_pdf.cell.side_effect = cell_side_effect
        mock_pdf.output.return_value = b"%PDF-1.4 Mock"

        # Running this with the unpatched code calls cell with '?' because of the catch block
        pdf_bytes = generate_acknowledgment(mock_cur, 1)

        # Inspect all calls to mock_pdf.cell
        printed_texts = []
        for call in mock_pdf.cell.call_args_list:
            args = call[0]
            if len(args) > 2:
                printed_texts.append(args[2])
            elif "txt" in call[1]:
                printed_texts.append(call[1]["txt"])

        # In unpatched code, '?' was printed because of the exception.
        # In patched code, '?' should never be printed for an Indic name!
        self.assertNotIn("?", printed_texts, "PDF fell back to '?' for Indic name!")


if __name__ == "__main__":
    unittest.main()
