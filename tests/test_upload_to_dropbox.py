"""
Tests for app/tasks/upload_to_dropbox.py module.

Covers _validate_dropbox_settings, get_dropbox_access_token, get_dropbox_client,
and upload_to_dropbox Celery task.
"""

from unittest.mock import Mock, patch

import pytest
from dropbox.exceptions import ApiError, AuthError


@pytest.mark.unit
class TestValidateDropboxSettings:
    """Tests for _validate_dropbox_settings function."""

    def test_all_settings_present(self):
        """Test validation passes when all settings are present."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = "token"
            mock_settings.dropbox_app_key = "key"
            mock_settings.dropbox_app_secret = "secret"

            assert _validate_dropbox_settings() is True

    def test_missing_refresh_token(self):
        """Test validation fails when refresh token is missing."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = ""
            mock_settings.dropbox_app_key = "key"
            mock_settings.dropbox_app_secret = "secret"

            assert _validate_dropbox_settings() is False

    def test_missing_app_key(self):
        """Test validation fails when app key is missing."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = "token"
            mock_settings.dropbox_app_key = ""
            mock_settings.dropbox_app_secret = "secret"

            assert _validate_dropbox_settings() is False

    def test_missing_app_secret(self):
        """Test validation fails when app secret is missing."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = "token"
            mock_settings.dropbox_app_key = "key"
            mock_settings.dropbox_app_secret = ""

            assert _validate_dropbox_settings() is False

    def test_missing_all_settings(self):
        """Test validation fails when all settings are missing."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_app_key = None
            mock_settings.dropbox_app_secret = None

            assert _validate_dropbox_settings() is False


@pytest.mark.unit
class TestGetDropboxAccessToken:
    """Tests for get_dropbox_access_token function."""

    @patch("app.tasks.upload_to_dropbox.requests.post")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_successful_refresh(self, mock_settings, mock_post):
        """Test successful token refresh."""
        from app.tasks.upload_to_dropbox import get_dropbox_access_token

        mock_settings.dropbox_refresh_token = "refresh-token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new-access-token"}
        mock_post.return_value = mock_response

        token = get_dropbox_access_token()
        assert token == "new-access-token"

    @patch("app.tasks.upload_to_dropbox.requests.post")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_refresh_failure_raises(self, mock_settings, mock_post):
        """Test that failed token refresh raises exception."""
        from app.tasks.upload_to_dropbox import get_dropbox_access_token

        mock_settings.dropbox_refresh_token = "refresh-token"
        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Failed to refresh"):
            get_dropbox_access_token()

    def test_returns_none_when_settings_missing(self):
        """Test returns None when settings are not configured."""
        from app.tasks.upload_to_dropbox import get_dropbox_access_token

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_app_key = None
            mock_settings.dropbox_app_secret = None

            result = get_dropbox_access_token()
            assert result is None


@pytest.mark.unit
class TestGetDropboxClient:
    """Tests for get_dropbox_client function."""

    @patch("app.tasks.upload_to_dropbox.dropbox.Dropbox")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_successful_client_creation(self, mock_settings, mock_dropbox):
        """Test successful Dropbox client creation."""
        from app.tasks.upload_to_dropbox import get_dropbox_client

        mock_settings.dropbox_app_key = "app-key"
        mock_settings.dropbox_app_secret = "app-secret"
        mock_settings.dropbox_refresh_token = "refresh-token"

        mock_instance = Mock()
        mock_dropbox.return_value = mock_instance

        client = get_dropbox_client()
        assert client == mock_instance
        mock_instance.users_get_current_account.assert_called_once()

    @patch("app.tasks.upload_to_dropbox.settings")
    def test_missing_app_key_raises(self, mock_settings):
        """Test that missing app key raises ValueError."""
        from app.tasks.upload_to_dropbox import get_dropbox_client

        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"

        with pytest.raises(ValueError, match="app key or app secret"):
            get_dropbox_client()

    @patch("app.tasks.upload_to_dropbox.settings")
    def test_missing_refresh_token_raises(self, mock_settings):
        """Test that missing refresh token raises ValueError."""
        from app.tasks.upload_to_dropbox import get_dropbox_client

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = ""

        with pytest.raises(ValueError, match="refresh token"):
            get_dropbox_client()

    @patch("app.tasks.upload_to_dropbox.dropbox.Dropbox")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_auth_error_propagated(self, mock_settings, mock_dropbox):
        """Test that AuthError is propagated."""
        from app.tasks.upload_to_dropbox import get_dropbox_client

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"

        mock_instance = Mock()
        mock_instance.users_get_current_account.side_effect = AuthError("req-id", "Invalid token")
        mock_dropbox.return_value = mock_instance

        with pytest.raises(AuthError):
            get_dropbox_client()


@pytest.mark.unit
class TestUploadToDropbox:
    """Tests for upload_to_dropbox Celery task."""

    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    def test_file_not_found(self, mock_log):
        """Test that missing file raises FileNotFoundError."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        with pytest.raises(FileNotFoundError):
            upload_to_dropbox.__wrapped__("/nonexistent/file.pdf", file_id=1)

    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_skipped_when_not_configured(self, mock_settings, mock_log, tmp_path):
        """Test upload skipped when Dropbox not configured."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = ""
        mock_settings.dropbox_app_secret = ""
        mock_settings.dropbox_refresh_token = ""

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        result = upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Skipped"

    @patch("app.tasks.upload_to_dropbox.get_unique_filename")
    @patch("app.tasks.upload_to_dropbox.extract_remote_path")
    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_successful_small_file_upload(
        self, mock_settings, mock_log, mock_client, mock_extract, mock_unique, tmp_path
    ):
        """Test successful upload of a small file."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"small file content")

        mock_dbx = Mock()
        mock_client.return_value = mock_dbx
        mock_extract.return_value = "uploads/test.pdf"
        mock_unique.return_value = "/uploads/test.pdf"

        result = upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert result["file_path"] == str(test_file)
        mock_dbx.files_upload.assert_called_once()

    @patch("app.tasks.upload_to_dropbox.get_unique_filename")
    @patch("app.tasks.upload_to_dropbox.extract_remote_path")
    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_large_file_chunked_upload(self, mock_settings, mock_log, mock_client, mock_extract, mock_unique, tmp_path):
        """Test chunked upload for large files (>10MB)."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        # Create a file larger than 10MB threshold
        test_file = tmp_path / "large.pdf"
        test_file.write_bytes(b"x" * (11 * 1024 * 1024))

        mock_dbx = Mock()
        mock_client.return_value = mock_dbx
        mock_extract.return_value = "uploads/large.pdf"
        mock_unique.return_value = "/uploads/large.pdf"

        mock_session = Mock()
        mock_session.session_id = "session-123"
        mock_dbx.files_upload_session_start.return_value = mock_session

        result = upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        mock_dbx.files_upload_session_start.assert_called_once()

    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_auth_error_handling(self, mock_settings, mock_log, mock_client, tmp_path):
        """Test AuthError during upload is caught and re-raised."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_client.side_effect = AuthError("req-id", "Invalid token")

        with pytest.raises(Exception, match="Authentication failed"):
            upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

    @patch("app.tasks.upload_to_dropbox.get_dropbox_client")
    @patch("app.tasks.upload_to_dropbox.log_task_progress")
    @patch("app.tasks.upload_to_dropbox.settings")
    def test_api_error_handling(self, mock_settings, mock_log, mock_client, tmp_path):
        """Test ApiError during upload is caught and re-raised."""
        from app.tasks.upload_to_dropbox import upload_to_dropbox

        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"
        mock_settings.dropbox_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_error = Mock()
        mock_error.is_path.return_value = False
        mock_client.side_effect = ApiError("req-id", mock_error, "user msg", "header")

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_dropbox.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()
