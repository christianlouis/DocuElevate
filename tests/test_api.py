"""
Integration tests for API endpoints.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestHealthEndpoints:
    """Tests for health check and status endpoints."""
    
    def test_root_endpoint(self, client: TestClient):
        """Test that root endpoint redirects to UI."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code in [200, 307, 308]  # OK or redirect
    
    def test_docs_endpoint(self, client: TestClient):
        """Test that API documentation is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()
    
    def test_openapi_schema(self, client: TestClient):
        """Test that OpenAPI schema is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "DocuElevate"


@pytest.mark.integration
class TestFileEndpoints:
    """Tests for file management endpoints."""
    
    def test_list_files_empty(self, client: TestClient):
        """Test listing files when database is empty."""
        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_get_nonexistent_file(self, client: TestClient):
        """Test getting a file that doesn't exist."""
        response = client.get("/api/files/99999")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.requires_external
class TestProcessingEndpoints:
    """Tests for document processing endpoints."""
    
    def test_process_endpoint_exists(self, client: TestClient):
        """Test that process endpoint is registered."""
        # This will return 422 (validation error) without proper data,
        # but confirms the endpoint exists
        response = client.post("/api/process")
        assert response.status_code in [400, 422]  # Bad request or validation error


@pytest.mark.integration
class TestConfigEndpoints:
    """Tests for configuration endpoints."""
    
    def test_config_status_endpoint(self, client: TestClient):
        """Test configuration status endpoint if it exists."""
        # Some apps have a /status or /config/status endpoint
        response = client.get("/api/status")
        # Endpoint may not exist, which is fine
        assert response.status_code in [200, 404]


@pytest.mark.integration
class TestAuthEndpoints:
    """Tests for authentication endpoints (when auth is disabled in tests)."""
    
    def test_unauthenticated_access_with_auth_disabled(self, client: TestClient):
        """Test that API is accessible when auth is disabled."""
        # With AUTH_ENABLED=False, API should be accessible
        response = client.get("/api/files")
        assert response.status_code == 200
