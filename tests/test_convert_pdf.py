"""Comprehensive unit tests for app/tasks/convert_to_pdf.py module."""

from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from app.tasks.convert_to_pdf import (
    _build_filename,
    _detect_extension,
    _detect_mime_type,
    _detect_mime_type_from_magic,
    convert_to_pdf,
)


@pytest.mark.unit
class TestDetectMimeTypeFromMagic:
    """Tests for _detect_mime_type_from_magic function."""

    @patch("app.tasks.convert_to_pdf.puremagic.from_file")
    def test_detects_mime_from_puremagic(self, mock_puremagic):
        """Test MIME type detection using puremagic."""
        mock_match = MagicMock()
        mock_match.mime_type = "application/pdf"
        mock_puremagic.return_value = [mock_match]

        result = _detect_mime_type_from_magic("/test/file.pdf")
        assert result == "application/pdf"

    @patch("app.tasks.convert_to_pdf.filetype.guess")
    @patch("app.tasks.convert_to_pdf.puremagic.from_file")
    def test_falls_back_to_filetype(self, mock_puremagic, mock_filetype):
        """Test fallback to filetype when puremagic fails."""
        from app.tasks.convert_to_pdf import puremagic

        mock_puremagic.side_effect = puremagic.PureError("Cannot detect")
        mock_guess = MagicMock()
        mock_guess.mime = "image/jpeg"
        mock_filetype.return_value = mock_guess

        result = _detect_mime_type_from_magic("/test/image.jpg")
        assert result == "image/jpeg"

    @patch("app.tasks.convert_to_pdf.filetype.guess")
    @patch("app.tasks.convert_to_pdf.puremagic.from_file")
    def test_returns_none_when_detection_fails(self, mock_puremagic, mock_filetype):
        """Test returns None when all detection methods fail."""
        from app.tasks.convert_to_pdf import puremagic

        mock_puremagic.side_effect = puremagic.PureError("Cannot detect")
        mock_filetype.return_value = None

        result = _detect_mime_type_from_magic("/test/unknown")
        assert result is None


@pytest.mark.unit
class TestDetectMimeType:
    """Tests for _detect_mime_type function."""

    @patch("app.tasks.convert_to_pdf.mimetypes.guess_type")
    def test_detects_from_file_path(self, mock_guess_type):
        """Test MIME type detection from file path extension."""
        mock_guess_type.return_value = ("application/pdf", None)

        mime_type, encoding = _detect_mime_type("/test/file.pdf", None)
        assert mime_type == "application/pdf"
        assert encoding is None

    @patch("app.tasks.convert_to_pdf._detect_mime_type_from_magic")
    @patch("app.tasks.convert_to_pdf.mimetypes.guess_type")
    def test_uses_original_filename_when_provided(self, mock_guess_type, mock_magic):
        """Test uses original filename for detection when provided."""
        mock_guess_type.side_effect = [(None, None), ("application/vnd.ms-excel", None)]

        mime_type, encoding = _detect_mime_type("/tmp/uuid.bin", "report.xls")
        assert mime_type == "application/vnd.ms-excel"

    @patch("app.tasks.convert_to_pdf._detect_mime_type_from_magic")
    @patch("app.tasks.convert_to_pdf.mimetypes.guess_type")
    def test_falls_back_to_magic_detection(self, mock_guess_type, mock_magic):
        """Test fallback to magic byte detection."""
        mock_guess_type.return_value = (None, None)
        mock_magic.return_value = "image/png"

        mime_type, encoding = _detect_mime_type("/test/file", None)
        assert mime_type == "image/png"


