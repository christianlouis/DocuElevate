"""Tests for app/views/dropbox.py module."""

import pytest


@pytest.mark.integration
class TestDropboxViews:
    """Tests for Dropbox view routes."""

    def test_dropbox_setup_page(self, client):
        """Test the Dropbox setup page."""
        response = client.get("/dropbox-setup")
        assert response.status_code == 200

    def test_dropbox_callback_no_code(self, client):
        """Test the Dropbox OAuth callback without code."""
        response = client.get("/dropbox-callback", follow_redirects=False)
        assert response.status_code == 200

    def test_dropbox_callback_with_error(self, client):
        """Test the Dropbox OAuth callback with error."""
        response = client.get("/dropbox-callback?error=access_denied")
        assert response.status_code == 200

    def test_dropbox_callback_with_code(self, client):
        """Test the Dropbox OAuth callback with auth code."""
        response = client.get("/dropbox-callback?code=test_code")
        assert response.status_code == 200

    def test_dropbox_setup_page_with_integration_id(self, client):
        """Test the Dropbox setup page accepts integration_id query param."""
        response = client.get("/dropbox-setup?integration_id=42")
        assert response.status_code == 200
        # The template should store the integration_id for per-user OAuth flow
        assert b"oauth_integration_id" in response.content
        assert b"42" in response.content

    def test_dropbox_setup_page_without_integration_id(self, client):
        """Test the Dropbox setup page works without integration_id (global flow)."""
        response = client.get("/dropbox-setup")
        assert response.status_code == 200
        # The template should not set integration_id when not provided
        body = response.text
        assert "oauth_integration_id" in body  # The JS code is always present
        # But integration_id template var should be empty
        assert 'const integrationId = ""' in body
