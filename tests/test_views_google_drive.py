"""Tests for app/views/google_drive.py module."""
import pytest


@pytest.mark.integration
class TestGoogleDriveViews:
    """Tests for Google Drive view routes."""

    def test_google_drive_setup_page(self, client):
        """Test the Google Drive setup page."""
        response = client.get("/google-drive-setup")
        assert response.status_code == 200

    def test_google_drive_callback_no_code(self, client):
        """Test the Google Drive OAuth callback without code."""
        response = client.get("/google-drive-callback", follow_redirects=False)
        assert response.status_code == 200

    def test_google_drive_callback_with_error(self, client):
        """Test the Google Drive OAuth callback with error."""
        response = client.get("/google-drive-callback?error=access_denied")
        assert response.status_code == 200

    def test_google_drive_callback_with_code(self, client):
        """Test the Google Drive OAuth callback with auth code."""
        response = client.get("/google-drive-callback?code=test_code")
        assert response.status_code == 200
