"""
Tests for app/tasks/upload_to_sharepoint.py module.

Covers get_sharepoint_token, resolve_sharepoint_drive,
create_sharepoint_upload_session, upload_large_file_sharepoint,
and upload_to_sharepoint Celery task.
"""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestGetSharepointToken:
    """Tests for get_sharepoint_token function."""

    @patch("app.tasks.upload_to_sharepoint.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_refresh_token_flow(self, mock_settings, mock_msal):
        """Test token acquisition using refresh token."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "client-secret"
        mock_settings.sharepoint_refresh_token = "refresh-token"
        mock_settings.sharepoint_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "new-access-token",
        }
        mock_msal.return_value = mock_app

        token = get_sharepoint_token()
        assert token == "new-access-token"

    @patch("app.tasks.upload_to_sharepoint.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_refresh_token_updates_new_token(self, mock_settings, mock_msal):
        """Test that a new refresh token updates settings."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "client-secret"
        mock_settings.sharepoint_refresh_token = "old-refresh-token"
        mock_settings.sharepoint_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "access_token": "access-token",
            "refresh_token": "new-refresh-token",
        }
        mock_msal.return_value = mock_app

        get_sharepoint_token()
        assert mock_settings.sharepoint_refresh_token == "new-refresh-token"

    @patch("app.tasks.upload_to_sharepoint.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_refresh_token_failure(self, mock_settings, mock_msal):
        """Test error handling when refresh token fails."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "client-secret"
        mock_settings.sharepoint_refresh_token = "expired-token"
        mock_settings.sharepoint_tenant_id = "common"

        mock_app = Mock()
        mock_app.acquire_token_by_refresh_token.return_value = {
            "error": "invalid_grant",
            "error_description": "Token expired",
        }
        mock_msal.return_value = mock_app

        with pytest.raises(ValueError, match="Failed to get SharePoint access token"):
            get_sharepoint_token()

    @patch("app.tasks.upload_to_sharepoint.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_client_credentials_flow(self, mock_settings, mock_msal):
        """Test token acquisition using client credentials (org accounts)."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "client-secret"
        mock_settings.sharepoint_refresh_token = ""
        mock_settings.sharepoint_tenant_id = "org-tenant-id"

        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "access_token": "client-cred-token",
        }
        mock_msal.return_value = mock_app

        token = get_sharepoint_token()
        assert token == "client-cred-token"

    @patch("app.tasks.upload_to_sharepoint.msal.ConfidentialClientApplication")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_client_credentials_failure(self, mock_settings, mock_msal):
        """Test error handling when client credentials flow fails."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "client-secret"
        mock_settings.sharepoint_refresh_token = ""
        mock_settings.sharepoint_tenant_id = "org-tenant-id"

        mock_app = Mock()
        mock_app.acquire_token_for_client.return_value = {
            "error": "unauthorized_client",
            "error_description": "Not authorized",
        }
        mock_msal.return_value = mock_app

        with pytest.raises(ValueError, match="Failed to get SharePoint access token"):
            get_sharepoint_token()

    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_missing_client_id(self, mock_settings):
        """Test error when client ID is missing."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = ""
        mock_settings.sharepoint_client_secret = "secret"

        with pytest.raises(ValueError, match="client ID and client secret"):
            get_sharepoint_token()

    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_no_refresh_token_common_tenant(self, mock_settings):
        """Test error for common tenant without refresh token."""
        from app.tasks.upload_to_sharepoint import get_sharepoint_token

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "secret"
        mock_settings.sharepoint_refresh_token = ""
        mock_settings.sharepoint_tenant_id = "common"

        with pytest.raises(ValueError, match="either a refresh token or a non-'common' tenant ID"):
            get_sharepoint_token()


