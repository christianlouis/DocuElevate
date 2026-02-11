"""
Tests to verify that all critical API endpoints are properly registered.

This test module serves as a regression prevention mechanism to ensure
that endpoints remain accessible after code refactoring or reorganization.
"""

import pytest

# Test constants
TEST_URL = "https://example.com/test.pdf"


@pytest.mark.unit
class TestEndpointRegistration:
    """Verify that critical API endpoints are registered in the FastAPI app"""

    def test_process_url_endpoint_exists(self, client):
        """Verify that /api/process-url endpoint is registered and accessible"""
        # Make a request to the endpoint - it should not return 404
        response = client.post(
            "/api/process-url",
            json={"url": TEST_URL}
        )
        
        # The endpoint exists if we don't get a 404
        # We may get other errors (401, 400, 500, etc.) due to validation or missing mocks,
        # but 404 specifically means the endpoint is not registered
        assert response.status_code != 404, (
            f"Endpoint /api/process-url returned 404 (not found). "
            f"This indicates the router is not properly registered in the application. "
            f"Verify that url_upload_router is included in app/api/__init__.py"
        )

    def test_process_url_endpoint_accepts_post(self, client):
        """Verify that /api/process-url accepts POST requests"""
        # Try POST request
        response = client.post(
            "/api/process-url",
            json={"url": TEST_URL}
        )
        
        # Should not return 405 (Method Not Allowed)
        assert response.status_code != 405, (
            f"Endpoint /api/process-url returned 405 (Method Not Allowed) for POST. "
            f"Verify the endpoint is decorated with @router.post()"
        )

    def test_api_router_included_in_app(self, client):
        """Verify that the main API router is included in the FastAPI app"""
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
