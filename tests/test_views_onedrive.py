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

    def test_onedrive_setup_page_with_integration_id(self, client):
        """Test the OneDrive setup page accepts integration_id query param."""
        response = client.get("/onedrive-setup?integration_id=77")
        assert response.status_code == 200
        # The template should store the integration_id for per-user OAuth flow
        assert b"oauth_integration_id" in response.content
        assert b"77" in response.content

    def test_onedrive_setup_page_without_integration_id(self, client):
        """Test the OneDrive setup page works without integration_id (global flow)."""
        response = client.get("/onedrive-setup")
        assert response.status_code == 200
        body = response.text
        assert "oauth_integration_id" in body
        assert 'const integrationId = ""' in body