@pytest.mark.unit
class TestResolveSharepointDrive:
    """Tests for resolve_sharepoint_drive function."""

    @patch("app.tasks.upload_to_sharepoint.requests.get")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_successful_resolution(self, mock_settings, mock_get):
        """Test successful site and drive resolution."""
        from app.tasks.upload_to_sharepoint import resolve_sharepoint_drive

        mock_settings.http_request_timeout = 30

        site_resp = Mock()
        site_resp.status_code = 200
        site_resp.json.return_value = {"id": "site-id-123"}

        drives_resp = Mock()
        drives_resp.status_code = 200
        drives_resp.json.return_value = {
            "value": [
                {"id": "drive-1", "name": "Documents"},
                {"id": "drive-2", "name": "Site Assets"},
            ]
        }

        mock_get.side_effect = [site_resp, drives_resp]

        site_id, drive_id = resolve_sharepoint_drive(
            "access-token", "https://tenant.sharepoint.com/sites/mysite", "Documents"
        )

        assert site_id == "site-id-123"
        assert drive_id == "drive-1"

    @patch("app.tasks.upload_to_sharepoint.requests.get")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_library_not_found(self, mock_settings, mock_get):
        """Test error when document library is not found."""
        from app.tasks.upload_to_sharepoint import resolve_sharepoint_drive

        mock_settings.http_request_timeout = 30

        site_resp = Mock()
        site_resp.status_code = 200
        site_resp.json.return_value = {"id": "site-id-123"}

        drives_resp = Mock()
        drives_resp.status_code = 200
        drives_resp.json.return_value = {
            "value": [
                {"id": "drive-1", "name": "Documents"},
            ]
        }

        mock_get.side_effect = [site_resp, drives_resp]

        with pytest.raises(RuntimeError, match="not found on site"):
            resolve_sharepoint_drive("access-token", "https://tenant.sharepoint.com/sites/mysite", "NonExistentLibrary")

    @patch("app.tasks.upload_to_sharepoint.requests.get")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_site_resolution_failure(self, mock_settings, mock_get):
        """Test error when site resolution fails."""
        from app.tasks.upload_to_sharepoint import resolve_sharepoint_drive

        mock_settings.http_request_timeout = 30

        site_resp = Mock()
        site_resp.status_code = 404
        site_resp.text = "Site not found"

        mock_get.return_value = site_resp

        with pytest.raises(RuntimeError, match="Failed to resolve SharePoint site"):
            resolve_sharepoint_drive("access-token", "https://tenant.sharepoint.com/sites/nonexistent", "Documents")

    def test_invalid_site_url(self):
        """Test error with invalid site URL."""
        from app.tasks.upload_to_sharepoint import resolve_sharepoint_drive

        with pytest.raises(ValueError, match="Invalid SharePoint site URL"):
            resolve_sharepoint_drive("access-token", "not-a-url", "Documents")

    @patch("app.tasks.upload_to_sharepoint.requests.get")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_case_insensitive_library_match(self, mock_settings, mock_get):
        """Test that library name matching is case-insensitive."""
        from app.tasks.upload_to_sharepoint import resolve_sharepoint_drive

        mock_settings.http_request_timeout = 30

        site_resp = Mock()
        site_resp.status_code = 200
        site_resp.json.return_value = {"id": "site-id"}

        drives_resp = Mock()
        drives_resp.status_code = 200
        drives_resp.json.return_value = {
            "value": [
                {"id": "drive-1", "name": "Shared Documents"},
            ]
        }

        mock_get.side_effect = [site_resp, drives_resp]

        site_id, drive_id = resolve_sharepoint_drive(
            "access-token", "https://tenant.sharepoint.com/sites/mysite", "shared documents"
        )

        assert drive_id == "drive-1"


