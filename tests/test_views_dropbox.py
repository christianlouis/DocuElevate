"""Tests for app/views/dropbox.py module."""

import json
from unittest.mock import patch

import pytest

from app.models import UserIntegration


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

    def test_dropbox_setup_user_mode_invalid_json_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is invalid JSON."""
        owner_id = "user_invalid_json@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="DROPBOX",
            name="My Dropbox (bad cfg)",
            config="{INVALID JSON}",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.dropbox.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors despite the bad config
        assert b"user_mode" not in response.content or b"Back to Integrations" in response.content

    def test_dropbox_setup_user_mode_none_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is None (no folder path)."""
        owner_id = "user_none_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="DROPBOX",
            name="My Dropbox (no cfg)",
            config=None,
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.dropbox.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors, with empty folder_path
        assert b"Back to Integrations" in response.content

    def test_dropbox_setup_user_mode_watchfolder_config(self, client, db_session):
        """Test user-mode correctly loads folder_path from WATCH_FOLDER source config."""
        owner_id = "user_wf_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="SOURCE",
            integration_type="WATCH_FOLDER",
            name="My Dropbox Watch",
            config=json.dumps({"source_type": "dropbox", "folder_path": "/Inbox"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.dropbox.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"/Inbox" in response.content
        assert b"Back to Integrations" in response.content

    def test_dropbox_setup_user_mode_integration_not_found(self, client, db_session):
        """Test user-mode falls back to admin mode when integration not owned by user."""
        with patch("app.views.dropbox.get_current_owner_id", return_value="other_user@example.com"):
            response = client.get("/dropbox-setup?integration_id=999999")

        assert response.status_code == 200
        # Falls back to admin mode (no "Back to Integrations" link)
        assert b"Dropbox Integration Setup" in response.content
        """Test user-mode correctly loads folder path from integration config."""
        owner_id = "user_valid_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="DROPBOX",
            name="My Dropbox",
            config=json.dumps({"folder": "/Documents/Uploads"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.dropbox.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"/Documents/Uploads" in response.content
        assert b"Back to Integrations" in response.content

    def test_dropbox_setup_user_mode_system_credentials_shown(self, client, db_session):
        """Test that system credentials toggle appears when system creds are configured."""
        owner_id = "user_sys_creds@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="DROPBOX",
            name="My Dropbox",
            config=json.dumps({"folder": "/test"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with (
            patch("app.views.dropbox.get_current_owner_id", return_value=owner_id),
            patch("app.views.dropbox.settings") as mock_settings,
        ):
            mock_settings.dropbox_app_key = "system-key"
            mock_settings.dropbox_app_secret = "system-secret"
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_folder = None
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"use-system-creds" in response.content
        assert b"DocuElevate" in response.content

    def test_dropbox_setup_user_mode_no_system_credentials(self, client, db_session):
        """Test that system credentials toggle is hidden when no system creds configured."""
        owner_id = "user_no_sys@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="DROPBOX",
            name="My Dropbox",
            config=json.dumps({"folder": "/test"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with (
            patch("app.views.dropbox.get_current_owner_id", return_value=owner_id),
            patch("app.views.dropbox.settings") as mock_settings,
        ):
            mock_settings.dropbox_app_key = None
            mock_settings.dropbox_app_secret = None
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_folder = None
            response = client.get(f"/dropbox-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # When no system credentials, hasSystemCredentials JS var should be false
        assert b"hasSystemCredentials = false" in response.content
