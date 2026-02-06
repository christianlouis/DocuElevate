"""
API endpoint tests for path traversal security.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.integration
@pytest.mark.security
class TestAPIPathTraversalSecurity:
    """Tests to ensure API endpoints block path traversal attacks."""
    
    def test_process_endpoint_blocks_path_traversal(self):
        """Test that /api/process endpoint blocks path traversal."""
        response = client.post(
            "/api/process/",
            params={"file_path": "../../../etc/passwd"}
        )
        # Should return 400 Bad Request
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_dropbox_blocks_path_traversal(self):
        """Test that /api/send_to_dropbox/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_dropbox/",
            params={"file_path": "../../etc/passwd"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_paperless_blocks_path_traversal(self):
        """Test that /api/send_to_paperless/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_paperless/",
            params={"file_path": "../sensitive.pdf"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_nextcloud_blocks_path_traversal(self):
        """Test that /api/send_to_nextcloud/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_nextcloud/",
            params={"file_path": "foo/../../etc/shadow"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_google_drive_blocks_path_traversal(self):
        """Test that /api/send_to_google_drive/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_google_drive/",
            params={"file_path": "/etc/passwd"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_onedrive_blocks_path_traversal(self):
        """Test that /api/send_to_onedrive/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_onedrive/",
            params={"file_path": "../../../root/.ssh/id_rsa"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
    
    def test_send_to_all_destinations_blocks_path_traversal(self):
        """Test that /api/send_to_all_destinations/ endpoint blocks path traversal."""
        response = client.post(
            "/api/send_to_all_destinations/",
            params={"file_path": "../../secret.pdf"}
        )
        assert response.status_code == 400
        assert "Path traversal detected" in response.json()["detail"] or "Invalid file path" in response.json()["detail"]
