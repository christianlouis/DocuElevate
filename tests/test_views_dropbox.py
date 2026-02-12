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