@pytest.mark.unit
class TestCreateSharepointUploadSession:
    """Tests for create_sharepoint_upload_session function."""

    @patch("app.tasks.upload_to_sharepoint.requests.post")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_successful_session_creation(self, mock_settings, mock_post):
        """Test successful upload session creation."""
        from app.tasks.upload_to_sharepoint import create_sharepoint_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session123"}
        mock_post.return_value = mock_response

        url = create_sharepoint_upload_session("test.pdf", "Uploads", "drive-id", "site-id", "access-token")

        assert url == "https://upload.url/session123"

    @patch("app.tasks.upload_to_sharepoint.requests.post")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_session_without_folder(self, mock_settings, mock_post):
        """Test upload session creation without folder path."""
        from app.tasks.upload_to_sharepoint import create_sharepoint_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session456"}
        mock_post.return_value = mock_response

        url = create_sharepoint_upload_session("test.pdf", None, "drive-id", "site-id", "access-token")

        assert url == "https://upload.url/session456"

    @patch("app.tasks.upload_to_sharepoint.requests.post")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_session_creation_failure(self, mock_settings, mock_post):
        """Test error handling when session creation fails."""
        from app.tasks.upload_to_sharepoint import create_sharepoint_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Access denied"
        mock_post.return_value = mock_response

        with pytest.raises(RuntimeError, match="Failed to create SharePoint upload session"):
            create_sharepoint_upload_session("test.pdf", "Uploads", "drive-id", "site-id", "access-token")

    @patch("app.tasks.upload_to_sharepoint.requests.post")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_url_encoding_special_characters(self, mock_settings, mock_post):
        """Test that special characters in folder path are URL-encoded."""
        from app.tasks.upload_to_sharepoint import create_sharepoint_upload_session

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"uploadUrl": "https://upload.url/session"}
        mock_post.return_value = mock_response

        create_sharepoint_upload_session("file with spaces.pdf", "My Documents/Uploads", "drive-id", "site-id", "token")

        call_url = mock_post.call_args[0][0]
        assert "My%20Documents" in call_url
        assert "file%20with%20spaces.pdf" in call_url