@pytest.mark.unit
class TestDetectExtension:
    """Tests for _detect_extension function."""

    def test_detects_extension_from_file_path(self):
        """Test extension detection from file path."""
        result = _detect_extension("/test/file.PDF", None, None)
        assert result == ".pdf"

    def test_uses_original_filename_extension(self):
        """Test uses original filename when file path has no extension."""
        result = _detect_extension("/tmp/uuid", "document.docx", None)
        assert result == ".docx"

    @patch("app.tasks.convert_to_pdf.mimetypes.guess_extension")
    def test_guesses_from_mime_type(self, mock_guess_ext):
        """Test extension guessing from MIME type."""
        mock_guess_ext.return_value = ".jpg"

        result = _detect_extension("/test/file", None, "image/jpeg")
        assert result == ".jpg"

    @patch("app.tasks.convert_to_pdf.filetype.guess")
    @patch("app.tasks.convert_to_pdf.puremagic.from_file")
    @patch("app.tasks.convert_to_pdf.mimetypes.guess_extension")
    def test_uses_puremagic_fallback(self, mock_guess_ext, mock_puremagic, mock_filetype):
        """Test uses puremagic as fallback for extension detection."""
        mock_guess_ext.return_value = None
        mock_match = MagicMock()
        mock_match.extension = ".png"
        mock_puremagic.return_value = [mock_match]

        result = _detect_extension("/test/file", None, None)
        assert result == ".png"

    @patch("app.tasks.convert_to_pdf.filetype.guess")
    @patch("app.tasks.convert_to_pdf.puremagic.from_file")
    @patch("app.tasks.convert_to_pdf.mimetypes.guess_extension")
    def test_returns_empty_when_all_fail(self, mock_guess_ext, mock_puremagic, mock_filetype):
        """Test returns empty string when all detection fails."""
        from app.tasks.convert_to_pdf import puremagic

        mock_guess_ext.return_value = None
        mock_puremagic.side_effect = puremagic.PureError("Cannot detect")
        mock_filetype.return_value = None

        result = _detect_extension("/test/file", None, None)
        assert result == ""


@pytest.mark.unit
class TestBuildFilename:
    """Tests for _build_filename function."""

    def test_uses_original_filename_with_extension(self):
        """Test uses original filename when it has an extension."""
        result = _build_filename("/tmp/uuid", "document.pdf", ".pdf")
        assert result == "document.pdf"

    def test_appends_extension_to_basename(self):
        """Test appends extension when needed."""
        result = _build_filename("/tmp/file", None, ".pdf")
        assert result == "file.pdf"

    def test_does_not_duplicate_extension(self):
        """Test does not duplicate extension."""
        result = _build_filename("/tmp/file.pdf", None, ".pdf")
        assert result == "file.pdf"

    def test_returns_basename_when_no_extension(self):
        """Test returns basename when no extension provided."""
        result = _build_filename("/tmp/file", None, "")
        assert result == "file"


