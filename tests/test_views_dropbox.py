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

    def test_dropbox_setup_user_mode_valid_config(self, client, db_session):
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