@pytest.mark.unit
class TestUploadLargeFileSharepoint:
    """Tests for upload_large_file_sharepoint function."""

    @patch("app.tasks.upload_to_sharepoint.requests.put")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_small_single_chunk_upload(self, mock_settings, mock_put, tmp_path):
        """Test uploading a file that fits in a single chunk."""
        from app.tasks.upload_to_sharepoint import upload_large_file_sharepoint

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "small.pdf"
        test_file.write_bytes(b"small content")

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "file123", "name": "small.pdf"}
        mock_put.return_value = mock_response

        result = upload_large_file_sharepoint(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_sharepoint.time.sleep")
    @patch("app.tasks.upload_to_sharepoint.requests.put")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_chunk_upload_retry_on_failure(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test retry logic when a chunk upload fails."""
        from app.tasks.upload_to_sharepoint import upload_large_file_sharepoint

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_fail = Mock()
        mock_fail.status_code = 500

        mock_success = Mock()
        mock_success.status_code = 201
        mock_success.json.return_value = {"id": "file123"}

        mock_put.side_effect = [mock_fail, mock_success]

        result = upload_large_file_sharepoint(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_sharepoint.time.sleep")
    @patch("app.tasks.upload_to_sharepoint.requests.put")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_chunk_upload_retry_on_exception(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test retry logic when an exception occurs during upload."""
        from app.tasks.upload_to_sharepoint import upload_large_file_sharepoint

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_success = Mock()
        mock_success.status_code = 201
        mock_success.json.return_value = {"id": "file123"}

        mock_put.side_effect = [Exception("Network error"), mock_success]

        result = upload_large_file_sharepoint(str(test_file), "https://upload.url/session")

        assert result["id"] == "file123"

    @patch("app.tasks.upload_to_sharepoint.time.sleep")
    @patch("app.tasks.upload_to_sharepoint.requests.put")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_all_retries_exhausted(self, mock_settings, mock_put, mock_sleep, tmp_path):
        """Test that exhausting all retries raises an exception."""
        from app.tasks.upload_to_sharepoint import upload_large_file_sharepoint

        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_fail = Mock()
        mock_fail.status_code = 500
        mock_fail.text = "Server Error"
        mock_put.return_value = mock_fail

        with pytest.raises(RuntimeError, match="Failed to upload chunk"):
            upload_large_file_sharepoint(str(test_file), "https://upload.url/session")


@pytest.mark.unit
class TestUploadToSharepoint:
    """Tests for upload_to_sharepoint Celery task."""

    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    def test_file_not_found(self, mock_log):
        """Test that missing file raises FileNotFoundError."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        with pytest.raises(FileNotFoundError):
            upload_to_sharepoint.__wrapped__("/nonexistent/file.pdf", file_id=1)

    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_missing_client_id(self, mock_settings, mock_log, tmp_path):
        """Test error when SharePoint client ID is not configured."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        mock_settings.sharepoint_client_id = ""

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with pytest.raises(ValueError, match="client ID is not configured"):
            upload_to_sharepoint.__wrapped__(str(test_file), file_id=1)

    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_missing_site_url(self, mock_settings, mock_log, tmp_path):
        """Test error when SharePoint site URL is not configured."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_site_url = ""

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with pytest.raises(ValueError, match="site URL is not configured"):
            upload_to_sharepoint.__wrapped__(str(test_file), file_id=1)

    @patch("app.tasks.upload_to_sharepoint.upload_large_file_sharepoint")
    @patch("app.tasks.upload_to_sharepoint.create_sharepoint_upload_session")
    @patch("app.tasks.upload_to_sharepoint.resolve_sharepoint_drive")
    @patch("app.tasks.upload_to_sharepoint.get_sharepoint_token")
    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_successful_upload(
        self, mock_settings, mock_log, mock_token, mock_resolve, mock_session, mock_upload, tmp_path
    ):
        """Test successful SharePoint upload."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "secret"
        mock_settings.sharepoint_refresh_token = "token"
        mock_settings.sharepoint_site_url = "https://tenant.sharepoint.com/sites/mysite"
        mock_settings.sharepoint_document_library = "Documents"
        mock_settings.sharepoint_folder_path = "Uploads"
        mock_settings.sharepoint_tenant_id = "common"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_token.return_value = "access-token"
        mock_resolve.return_value = ("site-id", "drive-id")
        mock_session.return_value = "https://upload.url/session"
        mock_upload.return_value = {"webUrl": "https://tenant.sharepoint.com/sites/mysite/test.pdf"}

        result = upload_to_sharepoint.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert "Uploads" in result["sharepoint_path"]
        assert result["web_url"] == "https://tenant.sharepoint.com/sites/mysite/test.pdf"

    @patch("app.tasks.upload_to_sharepoint.get_sharepoint_token")
    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_upload_exception_handling(self, mock_settings, mock_log, mock_token, tmp_path):
        """Test that upload errors are properly handled."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "secret"
        mock_settings.sharepoint_site_url = "https://tenant.sharepoint.com/sites/mysite"
        mock_settings.sharepoint_folder_path = "Uploads"
        mock_settings.sharepoint_document_library = "Documents"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_token.side_effect = ValueError("Token error")

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_sharepoint.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

    @patch("app.tasks.upload_to_sharepoint.upload_large_file_sharepoint")
    @patch("app.tasks.upload_to_sharepoint.create_sharepoint_upload_session")
    @patch("app.tasks.upload_to_sharepoint.resolve_sharepoint_drive")
    @patch("app.tasks.upload_to_sharepoint.get_sharepoint_token")
    @patch("app.tasks.upload_to_sharepoint.log_task_progress")
    @patch("app.tasks.upload_to_sharepoint.settings")
    def test_folder_override(
        self, mock_settings, mock_log, mock_token, mock_resolve, mock_session, mock_upload, tmp_path
    ):
        """Test that folder_override is used instead of settings."""
        from app.tasks.upload_to_sharepoint import upload_to_sharepoint

        mock_settings.sharepoint_client_id = "client-id"
        mock_settings.sharepoint_client_secret = "secret"
        mock_settings.sharepoint_refresh_token = "token"
        mock_settings.sharepoint_site_url = "https://tenant.sharepoint.com/sites/mysite"
        mock_settings.sharepoint_document_library = "Documents"
        mock_settings.sharepoint_folder_path = "DefaultFolder"
        mock_settings.sharepoint_tenant_id = "common"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_token.return_value = "access-token"
        mock_resolve.return_value = ("site-id", "drive-id")
        mock_session.return_value = "https://upload.url/session"
        mock_upload.return_value = {"webUrl": "https://example.com/test.pdf"}

        result = upload_to_sharepoint.apply(
            args=[str(test_file)], kwargs={"file_id": 1, "folder_override": "CustomFolder"}
        ).get()

        # Verify the session was created with the override folder
        mock_session.assert_called_once_with("test.pdf", "CustomFolder", "drive-id", "site-id", "access-token")
        assert result["status"] == "Completed"
