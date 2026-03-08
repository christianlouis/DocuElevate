"""
Final coverage tests for app/api/google_drive.py.

Targets the remaining uncovered branches from the 97.03% baseline:
  - 88->93  : update_google_drive_settings — refresh_token is empty/falsy
  - 180->191: test_google_drive_token — OAuth credentials have no expiry
  - 214     : test_google_drive_token — generic connection error (not token-related)
  - 302->306: get_google_drive_token_info — credentials already valid (no refresh)
  - 307->318: get_google_drive_token_info — credentials have no expiry
  - 395->397: save_dropbox_settings — refresh_token falsy inside use_oauth block
  - 449->451: save_dropbox_settings — refresh_token falsy in in-memory update
  - 468->470: save_dropbox_settings — folder_id falsy in db-persist block
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
class TestUpdateSettingsEmptyRefreshToken:
    """Cover branch 88->93: refresh_token falsy in update_google_drive_settings."""

    @pytest.mark.asyncio
    async def test_update_settings_empty_refresh_token(self):
        """Call update_google_drive_settings directly with empty refresh_token (branch 88->93)."""
        from unittest.mock import MagicMock

        from starlette.requests import Request as StarletteRequest

        from app.api.google_drive import update_google_drive_settings

        mock_request = MagicMock(spec=StarletteRequest)
        mock_request.session = {}
        mock_db = MagicMock()

        with patch("app.api.google_drive.save_setting_to_db"):
            with patch("app.api.google_drive.notify_settings_updated"):
                result = await update_google_drive_settings(
                    request=mock_request,
                    refresh_token="",  # falsy → branch 88->93
                    client_id="cid",
                    client_secret=None,
                    folder_id=None,
                    use_oauth="true",
                    db=mock_db,
                )
        assert result["status"] == "success"


@pytest.mark.unit
class TestTestTokenOAuthNoBranchExpiry:
    """Cover branches 180->191 and line 214 in test_google_drive_token."""

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_no_expiry_on_credentials(self, mock_settings, client: TestClient):
        """OAuth token test where credentials.expiry is None (branch 180->191)."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "refresh")

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expiry = None  # no expiry → branch 180->191

        mock_service = MagicMock()
        mock_service.about.return_value.get.return_value.execute.return_value = {
            "user": {"emailAddress": "user@example.com"}
        }

        with (
            patch("app.tasks.upload_to_google_drive.get_drive_service_oauth", return_value=mock_service),
            patch("google.oauth2.credentials.Credentials", return_value=mock_creds),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["auth_type"] == "oauth"

    @patch("app.api.google_drive.settings")
    def test_test_token_oauth_generic_connection_error(self, mock_settings, client: TestClient):
        """OAuth token test raises a generic error without 'token' or 'invalid_grant' (line 214)."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "refresh")

        # Error message deliberately avoids "token" and "invalid_grant"
        with patch(
            "app.tasks.upload_to_google_drive.get_drive_service_oauth",
            side_effect=Exception("Connection refused by remote host"),
        ):
            response = client.get("/api/google-drive/test-token")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Connection error" in data["message"]


@pytest.mark.unit
class TestGetTokenInfoCredentialsBranches:
    """Cover branches 302->306 and 307->318 in get_google_drive_token_info."""

    @patch("app.api.google_drive.settings")
    def test_get_token_info_credentials_already_valid(self, mock_settings, client: TestClient):
        """credentials.valid is True — no refresh needed (branch 302->306)."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "refresh")

        mock_creds = MagicMock()
        mock_creds.valid = True  # already valid → skip refresh (branch 302->306)
        mock_creds.expiry = datetime.now() + timedelta(hours=1)
        mock_creds.token = "access_token_value"

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds):
            response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["access_token"] == "access_token_value"

    @patch("app.api.google_drive.settings")
    def test_get_token_info_credentials_no_expiry(self, mock_settings, client: TestClient):
        """credentials.expiry is None — expiration_info stays empty (branch 307->318)."""
        type(mock_settings).google_drive_use_oauth = property(lambda self: True)
        type(mock_settings).google_drive_client_id = property(lambda self: "client_id")
        type(mock_settings).google_drive_client_secret = property(lambda self: "secret")
        type(mock_settings).google_drive_refresh_token = property(lambda self: "refresh")

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expiry = None  # no expiry → branch 307->318
        mock_creds.token = "access_token_value"

        with patch("google.oauth2.credentials.Credentials", return_value=mock_creds):
            response = client.get("/api/google-drive/get-token-info")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["token_info"] == {}


@pytest.mark.unit
class TestSaveGoogleDriveSettingsFalsyFields:
    """Cover branches 395->397, 449->451, 468->470 in save_dropbox_settings.

    Note: the Google Drive save endpoint is named save_dropbox_settings in the
    source (app/api/google_drive.py) due to an existing naming inconsistency.
    """

    @patch("app.api.google_drive.settings")
    @patch("os.path.exists", return_value=False)
    @pytest.mark.asyncio
    async def test_save_settings_empty_refresh_token_with_oauth(self, _mock_exists, mock_settings):
        """use_oauth=true, refresh_token="" — skips token blocks (branches 395->397 and 449->451)."""
        from unittest.mock import MagicMock

        from starlette.requests import Request as StarletteRequest

        from app.api.google_drive import save_dropbox_settings

        mock_request = MagicMock(spec=StarletteRequest)
        mock_request.session = {}
        mock_db = MagicMock()

        with patch("app.api.google_drive.save_setting_to_db"):
            with patch("app.api.google_drive.notify_settings_updated"):
                result = await save_dropbox_settings(
                    request=mock_request,
                    refresh_token="",  # falsy → branches 395->397 and 449->451
                    client_id="cid",
                    client_secret=None,
                    folder_id=None,
                    use_oauth="true",
                    db=mock_db,
                )
        assert result["status"] == "success"

    @patch("app.api.google_drive.settings")
    @patch("os.path.exists", return_value=False)
    def test_save_settings_no_folder_id(self, _mock_exists, mock_settings, client: TestClient):
        """folder_id not supplied — skips folder_id db-persist block (branch 468->470)."""
        response = client.post(
            "/api/google-drive/save-settings",
            data={
                "refresh_token": "some_refresh_token",
                # no folder_id → branch 468->470
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
