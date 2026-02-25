"""Tests for the head-to-head text comparison logic in process_with_ocr.

Covers lines 154-232 of app/tasks/process_with_ocr.py:
- original_text provided with both texts non-empty (comparison preferred=original)
- original_text provided with both texts non-empty (comparison preferred=ocr)
- comparison raises an exception → keep OCR text
- original_text provided but OCR returns empty text → fallback to original
- original_text provided but is empty → skip comparison, use OCR output
"""

from unittest.mock import Mock, patch

import pytest

from app.utils.text_quality import TextComparisonResult


@pytest.mark.unit
class TestProcessWithOCRTextComparison:
    """Tests for the head-to-head quality comparison in process_with_ocr."""

    _MINIMAL_PDF = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
        b"2 0 obj\n<</Type /Pages /Kids [3 0 R] /Count 1>>\nendobj\n"
        b"3 0 obj\n<</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]>>\nendobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer\n<</Size 4 /Root 1 0 R>>\n"
        b"startxref\n190\n%%EOF\n"
    )

    def _setup_ocr_task(self, tmp_path, extracted_text, searchable_pdf_path=None):
        """Helper to set up common mocks for OCR task tests."""
        from app.utils.ocr_provider import OCRResult

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        pdf_file = tmp_dir / "test.pdf"
        pdf_file.write_bytes(self._MINIMAL_PDF)

        mock_result = OCRResult(
            provider="azure",
            text=extracted_text,
            searchable_pdf_path=searchable_pdf_path or str(pdf_file),
        )

        provider_mock = Mock()
        provider_mock.name = "azure"
        provider_mock.__class__.__name__ = "AzureOCRProvider"
        provider_mock.process.return_value = mock_result

        return pdf_file, provider_mock

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    @patch("app.tasks.process_with_ocr.compare_text_quality")
    def test_comparison_prefers_original_text(self, mock_compare, mock_rotate, mock_log, tmp_path):
        """When comparison prefers original, final_text should be original_text."""
        from app.tasks.process_with_ocr import process_with_ocr

        pdf_file, provider_mock = self._setup_ocr_task(tmp_path, "OCR extracted text")
        mock_rotate.delay = Mock()

        mock_compare.return_value = TextComparisonResult(
            preferred="original",
            original_score=90,
            ocr_score=70,
            explanation="Original text is cleaner",
        )

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("OCR extracted text", str(pdf_file), {}),
            ),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("test.pdf", file_id=1, original_text="Original embedded text")

        assert result["cleaned_text"] == "Original embedded text"
        mock_compare.assert_called_once_with("Original embedded text", "OCR extracted text")

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    @patch("app.tasks.process_with_ocr.compare_text_quality")
    def test_comparison_prefers_ocr_text(self, mock_compare, mock_rotate, mock_log, tmp_path):
        """When comparison prefers OCR, final_text should be the OCR text."""
        from app.tasks.process_with_ocr import process_with_ocr

        pdf_file, provider_mock = self._setup_ocr_task(tmp_path, "High quality OCR text")
        mock_rotate.delay = Mock()

        mock_compare.return_value = TextComparisonResult(
            preferred="ocr",
            original_score=50,
            ocr_score=95,
            explanation="OCR text is more complete",
        )

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("High quality OCR text", str(pdf_file), {}),
            ),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("test.pdf", file_id=1, original_text="Low quality original")

        assert result["cleaned_text"] == "High quality OCR text"
        mock_compare.assert_called_once()

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    @patch("app.tasks.process_with_ocr.compare_text_quality")
    def test_comparison_exception_keeps_ocr_text(self, mock_compare, mock_rotate, mock_log, tmp_path):
        """When comparison raises an exception, the OCR text should be kept."""
        from app.tasks.process_with_ocr import process_with_ocr

        pdf_file, provider_mock = self._setup_ocr_task(tmp_path, "OCR text after error")
        mock_rotate.delay = Mock()

        mock_compare.side_effect = RuntimeError("AI comparison failed")

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("OCR text after error", str(pdf_file), {}),
            ),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("test.pdf", file_id=1, original_text="Some original text")

        assert result["cleaned_text"] == "OCR text after error"

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    def test_ocr_empty_falls_back_to_original(self, mock_rotate, mock_log, tmp_path):
        """When OCR returns empty text but original is non-empty, fallback to original."""
        from app.tasks.process_with_ocr import process_with_ocr

        pdf_file, provider_mock = self._setup_ocr_task(tmp_path, "")
        mock_rotate.delay = Mock()

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("", str(pdf_file), {}),
            ),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("test.pdf", file_id=1, original_text="Fallback original text")

        assert result["cleaned_text"] == "Fallback original text"

    @patch("app.tasks.process_with_ocr.log_task_progress")
    @patch("app.tasks.process_with_ocr.rotate_pdf_pages")
    def test_original_text_empty_skips_comparison(self, mock_rotate, mock_log, tmp_path):
        """When original_text is empty string, skip comparison and use OCR output."""
        from app.tasks.process_with_ocr import process_with_ocr

        pdf_file, provider_mock = self._setup_ocr_task(tmp_path, "Good OCR text")
        mock_rotate.delay = Mock()

        with (
            patch("app.tasks.process_with_ocr.settings") as mock_settings,
            patch("app.tasks.process_with_ocr.get_ocr_providers") as mock_providers,
            patch(
                "app.tasks.process_with_ocr.merge_ocr_results",
                return_value=("Good OCR text", str(pdf_file), {}),
            ),
            patch("app.tasks.process_with_ocr.compare_text_quality") as mock_compare,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_providers.return_value = [provider_mock]

            result = process_with_ocr.run("test.pdf", file_id=1, original_text="")

        assert result["cleaned_text"] == "Good OCR text"
        mock_compare.assert_not_called()

        # Verify "skipped" was logged for compare_ocr_quality
        skip_calls = [
            c
            for c in mock_log.call_args_list
            if len(c[0]) >= 3 and c[0][1] == "compare_ocr_quality" and c[0][2] == "skipped"
        ]
        assert len(skip_calls) == 1
