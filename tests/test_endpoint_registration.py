"""
Tests to verify that all critical API endpoints are properly registered.

This test module serves as a regression prevention mechanism to ensure
that endpoints remain accessible after code refactoring or reorganization.
"""

from unittest.mock import Mock, patch

import pytest

# Test constants
TEST_URL = "https://example.com/test.pdf"


@pytest.mark.unit
class TestEndpointRegistration:
    """Verify that critical API endpoints are registered in the FastAPI app"""

    @patch("app.api.url_upload.requests.get")
    @patch("app.api.url_upload.process_document")
    def test_process_url_endpoint_exists(self, mock_process_document, mock_requests_get, client):
        """Verify that /api/process-url endpoint is registered and accessible"""
        # Mock successful download to prevent actual HTTP requests
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}
        mock_response.iter_content = Mock(return_value=[b"PDF content"])
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Make a request to the endpoint - it should not return 404
        response = client.post("/api/process-url", json={"url": TEST_URL})

        # The endpoint exists if we don't get a 404
        # We may get other errors (401, 400, 500, etc.) due to validation or missing mocks,
        # but 404 specifically means the endpoint is not registered
        assert response.status_code != 404, (
            "Endpoint /api/process-url returned 404 (not found). "
            "This indicates the router is not properly registered in the application. "
            "Verify that url_upload_router is included in app/api/__init__.py"
        )

    @patch("app.api.url_upload.requests.get")
    @patch("app.api.url_upload.process_document")
    def test_process_url_endpoint_accepts_post(self, mock_process_document, mock_requests_get, client):
        """Verify that /api/process-url accepts POST requests"""
        # Mock successful download to prevent actual HTTP requests
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}
        mock_response.iter_content = Mock(return_value=[b"PDF content"])
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Try POST request
        response = client.post("/api/process-url", json={"url": TEST_URL})

        # Should not return 405 (Method Not Allowed)
        assert response.status_code != 405, (
            "Endpoint /api/process-url returned 405 (Method Not Allowed) for POST. "
            "Verify the endpoint is decorated with @router.post()"
        )

    @patch("app.api.url_upload.requests.get")
    @patch("app.api.url_upload.process_document")
    def test_api_router_included_in_app(self, mock_process_document, mock_requests_get, client):
        """Verify that the main API router is included in the FastAPI app"""
        # Mock successful download for /api/process-url test
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf", "Content-Length": "1024"}
        mock_response.iter_content = Mock(return_value=[b"PDF content"])
        mock_response.raise_for_status = Mock()
        mock_requests_get.return_value = mock_response

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Test a few known API endpoints to ensure the /api prefix works
        endpoints_to_check = [
            ("/api/process-url", "post"),
            ("/api/diagnostic/settings", "get"),
        ]

        for endpoint, method in endpoints_to_check:
            if method == "get":
                response = client.get(endpoint)
            else:
                response = client.post(endpoint, json={"url": TEST_URL})

            # None of these should return 404
            assert response.status_code != 404, (
                f"Endpoint {endpoint} returned 404. "
                f"Verify that api_router is included in app/main.py with prefix='/api'"
            )
