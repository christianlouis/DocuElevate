"""
Tests for app/tasks/upload_to_onedrive.py module.

Covers get_onedrive_token, create_upload_session, upload_large_file,
and upload_to_onedrive Celery task.
"""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestGetOnedriveToken:
    """Tests for get_onedrive_token function."""

    @patch("app.tasks.upload_to_onedrive.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_refresh_token_flow(self, mock_settings, mock_msal):
        """Test token acquisition using refresh token."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "client-secret"
        mock_settings.onedrive_refresh_token = "refresh-token"
        mock_settings.onedrive_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "new-access-token",
        }
        mock_msal.return_value = mock_app

        token = get_onedrive_token()
        assert token == "new-access-token"

    @patch("app.tasks.upload_to_onedrive.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_refresh_token_updates_new_token(self, mock_settings, mock_msal):
        """Test that a new refresh token updates settings."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "client-secret"
        mock_settings.onedrive_refresh_token = "old-refresh-token"
        mock_settings.onedrive_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "access-token",
            "refresh_token": "new-refresh-token",
        }
        mock_msal.return_value = mock_app

        get_onedrive_token()
        assert mock_settings.onedrive_refresh_token == "new-refresh-token"

    @patch("app.tasks.upload_to_onedrive.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_refresh_token_failure(self, mock_settings, mock_msal):
        """Test error handling when refresh token fails."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "client-secret"
        mock_settings.onedrive_refresh_token = "expired-token"
        mock_settings.onedrive_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }
        mock_msal.return_value = mock_app

        with pytest.raises(ValueError, match="Failed to get access token"):
            get_onedrive_token()

    @patch("app.tasks.upload_to_onedrive.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_client_credentials_flow(self, mock_settings, mock_msal):
        """Test token acquisition using client credentials (org accounts)."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "client-secret"
        mock_settings.onedrive_refresh_token = ""
        mock_settings.onedrive_tenant_id = "org-tenant-id"

        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "client-cred-token",
        }
        mock_msal.return_value = mock_app

        token = get_onedrive_token()
        assert token == "client-cred-token"

    @patch("app.tasks.upload_to_onedrive.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_client_credentials_failure(self, mock_settings, mock_msal):
        """Test error handling when client credentials flow fails."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "client-secret"
        mock_settings.onedrive_refresh_token = ""
        mock_settings.onedrive_tenant_id = "org-tenant-id"

        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "unauthorized_client",
            "error_description": "Not authorized",
        }
        mock_msal.return_value = mock_app

        with pytest.raises(ValueError, match="Failed to get access token"):
            get_onedrive_token()

    @patch("app.tasks.upload_to_onedrive.settings")
    def test_missing_client_id(self, mock_settings):
        """Test error when client ID is missing."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = ""
        mock_settings.onedrive_client_secret = "secret"

        with pytest.raises(ValueError, match="client ID and client secret"):
            get_onedrive_token()

    @patch("app.tasks.upload_to_onedrive.settings")
    def test_no_refresh_token_personal_account(self, mock_settings):
        """Test error for personal account without refresh token."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "secret"
        mock_settings.onedrive_refresh_token = ""
        mock_settings.onedrive_tenant_id = "common"

        with pytest.raises(ValueError, match="ONEDRIVE_REFRESH_TOKEN must be configured"):
            get_onedrive_token()

    @patch("app.tasks.upload_to_onedrive.settings")
    def test_no_refresh_token_no_tenant(self, mock_settings):
        """Test error when no refresh token and no specific tenant."""
        from app.tasks.upload_to_onedrive import get_onedrive_token

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "secret"
        mock_settings.onedrive_refresh_token = ""
        mock_settings.onedrive_tenant_id = ""

        with pytest.raises(ValueError, match="ONEDRIVE_REFRESH_TOKEN must be configured"):
            get_onedrive_token()


@pytest.mark.unit
class TestCreateUploadSession:
    """Tests for create_upload_session function."""

    @patch("app.tasks.upload_to_onedrive.requests.post")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_successful_session_creation(self, mock_settings, mock_post):
        """Test successful upload session creation."""
        from app.tasks.upload_to_onedrive import create_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session123"}
        mock_post.return_value = mock_response

        url = create_upload_session("test.pdf", "Documents/Uploads", "access-token")

        assert url == "https://upload.url/session123"

    @patch("app.tasks.upload_to_onedrive.requests.post")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_session_creation_without_folder(self, mock_settings, mock_post):
        """Test upload session creation without folder path."""
        from app.tasks.upload_to_onedrive import create_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session456"}
        mock_post.return_value = mock_response

        url = create_upload_session("test.pdf", None, "access-token")

        assert url == "https://upload.url/session456"

    @patch("app.tasks.upload_to_onedrive.requests.post")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_session_creation_failure(self, mock_settings, mock_post):
        """Test error handling when session creation fails."""
        from app.tasks.upload_to_onedrive import create_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Access denied"
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Failed to create upload session"):
            create_upload_session("test.pdf", "Documents", "access-token")

    @patch("app.tasks.upload_to_onedrive.requests.post")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_url_encoding_of_special_characters(self, mock_settings, mock_post):
        """Test that special characters in folder path are URL-encoded."""
        from app.tasks.upload_to_onedrive import create_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session"}
        mock_post.return_value = mock_response

        create_upload_session("file with spaces.pdf", "My Documents/Uploads", "access-token")

        # Verify the URL was constructed with encoded components
        call_url = mock_post.call_args[0][0]
        assert "My%20Documents" in call_url
        assert "file%20with%20spaces.pdf" in call_url


@pytest.mark.unit
class TestUploadLargeFile:
    """Tests for upload_large_file function."""

    @patch("app.tasks.upload_to_onedrive.requests.put")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_small_single_chunk_upload(self, mock_settings, mock_put, tmp_path):
        """Test uploading a file that fits in a single chunk."""
        from app.tasks.upload_to_onedrive import upload_large_file

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "small.pdf"
        test_file.write_bytes(b"small content")

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "file123", "name": "small.pdf"}
        mock_put.return_value = mock_response

        result = upload_large_file(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_onedrive.time.sleep")
    @patch("app.tasks.upload_to_onedrive.requests.put")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_chunk_upload_retry_on_failure(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test retry logic when a chunk upload fails."""
        from app.tasks.upload_to_onedrive import upload_large_file

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        # First attempt fails, second succeeds
        mock_fail = Mock()
        mock_fail.status_code = 500

        mock_success = Mock()
        mock_success.status_code = 201
        mock_success.json.return_value = {"id": "file123"}

        mock_put.side_effect = [mock_fail, mock_success]

        result = upload_large_file(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_onedrive.time.sleep")
    @patch("app.tasks.upload_to_onedrive.requests.put")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_chunk_upload_retry_on_exception(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test retry logic when an exception occurs during upload."""
        from app.tasks.upload_to_onedrive import upload_large_file

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_success = Mock()
        mock_success.status_code = 201
        mock_success.json.return_value = {"id": "file123"}

        mock_put.side_effect = [Exception("Network error"), mock_success]

        result = upload_large_file(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_onedrive.time.sleep")
    @patch("app.tasks.upload_to_onedrive.requests.put")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_all_retries_exhausted(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test that exhausting all retries raises an exception."""
        from app.tasks.upload_to_onedrive import upload_large_file

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_fail.text = "Server Error"
        mock_put.return_value = mock_fail

        with pytest.raises(Exception, match="Failed to upload chunk"):
            upload_large_file(str(test_file), "https://upload.url/session")


@pytest.mark.unit
class TestUploadToOnedrive:
    """Tests for upload_to_onedrive Celery task."""

    @patch("app.tasks.upload_to_onedrive.log_task_progress")
    def test_file_not_found(self, mock_log):
        """Test that missing file raises FileNotFoundError."""
        from app.tasks.upload_to_onedrive import upload_to_onedrive

        with pytest.raises(FileNotFoundError):
            upload_to_onedrive.__wrapped__("/nonexistent/file.pdf", file_id=1)

    @patch("app.tasks.upload_to_onedrive.log_task_progress")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_missing_client_id(self, mock_settings, mock_log, tmp_path):
        """Test error when OneDrive client ID is not configured."""
        from app.tasks.upload_to_onedrive import upload_to_onedrive

        mock_settings.onedrive_client_id = ""

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with pytest.raises(ValueError, match="client ID is not configured"):
            upload_to_onedrive.__wrapped__(str(test_file), file_id=1)

    @patch("app.tasks.upload_to_onedrive.upload_large_file")
    @patch("app.tasks.upload_to_onedrive.create_upload_session")
    @patch("app.tasks.upload_to_onedrive.get_onedrive_token")
    @patch("app.tasks.upload_to_onedrive.log_task_progress")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_successful_upload(self, mock_settings, mock_log, mock_token, mock_session, mock_upload, tmp_path):
        """Test successful OneDrive upload."""
        from app.tasks.upload_to_onedrive import upload_to_onedrive

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "secret"
        mock_settings.onedrive_refresh_token = "token"
        mock_settings.onedrive_folder_path = "Documents"
        mock_settings.onedrive_tenant_id = "common"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_token.return_value = "access-token"
        mock_session.return_value = "https://upload.url/session"
        mock_upload.return_value = {"webUrl": "https://onedrive.live.com/test.pdf"}

        result = upload_to_onedrive.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert "Documents" in result["onedrive_path"]
        assert result["web_url"] == "https://onedrive.live.com/test.pdf"

    @patch("app.tasks.upload_to_onedrive.get_onedrive_token")
    @patch("app.tasks.upload_to_onedrive.log_task_progress")
    @patch("app.tasks.upload_to_onedrive.settings")
    def test_upload_exception_handling(self, mock_settings, mock_log, mock_token, tmp_path):
        """Test that upload errors are properly handled."""
        from app.tasks.upload_to_onedrive import upload_to_onedrive

        mock_settings.onedrive_client_id = "client-id"
        mock_settings.onedrive_client_secret = "secret"
        mock_settings.onedrive_folder_path = "Documents"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_token.side_effect = ValueError("Token error")

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_onedrive.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()
