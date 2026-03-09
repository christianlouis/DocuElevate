"""Tests for app/views/onedrive.py module."""

import json
from unittest.mock import patch

import pytest

from app.models import UserIntegration


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

    def test_onedrive_setup_user_mode_invalid_json_config(self, client, db_session):
        """Test user-mode renders correctly when integration.config is invalid JSON."""
        owner_id = "user_od_invalid_json@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="My OneDrive (bad cfg)",
            config="{INVALID JSON}",
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        # Should render user mode without errors despite the bad config
        assert b"Back to Integrations" in response.content

    def test_onedrive_setup_user_mode_valid_config(self, client, db_session):
        """Test user-mode correctly loads folder path from integration config."""
        owner_id = "user_od_valid_cfg@example.com"
        integration = UserIntegration(
            owner_id=owner_id,
            direction="DESTINATION",
            integration_type="ONEDRIVE",
            name="My OneDrive",
            config=json.dumps({"folder_path": "Documents/Archive"}),
            is_active=True,
        )
        db_session.add(integration)
        db_session.commit()
        db_session.refresh(integration)

        with patch("app.views.onedrive.get_current_owner_id", return_value=owner_id):
            response = client.get(f"/onedrive-setup?integration_id={integration.id}")

        assert response.status_code == 200
        assert b"Documents/Archive" in response.content
        assert b"Back to Integrations" in response.content
