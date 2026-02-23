"""
Tests for app/api/dropbox.py module.

Covers Dropbox OAuth endpoints, settings management, and token testing.
"""

from unittest.mock import Mock, patch

import pytest
import requests


@pytest.mark.unit
class TestExchangeDropboxToken:
    """Tests for exchange_dropbox_token endpoint."""

    @patch("app.api.dropbox.exchange_oauth_token")
    def test_successful_exchange(self, mock_exchange, client):
        """Test successful OAuth token exchange."""
        mock_exchange.return_value = {
            "refresh_token": "test-refresh",
            "access_token": "test-access",
            "expires_in": 14400,
        }

        response = client.post(
            "/api/dropbox/exchange-token",
            data={
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "redirect_uri": "http://localhost/callback",
                "code": "test-auth-code",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["refresh_token"] == "test-refresh"
        assert data["access_token"] == "test-access"
        assert data["expires_in"] == 14400

    @patch("app.api.dropbox.exchange_oauth_token")
    def test_exchange_default_expiry(self, mock_exchange, client):
        """Test token exchange returns default expires_in when not provided."""
        mock_exchange.return_value = {
            "refresh_token": "test-refresh",
            "access_token": "test-access",
        }

        response = client.post(
            "/api/dropbox/exchange-token",
            data={
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "redirect_uri": "http://localhost/callback",
                "code": "test-auth-code",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expires_in"] == 14400


@pytest.mark.unit
class TestUpdateDropboxSettings:
    """Tests for update_dropbox_settings endpoint."""

    @patch("app.api.dropbox.settings")
    def test_update_all_settings(self, mock_settings, client):
        """Test updating all Dropbox settings in memory."""
        mock_settings.dropbox_refresh_token = ""
        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""
        mock_settings.dropbox_folder = ""

        response = client.post(
            "/api/dropbox/update-settings",
            data={
                "refresh_token": "new-refresh-token",
                "app_key": "new-app-key",
                "app_secret": "new-app-secret",
                "folder_path": "/Documents",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("app.api.dropbox.settings")
    def test_update_refresh_token_only(self, mock_settings, client):
        """Test updating only refresh token."""
        mock_settings.dropbox_refresh_token = ""

        response = client.post(
            "/api/dropbox/update-settings",
            data={
                "refresh_token": "new-refresh-token",
            },
        )

        assert response.status_code == 200

    @patch("app.api.dropbox.settings")
    def test_update_settings_exception(self, mock_settings, client):
        """Test that exceptions return 500 error."""
        # Make setting the attribute raise an exception
        type(mock_settings).dropbox_refresh_token = property(
            lambda self: "",
            lambda self, v: (_ for _ in ()).throw(RuntimeError("forced")),
        )

        response = client.post(
            "/api/dropbox/update-settings",
            data={"refresh_token": "token"},
        )

        assert response.status_code == 500


@pytest.mark.unit
class TestTestDropboxToken:
    """Tests for test_dropbox_token endpoint."""

    @patch("app.api.dropbox.settings")
    def test_not_configured(self, mock_settings, client):
        """Test response when Dropbox is not configured."""
        mock_settings.dropbox_refresh_token = ""
        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not fully configured" in data["message"]

    @patch("app.api.dropbox.requests.post")
    @patch("app.api.dropbox.settings")
    def test_valid_token(self, mock_settings, mock_post, client):
        """Test successful token validation."""
        mock_settings.dropbox_refresh_token = "valid-refresh-token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "email": "user@example.com",
            "name": {"display_name": "Test User"},
        }
        mock_post.return_value = mock_response

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["account"] == "user@example.com"
        assert data["account_name"] == "Test User"

    @patch("app.api.dropbox.requests.post")
    @patch("app.api.dropbox.settings")
    def test_expired_token_refreshed(self, mock_settings, mock_post, client):
        """Test that expired token triggers refresh and retry."""
        mock_settings.dropbox_refresh_token = "refresh-token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        # First call returns 401, second call (refresh) returns 200, third call returns 200
        mock_401 = Mock()
        mock_401.status_code = 401

        mock_refresh = Mock()
        mock_refresh.status_code = 200
        mock_refresh.json.return_value = {"access_token": "new-access-token"}

        mock_success = Mock()
        mock_success.status_code = 200
        mock_success.json.return_value = {
            "email": "user@example.com",
            "name": {"display_name": "Test User"},
        }

        mock_post.side_effect = [mock_401, mock_refresh, mock_success]

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    @patch("app.api.dropbox.requests.post")
    @patch("app.api.dropbox.settings")
    def test_refresh_token_expired(self, mock_settings, mock_post, client):
        """Test handling when refresh token itself is expired."""
        mock_settings.dropbox_refresh_token = "expired-refresh"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        # First call returns 401, refresh also fails
        mock_401 = Mock()
        mock_401.status_code = 401

        mock_refresh_fail = Mock()
        mock_refresh_fail.status_code = 400
        mock_refresh_fail.text = "invalid_grant"

        mock_post.side_effect = [mock_401, mock_refresh_fail]

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["needs_reauth"] is True

    @patch("app.api.dropbox.requests.post")
    @patch("app.api.dropbox.settings")
    def test_token_validation_failure(self, mock_settings, mock_post, client):
        """Test handling non-401, non-200 response."""
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    @patch("app.api.dropbox.requests.post")
    @patch("app.api.dropbox.settings")
    def test_connection_error(self, mock_settings, mock_post, client):
        """Test handling of connection exceptions."""
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        mock_post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        response = client.get("/api/dropbox/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Connection error" in data["message"]


@pytest.mark.unit
class TestSaveDropboxSettings:
    """Tests for save_dropbox_settings endpoint."""

    @patch("app.api.dropbox.settings")
    def test_save_settings_env_not_found(self, mock_settings, client):
        """Test that missing .env file is non-fatal — DB write still succeeds."""
        with patch("os.path.exists", return_value=False):
            response = client.post(
                "/api/dropbox/save-settings",
                data={"refresh_token": "test-token"},
            )

        # .env write is best-effort; endpoint should still succeed via DB write
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @patch("app.api.dropbox.settings")
    def test_save_settings_success(self, mock_settings, client, tmp_path):
        """Test successful save of Dropbox settings to .env file."""
        mock_settings.dropbox_refresh_token = ""
        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""
        mock_settings.dropbox_folder = ""

        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("DROPBOX_REFRESH_TOKEN=old_token\nOTHER_VAR=value\n")

        with (
            patch("app.api.dropbox.os.path.join", return_value=str(env_file)),
            patch("app.api.dropbox.os.path.exists", return_value=True),
            patch("app.api.dropbox.os.path.dirname", return_value=str(tmp_path)),
        ):
            response = client.post(
                "/api/dropbox/save-settings",
                data={
                    "refresh_token": "new-token",
                    "app_key": "new-key",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify the .env file was updated
        content = env_file.read_text()
        assert "new-token" in content

    @patch("app.api.dropbox.settings")
    def test_save_settings_with_all_optional_fields(
        self, mock_settings, client, tmp_path
    ):
        """Test saving all Dropbox settings including optional fields."""
        mock_settings.dropbox_refresh_token = ""
        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""
        mock_settings.dropbox_folder = ""

        # Create a temporary .env file with commented lines
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# DROPBOX_REFRESH_TOKEN=old_token\n"
            "# DROPBOX_APP_KEY=old_key\n"
            "# DROPBOX_APP_SECRET=old_secret\n"
            "OTHER_VAR=value\n"
        )

        with (
            patch("app.api.dropbox.os.path.join", return_value=str(env_file)),
            patch("app.api.dropbox.os.path.exists", return_value=True),
            patch("app.api.dropbox.os.path.dirname", return_value=str(tmp_path)),
        ):
            response = client.post(
                "/api/dropbox/save-settings",
                data={
                    "refresh_token": "new-token",
                    "app_key": "new-key",
                    "app_secret": "new-secret",
                    "folder_path": "/Documents",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        # Verify all settings were updated in the file
        content = env_file.read_text()
        assert "DROPBOX_REFRESH_TOKEN=new-token" in content
        assert "DROPBOX_APP_KEY=new-key" in content
        assert "DROPBOX_APP_SECRET=new-secret" in content
        assert "DROPBOX_FOLDER=/Documents" in content

    @patch("app.api.dropbox.settings")
    def test_save_settings_adds_missing_keys(self, mock_settings, client, tmp_path):
        """Test that missing keys are added to .env file."""
        mock_settings.dropbox_refresh_token = ""
        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""
        mock_settings.dropbox_folder = ""

        # Create a temporary .env file without Dropbox settings
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_VAR=value\nANOTHER_VAR=test\n")

        with (
            patch("app.api.dropbox.os.path.join", return_value=str(env_file)),
            patch("app.api.dropbox.os.path.exists", return_value=True),
            patch("app.api.dropbox.os.path.dirname", return_value=str(tmp_path)),
        ):
            response = client.post(
                "/api/dropbox/save-settings",
                data={
                    "refresh_token": "new-token",
                    "app_key": "new-key",
                    "folder_path": "/Shared",
                },
            )

        assert response.status_code == 200

        # Verify new keys were added
        content = env_file.read_text()
        assert "DROPBOX_REFRESH_TOKEN=new-token" in content
        assert "DROPBOX_APP_KEY=new-key" in content
        assert "DROPBOX_FOLDER=/Shared" in content
        # Original lines should be preserved
        assert "OTHER_VAR=value" in content
        assert "ANOTHER_VAR=test" in content

    @patch("app.api.dropbox.settings")
    def test_save_settings_io_error(self, mock_settings, client, tmp_path):
        """Test that I/O errors on .env write are non-fatal — DB write still succeeds."""
        mock_settings.dropbox_refresh_token = ""

        # Create a temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("DROPBOX_REFRESH_TOKEN=old_token\n")

        with (
            patch("app.api.dropbox.os.path.join", return_value=str(env_file)),
            patch("app.api.dropbox.os.path.exists", return_value=True),
            patch("app.api.dropbox.os.path.dirname", return_value=str(tmp_path)),
            patch("builtins.open", side_effect=IOError("Permission denied")),
        ):
            response = client.post(
                "/api/dropbox/save-settings",
                data={"refresh_token": "new-token"},
            )

        # .env write is best-effort; endpoint should still succeed via DB write
        assert response.status_code == 200
        assert response.json()["status"] == "success"
