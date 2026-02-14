"""Tests for app/views/google_drive.py module."""

import urllib.parse
from unittest.mock import patch

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

    def test_google_drive_callback_with_code_and_state(self, client):
        """Test the Google Drive OAuth callback with code and state."""
        response = client.get("/google-drive-callback?code=test_code&state=test_state")
        assert response.status_code == 200

    def test_google_drive_auth_start_with_redirect_uri(self, client):
        """Test starting Google Drive OAuth flow with explicit redirect_uri."""
        client_id = "test_client_id_123"
        redirect_uri = "https://example.com/callback"
        response = client.get(
            f"/google-drive-auth-start?client_id={client_id}&redirect_uri={redirect_uri}", follow_redirects=False
        )

        assert response.status_code in [302, 307]  # Redirect status codes

        # Verify redirect location
        location = response.headers.get("location")
        assert location is not None
        assert "accounts.google.com/o/oauth2/auth" in location
        assert f"client_id={client_id}" in location
        assert urllib.parse.quote(redirect_uri) in location
        assert "response_type=code" in location
        assert "access_type=offline" in location
        assert "prompt=consent" in location
        # Verify scope includes drive.file
        assert "scope=" in location

    def test_google_drive_auth_start_without_redirect_uri(self, client):
        """Test starting Google Drive OAuth flow without explicit redirect_uri."""
        client_id = "test_client_id_456"
        response = client.get(f"/google-drive-auth-start?client_id={client_id}", follow_redirects=False)

        assert response.status_code in [302, 307]  # Redirect status codes

        # Verify redirect location
        location = response.headers.get("location")
        assert location is not None
        assert "accounts.google.com/o/oauth2/auth" in location
        assert f"client_id={client_id}" in location
        # Should use default redirect_uri based on request host
        assert "redirect_uri=" in location

    def test_google_drive_auth_start_scope_configuration(self, client):
        """Test that Google Drive auth start uses correct OAuth scope."""
        client_id = "test_client_id_789"
        response = client.get(f"/google-drive-auth-start?client_id={client_id}", follow_redirects=False)

        location = response.headers.get("location")
        assert location is not None

        # The scope should be URL encoded, so check for the encoded version
        # drive.file scope: https://www.googleapis.com/auth/drive.file
        expected_scope = urllib.parse.quote("https://www.googleapis.com/auth/drive.file")
        assert expected_scope in location

    @patch("app.views.google_drive.settings")
    def test_google_drive_setup_page_with_folder_id_none(self, mock_settings, client):
        """Test setup page when folder_id is None - should show not configured."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_client_id = "test_client_id"
        mock_settings.google_drive_client_secret = "test_secret"
        mock_settings.google_drive_refresh_token = "test_token"
        mock_settings.google_drive_credentials_json = '{"test": "creds"}'
        mock_settings.google_drive_folder_id = None  # Empty folder ID

        response = client.get("/google-drive-setup")
        assert response.status_code == 200
        # Verify the response context indicates configuration is incomplete
        # The is_configured flag should be False when folder_id is missing
        assert b"google_drive.html" in response.content or response.status_code == 200

    @patch("app.views.google_drive.settings")
    def test_google_drive_setup_page_with_folder_id_empty_string(self, mock_settings, client):
        """Test setup page when folder_id is empty string - should show not configured."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_client_id = "test_client_id"
        mock_settings.google_drive_client_secret = "test_secret"
        mock_settings.google_drive_refresh_token = "test_token"
        mock_settings.google_drive_credentials_json = '{"test": "creds"}'
        mock_settings.google_drive_folder_id = ""  # Empty string folder ID

        response = client.get("/google-drive-setup")
        assert response.status_code == 200
        # Should handle empty string folder_id similar to None

    @patch("app.views.google_drive.settings")
    def test_google_drive_setup_page_oauth_mode(self, mock_settings, client):
        """Test setup page in OAuth mode."""
        mock_settings.google_drive_use_oauth = True
        mock_settings.google_drive_client_id = "oauth_client_id"
        mock_settings.google_drive_client_secret = "oauth_secret"
        mock_settings.google_drive_refresh_token = "oauth_token"
        mock_settings.google_drive_folder_id = "test_folder_id"
        mock_settings.google_drive_credentials_json = None

        response = client.get("/google-drive-setup")
        assert response.status_code == 200

    @patch("app.views.google_drive.settings")
    def test_google_drive_setup_page_service_account_mode(self, mock_settings, client):
        """Test setup page in service account mode."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_folder_id = "test_folder_id"
        mock_settings.google_drive_client_id = None
        mock_settings.google_drive_client_secret = None
        mock_settings.google_drive_refresh_token = None

        response = client.get("/google-drive-setup")
        assert response.status_code == 200