@pytest.mark.unit
class TestConvertToPdf:
    """Tests for convert_to_pdf Celery task."""

    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"file content")
    def test_converts_office_document_successfully(self, mock_file, mock_log_progress, mock_post, mock_process):
        """Test successful conversion of Office document."""
        # Mock successful Gotenberg response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 converted content"
        mock_post.return_value = mock_response

        # Mock file type detection
        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        None,
                    )
                    mock_detect_ext.return_value = ".docx"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/test.docx", "document.docx")

                    # Verify Gotenberg was called
                    mock_post.assert_called_once()
                    call_args = mock_post.call_args
                    assert "libreoffice/convert" in call_args[0][0]

                    # Verify PDF was written
                    write_calls = [call for call in mock_file().write.call_args_list]
                    assert len(write_calls) > 0

                    # Verify process_document was queued
                    mock_process.delay.assert_called_once()

                    # Verify result
                    assert result == "/tmp/test.pdf"

    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_returns_none_when_gotenberg_url_not_configured(self, mock_log_progress):
        """Test returns None when Gotenberg URL is not configured."""
        with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
            mock_settings.gotenberg_url = None

            convert_to_pdf.request.id = "test-task-id"
            result = convert_to_pdf.__wrapped__("/tmp/test.docx")

            assert result is None
            # Verify error was logged
            failure_calls = [call for call in mock_log_progress.call_args_list if "failure" in str(call)]
            assert len(failure_calls) > 0

    @patch("app.tasks.convert_to_pdf.log_task_progress")
    def test_returns_none_when_file_type_unknown(self, mock_log_progress):
        """Test returns None when file type cannot be determined."""
        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_detect_mime.return_value = (None, None)
                    mock_detect_ext.return_value = ""

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/unknown_file")

                    assert result is None

    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"image content")
    def test_converts_image_file(self, mock_file, mock_log_progress, mock_post, mock_process):
        """Test conversion of image file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 converted image"
        mock_post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = ("image/jpeg", None)
                    mock_detect_ext.return_value = ".jpg"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/photo.jpg")

                    # Verify LibreOffice endpoint was used for images
                    mock_post.assert_called_once()
                    call_args = mock_post.call_args
                    assert "libreoffice/convert" in call_args[0][0]
                    assert result == "/tmp/photo.pdf"

    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"<html><body>Test</body></html>")
    def test_converts_html_file(self, mock_file, mock_log_progress, mock_post, mock_process):
        """Test conversion of HTML file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 converted html"
        mock_post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = ("text/html", None)
                    mock_detect_ext.return_value = ".html"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/page.html")

                    # Verify Chromium endpoint was used
                    mock_post.assert_called_once()
                    call_args = mock_post.call_args
                    assert "chromium/convert/html" in call_args[0][0]
                    assert result == "/tmp/page.pdf"

    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"# Markdown\n\nTest content")
    def test_converts_markdown_file(self, mock_file, mock_log_progress, mock_post):
        """Test conversion of Markdown file."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4 converted markdown"
        mock_post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    with patch("app.tasks.convert_to_pdf.os.path.exists") as mock_exists:
                        with patch("app.tasks.convert_to_pdf.os.path.dirname") as mock_dirname:
                            with patch("app.tasks.convert_to_pdf.os.remove") as mock_remove:
                                mock_settings.gotenberg_url = "http://gotenberg:3000"
                                mock_settings.http_request_timeout = 60
                                mock_detect_mime.return_value = ("text/markdown", None)
                                mock_detect_ext.return_value = ".md"
                                mock_exists.return_value = True
                                mock_dirname.return_value = "/tmp"

                                convert_to_pdf.request.id = "test-task-id"
                                result = convert_to_pdf.__wrapped__("/tmp/readme.md")

                                # Verify Chromium markdown endpoint was used
                                mock_post.assert_called_once()
                                call_args = mock_post.call_args
                                assert "chromium/convert/markdown" in call_args[0][0]

    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"file content")
    def test_handles_gotenberg_error(self, mock_file, mock_log_progress, mock_post):
        """Test handling of Gotenberg API errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = ("application/pdf", None)
                    mock_detect_ext.return_value = ".pdf"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/test.pdf")

                    assert result is None
                    # Verify error was logged
                    failure_calls = [call for call in mock_log_progress.call_args_list if "failure" in str(call)]
                    assert len(failure_calls) >= 1

    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"file content")
    def test_handles_network_exception(self, mock_file, mock_log_progress, mock_post):
        """Test handling of network exceptions during conversion."""
        mock_post.side_effect = Exception("Connection timeout")

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = ("application/pdf", None)
                    mock_detect_ext.return_value = ".pdf"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/test.pdf")

                    assert result is None

    @patch("app.tasks.convert_to_pdf.process_document")
    @patch("app.tasks.convert_to_pdf.requests.post")
    @patch("app.tasks.convert_to_pdf.log_task_progress")
    @patch("builtins.open", new_callable=mock_open, read_data=b"file content")
    def test_preserves_original_filename(self, mock_file, mock_log_progress, mock_post, mock_process):
        """Test that original filename is preserved and passed to process_document."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4"
        mock_post.return_value = mock_response

        with patch("app.tasks.convert_to_pdf._detect_mime_type") as mock_detect_mime:
            with patch("app.tasks.convert_to_pdf._detect_extension") as mock_detect_ext:
                with patch("app.tasks.convert_to_pdf.settings") as mock_settings:
                    mock_settings.gotenberg_url = "http://gotenberg:3000"
                    mock_settings.http_request_timeout = 60
                    mock_detect_mime.return_value = ("application/vnd.ms-excel", None)
                    mock_detect_ext.return_value = ".xls"

                    convert_to_pdf.request.id = "test-task-id"
                    result = convert_to_pdf.__wrapped__("/tmp/uuid.xls", "report.xls")

                    # Verify process_document was called with modified original filename
                    mock_process.delay.assert_called_once()
                    call_args = mock_process.delay.call_args
                    assert call_args[1]["original_filename"] == "report.pdf"
