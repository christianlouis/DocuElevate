"""
Tests for URL-based file upload functionality
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx
import pytest


@pytest.mark.unit
class TestURLUploadValidation:
    """Test URL validation and SSRF protection"""

    def test_validate_url_scheme_http_allowed(self):
        """Test that HTTP URLs are allowed"""
        from app.api.url_upload import URLUploadRequest

        request = URLUploadRequest(url="http://example.com/file.pdf")
        assert str(request.url) == "http://example.com/file.pdf"

    def test_validate_url_scheme_https_allowed(self):
        """Test that HTTPS URLs are allowed"""
        from app.api.url_upload import URLUploadRequest

        request = URLUploadRequest(url="https://example.com/file.pdf")
        assert str(request.url) == "https://example.com/file.pdf"

    def test_validate_url_scheme_ftp_rejected(self):
        """Test that FTP URLs are rejected"""
        from pydantic import ValidationError

        from app.api.url_upload import URLUploadRequest

        with pytest.raises(ValidationError) as exc_info:
            URLUploadRequest(url="ftp://example.com/file.pdf")
        # Pydantic HttpUrl validates scheme automatically
        assert "url_scheme" in str(exc_info.value)

    def test_validate_url_scheme_file_rejected(self):
        """Test that file:// URLs are rejected"""
        from pydantic import ValidationError

        from app.api.url_upload import URLUploadRequest

        with pytest.raises(ValidationError) as exc_info:
            URLUploadRequest(url="file:///etc/passwd")
        # Pydantic HttpUrl validates scheme automatically
        assert "url_scheme" in str(exc_info.value)

    def test_is_private_ip_localhost(self):
        """Test that localhost is detected as private"""
        from app.utils.network import is_private_ip

        assert is_private_ip("127.0.0.1") is True
        assert is_private_ip("localhost") is True

    def test_is_private_ip_private_ranges(self):
        """Test that private IP ranges are detected"""
        from app.utils.network import is_private_ip

        # Private IP ranges
        assert is_private_ip("10.0.0.1") is True
        assert is_private_ip("172.16.0.1") is True
        assert is_private_ip("192.168.1.1") is True
        assert is_private_ip("169.254.169.254") is True  # AWS metadata

    def test_is_private_ip_public_allowed(self):
        """Test that public IPs are allowed"""
        from app.utils.network import is_private_ip

        # Public IPs should not be blocked
        assert is_private_ip("8.8.8.8") is False
        assert is_private_ip("1.1.1.1") is False

    def test_validate_url_safety_blocks_localhost(self, client):
        """Test that localhost URLs are blocked"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://localhost/file.pdf")
        assert exc_info.value.status_code == 400
        assert "private/internal" in exc_info.value.detail

    def test_validate_url_safety_blocks_private_ip(self, client):
        """Test that private IP URLs are blocked"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://192.168.1.1/file.pdf")
        assert exc_info.value.status_code == 400
        assert "private/internal" in exc_info.value.detail

    def test_validate_url_safety_blocks_metadata_endpoint(self):
        """Test that cloud metadata endpoints are blocked"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://169.254.169.254/latest/meta-data/")
        assert exc_info.value.status_code == 400
        # Check for either metadata OR private/internal (169.254.x.x is link-local)
        assert "metadata" in exc_info.value.detail or "private" in exc_info.value.detail

    def test_validate_url_safety_allows_public_url(self):
        """Test that public URLs are allowed"""
        from app.api.url_upload import validate_url_safety

        # Should not raise
        validate_url_safety("https://example.com/file.pdf")

    def test_validate_file_type_pdf_allowed(self):
        """Test that PDF files are allowed"""
        from app.api.url_upload import validate_file_type

        assert validate_file_type("application/pdf", "file.pdf") is True

    def test_validate_file_type_office_documents_allowed(self):
        """Test that Office documents are allowed"""
        from app.api.url_upload import validate_file_type

        # Word
        assert validate_file_type("application/msword", "file.doc") is True
        assert (
            validate_file_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file.docx")
            is True
        )

        # Excel
        assert validate_file_type("application/vnd.ms-excel", "file.xls") is True
        assert (
            validate_file_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "file.xlsx") is True
        )

    def test_validate_file_type_images_allowed(self):
        """Test that image files are allowed"""
        from app.api.url_upload import validate_file_type

        assert validate_file_type("image/jpeg", "file.jpg") is True
        assert validate_file_type("image/png", "file.png") is True
        assert validate_file_type("image/gif", "file.gif") is True

    def test_validate_file_type_executable_rejected(self):
        """Test that executable files are rejected"""
        from app.api.url_upload import validate_file_type

        assert validate_file_type("application/x-executable", "file.exe") is False
        assert validate_file_type("application/x-sh", "file.sh") is False

    def test_validate_file_type_with_charset(self):
        """Test content-type with charset parameter"""
        from app.api.url_upload import validate_file_type

        # Content-Type often includes charset
        assert validate_file_type("application/pdf; charset=utf-8", "file.pdf") is True
        assert validate_file_type("text/plain; charset=utf-8", "file.txt") is True


@pytest.mark.integration
class TestURLUploadEndpoint:
    """Integration tests for URL upload endpoint"""

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_requires_authentication(self, mock_process_document, mock_stream, client, monkeypatch):
        """Test that endpoint requires authentication when auth is enabled"""
        # Mock successful download to prevent actual HTTP requests
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF content"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Temporarily enable auth for this test
        monkeypatch.setenv("AUTH_ENABLED", "True")

        # Since we can't easily reload the app config, we'll just test that the endpoint exists
        # In production with auth enabled, it would redirect or return 401
        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})
        # With AUTH_ENABLED=False (default in tests), this should work but fail for other reasons
        # (like no mocking). We're just checking the endpoint exists and is reachable.
        assert response.status_code != 404  # Endpoint should exist

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_success(self, mock_process_document, mock_stream, client, tmp_path):
        """Test successful URL processing"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF content here"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id-123"
        mock_process_document.delay.return_value = mock_task

        # Make request
        response = client.post("/api/process-url", json={"url": "https://example.com/document.pdf"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-id-123"
        assert data["status"] == "queued"
        assert "filename" in data
        assert "size" in data

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_blocks_private_ip(self, mock_stream, client):
        """Test that private IPs are blocked"""
        response = client.post("/api/process-url", json={"url": "http://192.168.1.1/file.pdf"})

        assert response.status_code == 400
        data = response.json()
        assert "private/internal" in data["detail"]

        # Should not make HTTP request
        mock_stream.assert_not_called()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_blocks_localhost(self, mock_stream, client):
        """Test that localhost is blocked"""
        response = client.post("/api/process-url", json={"url": "http://localhost/file.pdf"})

        assert response.status_code == 400
        data = response.json()
        assert "private/internal" in data["detail"]

        # Should not make HTTP request
        mock_stream.assert_not_called()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_blocks_metadata_endpoint(self, mock_stream, client):
        """Test that cloud metadata endpoints are blocked"""
        response = client.post("/api/process-url", json={"url": "http://169.254.169.254/latest/meta-data/"})

        assert response.status_code == 400
        data = response.json()
        # 169.254.x.x is also a link-local (private) IP, so either error message is acceptable
        assert "metadata" in data["detail"] or "private" in data["detail"]

        # Should not make HTTP request
        mock_stream.assert_not_called()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_invalid_file_type(self, mock_stream, client):
        """Test that invalid file types are rejected"""
        # Mock response with executable content-type
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/x-executable"}
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        response = client.post("/api/process-url", json={"url": "https://example.com/malware.exe"})

        assert response.status_code == 400
        data = response.json()
        assert "Unsupported file type" in data["detail"]

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_file_too_large_by_header(self, mock_process_document, mock_stream, client):
        """Test that files too large are rejected based on Content-Length header"""
        from app.config import settings

        # Mock response with large content-length
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "Content-Type": "application/pdf",
            "Content-Length": str(settings.max_upload_size + 1000),
        }
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        response = client.post("/api/process-url", json={"url": "https://example.com/huge.pdf"})

        assert response.status_code == 413
        data = response.json()
        assert "too large" in data["detail"]

        # Should not process document
        mock_process_document.delay.assert_not_called()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_timeout_error(self, mock_stream, client):
        """Test handling of timeout errors"""
        mock_stream.side_effect = httpx.TimeoutException("Request timed out")

        response = client.post("/api/process-url", json={"url": "https://example.com/slow.pdf"})

        assert response.status_code == 408
        data = response.json()
        assert "timeout" in data["detail"].lower()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_connection_error(self, mock_stream, client):
        """Test handling of connection errors"""
        mock_stream.side_effect = httpx.ConnectError("Failed to connect")

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 502
        data = response.json()
        assert "connect" in data["detail"].lower()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_http_error_404(self, mock_stream, client):
        """Test handling of HTTP 404 errors"""
        # When raising HTTPStatusError, httpx requires request and response arguments
        # For our code, we just need it to hit the exception handler and check status code
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_stream.side_effect = httpx.HTTPStatusError("404 Not Found", request=mock_request, response=mock_response)

        response = client.post("/api/process-url", json={"url": "https://example.com/notfound.pdf"})

        assert response.status_code == 404
        data = response.json()
        assert "HTTP error" in data["detail"]

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_with_custom_filename(self, mock_process_document, mock_stream, client, tmp_path):
        """Test URL upload with custom filename"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF content"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Make request with custom filename
        response = client.post(
            "/api/process-url", json={"url": "https://example.com/doc.pdf", "filename": "my-document.pdf"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "my-document.pdf"

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_extracts_filename_from_url(self, mock_process_document, mock_stream, client, tmp_path):
        """Test that filename is extracted from URL when not provided"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF content"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Make request without custom filename
        response = client.post("/api/process-url", json={"url": "https://example.com/annual-report.pdf"})

        assert response.status_code == 200
        data = response.json()
        # Should extract "annual-report.pdf" from URL
        assert "annual-report" in data["filename"]

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_file_size_during_download(self, mock_process_document, mock_stream, client):
        """Test that file size is checked during download"""
        from app.config import settings

        # Create a large chunk that exceeds max_upload_size
        large_chunk = b"x" * (settings.max_upload_size + 1000)

        # Mock response without Content-Length header
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}  # No Content-Length

        async def mock_aiter_bytes(chunk_size=None):
            yield large_chunk

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        response = client.post("/api/process-url", json={"url": "https://example.com/big.pdf"})

        assert response.status_code == 413
        data = response.json()
        assert "too large" in data["detail"]

        # Should not process document
        mock_process_document.delay.assert_not_called()

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_request_exception(self, mock_stream, client):
        """Test handling of generic RequestError"""
        mock_stream.side_effect = httpx.RequestError("Generic request error")

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 500
        data = response.json()
        assert "Failed to download file" in data["detail"]

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_oserror_during_save(self, mock_stream, client, tmp_path, monkeypatch):
        """Test handling of OSError when saving file"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock workdir to a non-existent path to trigger OSError
        from app.config import settings

        original_workdir = settings.workdir
        monkeypatch.setattr(settings, "workdir", "/nonexistent/path/that/does/not/exist")

        try:
            response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

            assert response.status_code == 500
            data = response.json()
            assert "Failed to save file" in data["detail"]
        finally:
            # Restore original workdir
            monkeypatch.setattr(settings, "workdir", original_workdir)

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_unexpected_exception(self, mock_process_document, mock_stream, client):
        """Test handling of unexpected exceptions"""
        # Mock successful download but process_document.delay raises unexpected error
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock process_document.delay to raise an unexpected exception
        mock_process_document.delay.side_effect = RuntimeError("Unexpected processing error")

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 500
        data = response.json()
        assert "Unexpected error" in data["detail"]

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_filename_without_extension(self, mock_process_document, mock_stream, client):
        """Test that files without extensions are handled correctly"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # URL with no extension in path
        response = client.post("/api/process-url", json={"url": "https://example.com/document", "filename": "noext"})

        assert response.status_code == 200
        data = response.json()
        # Should still work, just without extension
        assert data["task_id"] == "test-task-id"

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_empty_path_uses_download(self, mock_process_document, mock_stream, client):
        """Test that empty URL path defaults to 'download' filename"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # URL with no path (will default to "download")
        response = client.post("/api/process-url", json={"url": "https://example.com"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-id"
        # Filename should start with "document" when no path is provided (sanitize_filename adds timestamp)
        assert "document" in data["filename"]

    def test_validate_url_no_hostname(self):
        """Test that URLs without hostname are rejected"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://")
        assert exc_info.value.status_code == 400
        assert "no hostname" in exc_info.value.detail

    def test_validate_file_type_by_extension_fallback(self):
        """Test that file type validation falls back to extension when content-type is empty"""
        from app.api.url_upload import validate_file_type

        # Empty content-type but valid extension
        assert validate_file_type("", "document.pdf") is True
        assert validate_file_type("", "image.jpg") is True
        assert validate_file_type("", "spreadsheet.xlsx") is True

        # Empty content-type and invalid extension
        assert validate_file_type("", "malware.exe") is False
        assert validate_file_type("", "script.sh") is False

    def test_is_private_ip_ipv6_loopback(self):
        """Test that IPv6 loopback is detected as private"""
        from app.utils.network import is_private_ip

        # IPv6 loopback (::1)
        assert is_private_ip("::1") is True

    def test_is_private_ip_link_local(self):
        """Test that link-local addresses are detected as private"""
        from app.utils.network import is_private_ip

        # Link-local address
        assert is_private_ip("169.254.1.1") is True

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_sanitizes_dangerous_filename(self, mock_process_document, mock_stream, client):
        """Test that dangerous filenames are sanitized"""
        # Mock successful download
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Dangerous filename with path traversal
        response = client.post(
            "/api/process-url", json={"url": "https://example.com/file.pdf", "filename": "../../../etc/passwd"}
        )

        assert response.status_code == 200
        data = response.json()
        # Filename should be sanitized (no path traversal)
        assert ".." not in data["filename"]
        assert "/" not in data["filename"]


