"""
Coverage-targeted tests for app/api/onedrive.py

Focuses on uncovered lines: 98-99, 121-143, 160-161, 170-171,
324-326, 400-402, 436-438.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestTestTokenRefreshFailed:
    """Cover lines 98-99: token refresh returns non-200."""

    @patch("app.api.onedrive.requests.post")
    def test_test_token_refresh_returns_non_200(self, mock_post, client: TestClient):
        """Test token refresh returning a failure status hits the error branch."""
        from app.config import settings

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"
        mock_post.return_value = mock_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "tok"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
        ):
            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["needs_reauth"] is True


@pytest.mark.unit
class TestTestTokenRotation:
    """Cover lines 121-143, 160-161: token rotation with .env and DB persist."""

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_token_rotation_env_file_exists(self, mock_post, mock_get, client: TestClient, tmp_path):
        """When a new refresh token is received and .env file exists, it should be updated."""
        from app.config import settings

        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("ONEDRIVE_REFRESH_TOKEN=old_token\nOTHER=value\n")

        # Mock token refresh returning a new refresh token
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "brand_new_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        # Mock user info
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "displayName": "Test User",
            "userPrincipalName": "test@example.com",
        }
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "old_token"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
            patch("app.api.onedrive.os.path.join", return_value=str(env_file)),
            patch("app.api.onedrive.os.path.exists", return_value=True),
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.api.onedrive.save_setting_to_db"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_token_rotation_env_not_existing(self, mock_post, mock_get, client: TestClient):
        """Token rotation when .env doesn't exist still succeeds."""
        from app.config import settings

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "brand_new_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "displayName": "Test User",
            "userPrincipalName": "test@example.com",
        }
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "old_token"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
            patch("app.api.onedrive.os.path.exists", return_value=False),
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.api.onedrive.save_setting_to_db"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_token_rotation_env_write_failure(self, mock_post, mock_get, client: TestClient):
        """Token rotation when .env write fails (lines 142-143) still continues."""
        from app.config import settings

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "brand_new_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "displayName": "Test User",
            "userPrincipalName": "test@example.com",
        }
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "old_token"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
            patch("app.api.onedrive.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=PermissionError("Permission denied")),
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.api.onedrive.save_setting_to_db"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_token_rotation_db_persist_failure(self, mock_post, mock_get, client: TestClient):
        """Token rotation when DB persist fails (lines 160-161) still continues."""
        from app.config import settings

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "brand_new_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "displayName": "Test User",
            "userPrincipalName": "test@example.com",
        }
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "old_token"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
            patch("app.api.onedrive.os.path.exists", return_value=False),
            patch("app.database.SessionLocal", side_effect=Exception("DB error")),
        ):
            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        assert response.json()["status"] == "success"


@pytest.mark.unit
class TestTestTokenUserInfoFailed:
    """Cover lines 170-171: user info request fails."""

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_user_info_returns_non_200(self, mock_post, mock_get, client: TestClient):
        """Test when user info request fails after successful token refresh."""
        from app.config import settings

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "tok",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 401
        mock_get_resp.text = "Unauthorized"
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "tok"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
        ):
            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "401" in data["message"]


@pytest.mark.unit
class TestTokenRotationEnvAppendLine:
    """Cover the branch at line 134 where token line is not found in .env and must be appended."""

    @patch("app.api.onedrive.requests.get")
    @patch("app.api.onedrive.requests.post")
    def test_token_rotation_appends_to_env(self, mock_post, mock_get, client: TestClient, tmp_path):
        """When .env exists but doesn't have ONEDRIVE_REFRESH_TOKEN, it should append."""
        from app.config import settings

        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_KEY=value\n")

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "brand_new_token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "displayName": "Test User",
            "userPrincipalName": "test@example.com",
        }
        mock_get.return_value = mock_get_resp

        with (
            patch.object(settings, "onedrive_refresh_token", "old_token"),
            patch.object(settings, "onedrive_client_id", "cid"),
            patch.object(settings, "onedrive_client_secret", "sec"),
            patch("app.api.onedrive.os.path.join", return_value=str(env_file)),
            patch("app.api.onedrive.os.path.exists", return_value=True),
            patch("app.database.SessionLocal") as mock_sl,
            patch("app.api.onedrive.save_setting_to_db"),
            patch("app.api.onedrive.notify_settings_updated"),
        ):
            mock_sl.return_value = MagicMock()
            response = client.get("/api/onedrive/test-token")

        assert response.status_code == 200
        assert response.json()["status"] == "success"


@pytest.mark.unit
class TestSaveSettingsException:
    """Cover lines 324-326: save_onedrive_settings outer exception handler."""

    def test_save_settings_outer_exception(self, client: TestClient):
        """Trigger the outer exception handler in save_onedrive_settings."""
        with patch("app.api.onedrive.os.path.join", side_effect=Exception("Unexpected boom")):
            response = client.post(
                "/api/onedrive/save-settings",
                data={
                    "refresh_token": "test_token",
                    "client_id": "cid",
                    "client_secret": "sec",
                },
            )
        assert response.status_code == 500
        assert "Failed to save OneDrive settings" in response.json()["detail"]


@pytest.mark.unit
class TestUpdateSettingsException:
    """Cover lines 400-402: update_onedrive_settings outer exception handler."""

    def test_update_settings_outer_exception(self, client: TestClient):
        """Trigger the outer exception handler in update_onedrive_settings."""
        with patch("app.api.onedrive.save_setting_to_db", side_effect=Exception("DB crash")):
            response = client.post(
                "/api/onedrive/update-settings",
                data={
                    "refresh_token": "test_token",
                },
            )
        assert response.status_code == 500
        assert "Failed to update OneDrive settings" in response.json()["detail"]


@pytest.mark.unit
class TestGetFullConfigException:
    """Cover lines 436-438: get_onedrive_full_config exception handler."""

    def test_get_full_config_exception(self, client: TestClient):
        """Trigger the exception handler in get_onedrive_full_config."""
        from app.config import settings

        with patch.object(
            type(settings), "onedrive_client_id", property(fget=lambda self: (_ for _ in ()).throw(Exception("boom")))
        ):
            response = client.get("/api/onedrive/get-full-config")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
