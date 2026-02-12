"""Tests for app/api/process.py module."""

import pytest


@pytest.mark.integration
class TestProcessEndpoints:
    """Tests for process API endpoints."""

    def test_process_file_not_found(self, client):
        """Test POST /api/process/ with non-existent file."""
        response = client.post("/api/process/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_dropbox_file_not_found(self, client):
        """Test POST /api/send_to_dropbox/ with non-existent file."""
        response = client.post("/api/send_to_dropbox/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_paperless_file_not_found(self, client):
        """Test POST /api/send_to_paperless/ with non-existent file."""
        response = client.post("/api/send_to_paperless/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_nextcloud_file_not_found(self, client):
        """Test POST /api/send_to_nextcloud/ with non-existent file."""
        response = client.post("/api/send_to_nextcloud/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_google_drive_file_not_found(self, client):
        """Test POST /api/send_to_google_drive/ with non-existent file."""
        response = client.post("/api/send_to_google_drive/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_onedrive_file_not_found(self, client):
        """Test POST /api/send_to_onedrive/ with non-existent file."""
        response = client.post("/api/send_to_onedrive/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_send_to_all_destinations_file_not_found(self, client):
        """Test POST /api/send_to_all_destinations/ with non-existent file."""
        response = client.post("/api/send_to_all_destinations/?file_path=nonexistent.pdf")
        assert response.status_code == 400

    def test_processall_endpoint(self, client, tmp_path):
        """Test POST /api/processall with no PDF files in workdir."""
        from unittest.mock import patch

        with patch("app.api.process.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            response = client.post("/api/processall")
            assert response.status_code == 200
            data = response.json()
            assert "No PDF files found" in data["message"]