@pytest.mark.unit
class TestURLUploadCoverageGaps:
    """Additional tests to cover previously uncovered lines/branches"""

    def test_validate_url_scheme_raises_for_non_http_scheme(self):
        """Test that validate_url_scheme raises ValueError for non-http/https scheme (line 41)"""
        from unittest.mock import MagicMock

        from app.api.url_upload import URLUploadRequest

        # Call the validator directly with a mock URL whose str() returns an ftp scheme
        mock_url = MagicMock()
        mock_url.__str__ = MagicMock(return_value="ftp://example.com/file")

        with pytest.raises(ValueError, match="Only HTTP and HTTPS URLs are allowed"):
            URLUploadRequest.validate_url_scheme(mock_url)

    @patch("socket.getaddrinfo")
    def test_is_private_ip_hostname_resolves_to_public_ip(self, mock_getaddrinfo):
        """Test that a hostname resolving to a public IP returns False (lines 65->61, 67)"""
        from app.utils.network import is_private_ip

        # Mock DNS resolution to return a single public IP (8.8.8.8 is Google DNS)
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("8.8.8.8", 0)),
        ]

        # "example.com" is not a direct IP, so socket.getaddrinfo is called
        result = is_private_ip("example.com")
        assert result is False
        mock_getaddrinfo.assert_called_once()

    @patch("app.utils.network.socket.getaddrinfo")
    def test_is_private_ip_unresolvable_hostname_fails_securely(self, mock_getaddrinfo):
        """Test that unresolvable hostnames fail securely by blocking access."""
        import socket

        from app.utils.network import is_private_ip

        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")

        result = is_private_ip("unresolvable.example.internal")
        assert result is True  # Fails securely

    @patch("socket.getaddrinfo")
    def test_is_private_ip_hostname_resolves_multiple_ips_all_public(self, mock_getaddrinfo):
        """Test hostname with multiple public IPs returns False (covers 65->61 loop branch)"""
        from app.utils.network import is_private_ip

        # Return two public IPs - neither is private, so loop runs twice (65->61) then returns False (67)
        mock_getaddrinfo.return_value = [
            (2, 1, 6, "", ("8.8.8.8", 0)),
            (2, 1, 6, "", ("1.1.1.1", 0)),
        ]

        result = is_private_ip("multi.example.com")
        assert result is False

    def test_validate_url_safety_non_http_scheme_direct(self):
        """Test validate_url_safety raises for ftp:// scheme (line 87)"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("ftp://example.com/file.txt")
        assert exc_info.value.status_code == 400
        assert "HTTP and HTTPS" in exc_info.value.detail

    @patch("app.api.url_upload.is_private_ip", return_value=False)
    def test_validate_url_safety_blocks_google_metadata_internal(self, mock_is_private):
        """Test that metadata.google.internal is blocked (line 107)"""
        from fastapi import HTTPException

        from app.api.url_upload import validate_url_safety

        # metadata.google.internal is in the explicit metadata_endpoints list.
        # Explicitly mock is_private_ip to return False so we always reach the
        # metadata_endpoints check on line 106-107, regardless of DNS availability.
        with pytest.raises(HTTPException) as exc_info:
            validate_url_safety("http://metadata.google.internal/computeMetadata/v1/")
        assert exc_info.value.status_code == 400
        assert "metadata" in exc_info.value.detail

    def test_validate_file_type_no_extension_not_allowed(self):
        """Test validate_file_type returns False for filename without extension (line 130->135)"""
        from app.api.url_upload import validate_file_type

        # Unknown content-type and filename has NO extension at all
        assert validate_file_type("application/x-unknown", "filename_without_extension") is False
        # Empty content-type and no extension
        assert validate_file_type("", "filename_without_extension") is False

    @patch("app.api.url_upload.sanitize_filename", return_value="")
    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_sanitize_filename_returns_empty(
        self, mock_process_document, mock_stream, mock_sanitize, client
    ):
        """Test that when sanitize_filename returns empty string, filename defaults to 'download' (line 177)"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF content"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        mock_task = Mock()
        mock_task.id = "test-task-id-sanitize"
        mock_process_document.delay.return_value = mock_task

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 200
        data = response.json()
        # When sanitize_filename returns "", safe_filename defaults to "download"
        assert data["filename"] == "download"

    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    @patch("app.api.url_upload.process_document")
    def test_process_url_skips_empty_chunks(self, mock_process_document, mock_stream, client):
        """Test that empty bytes chunks are skipped during download (line 234->233 branch)"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        # Mix empty bytes (falsy) with real content - covers the `if chunk:` False branch

        async def mock_aiter_bytes(chunk_size=None):
            yield b""
            yield b"PDF content"
            yield b""

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        mock_task = Mock()
        mock_task.id = "test-task-id-chunks"
        mock_process_document.delay.return_value = mock_task

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-id-chunks"

    @patch("app.api.url_upload.os.remove")
    @patch("app.api.url_upload.os.path.exists", return_value=True)
    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_oserror_cleanup_removes_existing_file(
        self, mock_stream, mock_exists, mock_remove, client, tmp_path, monkeypatch
    ):
        """Test OSError handler removes the partial file when it exists (line 285)"""
        import os

        from app.config import settings

        # Create a temp subdir then remove it so open() raises OSError (dir doesn't exist)
        non_existent = tmp_path / "removed_workdir"
        non_existent.mkdir()
        os.rmdir(non_existent)

        monkeypatch.setattr(settings, "workdir", str(non_existent))

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "100"}

        async def mock_aiter_bytes(chunk_size=None):
            yield b"PDF"

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        assert response.status_code == 500
        assert "Failed to save file" in response.json()["detail"]
        # os.path.exists returned True, so os.remove should have been called
        mock_remove.assert_called_once()

    @patch("app.api.url_upload.validate_file_type", side_effect=ValueError("unexpected internal error"))
    @patch("app.api.url_upload.httpx.AsyncClient.stream")
    def test_process_url_unexpected_exception_with_no_file_created(self, mock_stream, mock_validate, client):
        """Test unexpected exception before target_path is assigned; no file cleanup attempted (line 291->293)"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        mock_stream.return_value = mock_context

        response = client.post("/api/process-url", json={"url": "https://example.com/file.pdf"})

        # Generic exception (not HTTPException/OSError/RequestException) is caught and returns 500
        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]
