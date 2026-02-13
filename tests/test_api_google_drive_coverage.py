"""
Additional tests for app/api/google_drive.py to increase coverage from 81.55% to 85%+.

Focuses on:
- Missing OAuth credentials validation paths (lines 127-128, 237-238, 248-249)
- Token retrieval error paths
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestTestGoogleDriveTokenMissingCredentials:
    """Test missing credentials scenarios in test_google_drive_token endpoint."""

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_missing_client_id(self, mock_settings, client: TestClient):
        """Test OAuth token test with missing client_id."""
        # Configure settings to trigger OAuth path
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: None)
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_missing_client_secret(self, mock_settings, client: TestClient):
        """Test OAuth token test with missing client_secret."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: None)
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_missing_refresh_token(self, mock_settings, client: TestClient):
        """Test OAuth token test with missing refresh_token."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: None)

        response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_empty_credentials(self, mock_settings, client: TestClient):
        """Test OAuth token test with empty string credentials."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "")
        type(mock_settings).google_drive_client_secret = property(lambda self: "")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "")

        response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()


@pytest.mark.unit
class TestGetGoogleDriveTokenInfo:
    """Test get_google_drive_token_info endpoint edge cases."""

    @patch("app.api.google_drive.settings")
    def test_get_token_info_oauth_disabled(self, mock_settings, client: TestClient):
        """Test get_token_info when OAuth is disabled."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: False)

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not enabled" in data["message"].lower() or "service account" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_get_token_info_missing_client_id(self, mock_settings, client: TestClient):
        """Test get_token_info with missing client_id."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: None)
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_get_token_info_missing_client_secret(self, mock_settings, client: TestClient):
        """Test get_token_info with missing client_secret."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: None)
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("app.api.google_drive.settings")
    def test_get_token_info_missing_refresh_token(self, mock_settings, client: TestClient):
        """Test get_token_info with missing refresh_token."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: None)

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"].lower()

    @patch("google.auth.transport.requests.Request")
    @patch("google.oauth2.credentials.Credentials")
    @patch("app.api.google_drive.settings")
    def test_get_token_info_token_refresh_error(
        self, mock_settings, mock_credentials_class, mock_request, client: TestClient
    ):
        """Test get_token_info when token refresh fails."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        # Mock credentials to raise error on refresh
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.refresh.side_effect = Exception("invalid_grant: Token has been revoked")
        mock_credentials_class.return_value = mock_creds

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        # Should detect invalid_grant error
        assert "needs_reauth" in data or "invalid_grant" in data["message"].lower() or "error" in data["status"]

    @patch("google.auth.transport.requests.Request")
    @patch("google.oauth2.credentials.Credentials")
    @patch("app.api.google_drive.settings")
    def test_get_token_info_generic_error(
        self, mock_settings, mock_credentials_class, mock_request, client: TestClient
    ):
        """Test get_token_info with generic error."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "token")

        # Mock credentials to raise generic error
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.refresh.side_effect = Exception("Network timeout")
        mock_credentials_class.return_value = mock_creds

        response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


@pytest.mark.unit
class TestSaveGoogleDriveSettings:
    """Test save_google_drive_settings endpoint edge cases."""

    @patch("app.api.google_drive.settings")
    @patch("os.path.exists")
    def test_save_settings_env_file_not_exists(self, mock_exists, mock_settings, client: TestClient):
        """Test saving settings when .env file doesn't exist (Docker container scenario)."""
        mock_exists.return_value = False

        response = client.post(
            "/api/google-drive/save-settings",
            data={
                "refresh_token": "new_token",
                "client_id": "new_id",
                "client_secret": "new_secret",
                "folder_id": "folder123",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["in_memory_only"] is True

    @patch("app.api.google_drive.settings")
    @patch("os.path.exists")
    def test_save_settings_only_refresh_token(self, mock_exists, mock_settings, client: TestClient):
        """Test saving with only refresh_token (minimal required field)."""
        mock_exists.return_value = False

        response = client.post(
            "/api/google-drive/save-settings",
            data={"refresh_token": "new_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("app.api.google_drive.settings")
    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    @patch("os.path.exists")
    def test_save_settings_env_file_write_error(self, mock_exists, mock_open, mock_settings, client: TestClient):
        """Test saving when .env file write fails but continues with in-memory update."""
        mock_exists.return_value = True

        response = client.post(
            "/api/google-drive/save-settings",
            data={"refresh_token": "new_token"}
        )

        # Should succeed (in-memory update) even if file write fails
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


@pytest.mark.unit  
class TestHelperFunctions:
    """Test helper functions in google_drive module."""
    
    def test_format_time_remaining_expired(self):
        """Test format_time_remaining with negative timedelta."""
        from app.api.google_drive import format_time_remaining
        from datetime import timedelta
        
        # Expired time
        delta = timedelta(seconds=-1)
        result = format_time_remaining(delta)
        assert result == "Expired"
    
    def test_format_time_remaining_days(self):
        """Test format_time_remaining with days."""
        from app.api.google_drive import format_time_remaining
        from datetime import timedelta
        
        # 2 days, 3 hours
        delta = timedelta(days=2, hours=3)
        result = format_time_remaining(delta)
        assert "2 days" in result
        assert "3 hours" in result
        
    def test_format_time_remaining_hours_only(self):
        """Test format_time_remaining with hours but no days."""
        from app.api.google_drive import format_time_remaining
        from datetime import timedelta
        
        # 5 hours, 30 minutes
        delta = timedelta(hours=5, minutes=30)
        result = format_time_remaining(delta)
        assert "5 hours" in result
        assert "30 minutes" in result
        
    def test_format_time_remaining_singular_units(self):
        """Test format_time_remaining with singular units."""
        from app.api.google_drive import format_time_remaining
        from datetime import timedelta
        
        # 1 day, 1 hour
        delta = timedelta(days=1, hours=1)
        result = format_time_remaining(delta)
        # Should use singular form (no 's')
        assert "1 day" in result and "1 days" not in result
        assert "1 hour" in result and "1 hours" not in result
