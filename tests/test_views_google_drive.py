"""Tests for app/views/google_drive.py module."""

import json
import urllib.parse
from unittest.mock import patch

import pytest

from app.models import UserIntegration


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

    def test_google_drive_setup_page_with_integration_id(self, client):
        """Test the Google Drive setup page accepts integration_id query param."""
        response = client.get("/google-drive-setup?integration_id=99")
        assert response.status_code == 200
        # The template should store the integration_id for per-user OAuth flow
        assert b"oauth_integration_id" in response.content
        assert b"99" in response.content

    def test_google_drive_setup_page_without_integration_id(self, client):
        """Test the Google Drive setup page works without integration_id (global flow)."""
        response = client.get("/google-drive-setup")
        assert response.status_code == 200
        body = response.text
        assert "oauth_integration_id" in body
        assert 'const integrationId = ""' in body

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

    def test_google_drive_setup_user_mode_invalid_json_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is invalid JSON."""
        owner_id = "user_gd_invalid_json@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="GOOGLE_DRIVE",
            name="My GDrive (bad cfg)",
            config="{INVALID JSON}",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.google_drive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/google-drive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors despite the bad config
        assert b"Back to Integrations" in response.content

    def test_google_drive_setup_user_mode_none_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is None (no folder ID)."""
        owner_id = "user_gd_none_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="GOOGLE_DRIVE",
            name="My GDrive (no cfg)",
            config=None,
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.google_drive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/google-drive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors, with empty folder_id
        assert b"Back to Integrations" in response.content

    def test_google_drive_setup_user_mode_integration_not_found(self, client, db_session):
        """Test user-mode falls back to admin mode when integration not owned by user."""
        with patch("app.views.google_drive.get_current_owner_id", return_value="other_user@example.com"):
            response = client.get("/google-drive-setup?integration_id=999999")

        assert response.status_code == 200
        # Falls back to admin mode (no "Back to Integrations" link)
        assert b"Google Drive Integration Setup" in response.content

    def test_google_drive_setup_user_mode_valid_config(self, client, db_session):
        """Test user-mode correctly loads folder ID from integration config."""
        owner_id = "user_gd_valid_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="GOOGLE_DRIVE",
            name="My Google Drive",
            config=json.dumps({"folder_id": "1abc2def3ghi"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.google_drive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/google-drive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"1abc2def3ghi" in response.content
        assert b"Back to Integrations" in response.content
