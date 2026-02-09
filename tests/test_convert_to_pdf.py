"""Tests for app/tasks/convert_to_pdf.py module."""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestConvertToPdfMimeTypes:
    """Tests for file type detection in convert_to_pdf."""

    def test_office_extensions_set(self):
        """Test that the task module is importable."""
        from app.tasks.convert_to_pdf import convert_to_pdf
        assert callable(convert_to_pdf)

    @patch("app.tasks.convert_to_pdf.requests")
    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_convert_with_no_gotenberg_url(self, mock_log, mock_process, mock_requests):
        """Test convert_to_pdf when gotenberg_url is not configured."""
        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = None

            mock_self = MagicMock()
            mock_self.request.id = "test-task-id"

            from app.tasks.convert_to_pdf import convert_to_pdf
            result = convert_to_pdf.__wrapped__(mock_self, "/tmp/test.docx")
            assert result is None

    @patch("app.tasks.convert_to_pdf.requests")
    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_convert_exception_handling(self, mock_log, mock_process, mock_requests, tmp_path):
        """Test convert_to_pdf exception handling."""
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"test content")

        mock_requests.post.side_effect = Exception("Connection error")

        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = "http://localhost:3000"
            mock_settings.http_request_timeout = 30

            mock_self = MagicMock()
            mock_self.request.id = "test-task-id"

            from app.tasks.convert_to_pdf import convert_to_pdf
            result = convert_to_pdf.__wrapped__(mock_self, str(test_file))
            assert result is None
