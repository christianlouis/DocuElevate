"""Tests for app/views/onedrive.py module."""
import pytest


@pytest.mark.integration
class TestOnedriveViews:
    """Tests for OneDrive view routes."""

    def test_onedrive_setup_page(self, client):
        """Test the OneDrive setup page."""
        response = client.get("/onedrive-setup")
        assert response.status_code == 200

    def test_onedrive_callback_no_code(self, client):
        """Test the OneDrive OAuth callback without code."""
        response = client.get("/onedrive-callback", follow_redirects=False)
        assert response.status_code == 200

    def test_onedrive_callback_with_error(self, client):
        """Test the OneDrive OAuth callback with error."""
        response = client.get("/onedrive-callback?error=access_denied")
        assert response.status_code == 200

    def test_onedrive_callback_with_code(self, client):
        """Test the OneDrive OAuth callback with auth code."""
        response = client.get("/onedrive-callback?code=test_code")
        assert response.status_code == 200
