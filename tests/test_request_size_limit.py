"""
Tests for the RequestSizeLimitMiddleware.

Validates that:
- Non-file requests exceeding MAX_REQUEST_BODY_SIZE are rejected with HTTP 413
- Multipart/form-data uploads exceeding MAX_UPLOAD_SIZE are rejected with HTTP 413
- Requests within the limits pass through normally
- Missing Content-Length header does not cause false rejections
"""

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestRequestSizeLimitMiddleware:
    """Unit tests for the RequestSizeLimitMiddleware dispatch logic."""

    def test_middleware_rejects_oversized_json_body(self, client: TestClient):
        """Non-file request with Content-Length exceeding MAX_REQUEST_BODY_SIZE is rejected."""
        from app.config import settings

        oversized = settings.max_request_body_size + 1
        response = client.post(
            "/api/process-url",
            content=b"x" * 10,  # actual body doesn't matter; header is checked first
            headers={
                "Content-Length": str(oversized),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 413
        detail = response.json()["detail"]
        assert "MAX_REQUEST_BODY_SIZE" in detail

    def test_middleware_allows_request_within_json_limit(self, client: TestClient):
        """Non-file request with Content-Length within limit is not rejected by middleware."""
        from app.config import settings

        # Send a body within limit; the endpoint may return 4xx for its own reasons,
        # but the middleware must NOT return 413.
        small = settings.max_request_body_size - 1
        response = client.post(
            "/api/process-url",
            content=b"{}",
            headers={"Content-Length": str(small), "Content-Type": "application/json"},
        )
        # The endpoint may return 400/422 (bad JSON or auth), but NOT 413 from middleware
        assert response.status_code != 413

    def test_middleware_rejects_oversized_multipart_upload(self, client: TestClient):
        """Multipart upload with Content-Length exceeding MAX_UPLOAD_SIZE is rejected."""
        from app.config import settings

        oversized = settings.max_upload_size + 1
        response = client.post(
            "/api/ui-upload",
            content=b"x" * 10,
            headers={
                "Content-Length": str(oversized),
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
        )
        assert response.status_code == 413
        detail = response.json()["detail"]
        assert "MAX_UPLOAD_SIZE" in detail

    def test_middleware_allows_multipart_within_upload_limit(self, client: TestClient):
        """Multipart upload with Content-Length within MAX_UPLOAD_SIZE passes middleware."""
        from app.config import settings

        # A Content-Length within the upload limit should NOT be rejected by the middleware.
        # The endpoint itself will reject because the body is not a real multipart payload.
        within_limit = min(1024, settings.max_upload_size - 1)
        response = client.post(
            "/api/ui-upload",
            content=b"x" * 10,
            headers={
                "Content-Length": str(within_limit),
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
        )
        # Not rejected by middleware (may be 400/422 from endpoint)
        assert response.status_code != 413

    def test_middleware_allows_request_without_content_length(self, client: TestClient):
        """Requests without Content-Length header pass through middleware (no false rejection)."""
        # Remove Content-Length header entirely; middleware must not reject
        response = client.get("/api/files")
        # May get 200/401/403 but not 413
        assert response.status_code != 413

    def test_middleware_error_message_contains_limit_and_config_hint(self, client: TestClient):
        """413 response body contains limit details and config variable name."""
        from app.config import settings

        oversized = settings.max_request_body_size + 1
        response = client.post(
            "/api/process-url",
            content=b"{}",
            headers={
                "Content-Length": str(oversized),
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 413
        detail = response.json()["detail"]
        assert str(settings.max_request_body_size) in detail
        assert "SECURITY_AUDIT.md" in detail


@pytest.mark.integration
class TestFileUploadSizeLimitStreaming:
    """Integration tests for streaming size enforcement in the ui-upload endpoint."""

    @pytest.fixture(autouse=True)
    def mock_celery(self):
        with (
            patch("app.api.files.process_document") as mock_proc,
            patch("app.api.files.convert_to_pdf") as mock_conv,
        ):
            from unittest.mock import MagicMock

            task = MagicMock()
            task.id = "test-task-id"
            mock_proc.delay.return_value = task
            mock_conv.delay.return_value = task
            yield

    def test_upload_rejected_when_content_length_declared_too_large(self, client: TestClient):
        """Upload is rejected early via Content-Length check before reading data."""
        from app.config import settings

        oversized = settings.max_upload_size + 1
        pdf_data = b"%PDF-1.4\n%EOF"
        response = client.post(
            "/api/ui-upload",
            content=pdf_data,
            headers={
                "Content-Length": str(oversized),
                "Content-Type": "multipart/form-data; boundary=boundary",
            },
        )
        assert response.status_code == 413

    def test_upload_rejected_mid_stream_when_data_exceeds_limit(self, client: TestClient):
        """Upload is rejected mid-stream when actual data exceeds max_upload_size."""
        from app.config import settings

        # Temporarily reduce max_upload_size to a tiny value for this test
        small_limit = 100  # 100 bytes
        with patch.object(settings, "max_upload_size", small_limit):
            large_content = b"x" * (small_limit + 1)
            response = client.post(
                "/api/ui-upload",
                files={"file": ("big.pdf", io.BytesIO(large_content), "application/pdf")},
            )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()

    def test_upload_succeeds_within_size_limit(self, client: TestClient):
        """Small, valid file upload completes successfully within size limits."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<</Type /Catalog>>\nendobj\n%%EOF"
        response = client.post(
            "/api/ui-upload",
            files={"file": ("small.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
