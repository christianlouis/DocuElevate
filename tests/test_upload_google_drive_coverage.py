"""Comprehensive tests for app/tasks/upload_to_google_drive.py to improve coverage."""

import json
import os
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest


@pytest.mark.unit
class TestGetDriveServiceOAuth:
    """Tests for get_drive_service_oauth function."""

    @patch("app.tasks.upload_to_google_drive.build")
    @patch("app.tasks.upload_to_google_drive.Request")
    @patch("app.tasks.upload_to_google_drive.OAuthCredentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_successful_oauth_service(self, mock_settings, mock_creds_cls, mock_request, mock_build):
        """Test successful OAuth service creation."""
        from app.tasks.upload_to_google_drive import get_drive_service_oauth

        mock_settings.google_drive_client_id = "client_id"
        mock_settings.google_drive_client_secret = "client_secret"
        mock_settings.google_drive_refresh_token = "refresh_token"

        mock_creds = MagicMock()
        mock_creds_cls.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = get_drive_service_oauth()
        assert result == mock_service
        mock_creds.refresh.assert_called_once()

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_when_missing_client_id(self, mock_settings):
        """Test returns None when client_id is missing."""
        from app.tasks.upload_to_google_drive import get_drive_service_oauth

        mock_settings.google_drive_client_id = None
        mock_settings.google_drive_client_secret = "secret"
        mock_settings.google_drive_refresh_token = "token"

        result = get_drive_service_oauth()
        assert result is None

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_when_missing_secret(self, mock_settings):
        """Test returns None when client_secret is missing."""
        from app.tasks.upload_to_google_drive import get_drive_service_oauth

        mock_settings.google_drive_client_id = "id"
        mock_settings.google_drive_client_secret = None
        mock_settings.google_drive_refresh_token = "token"

        result = get_drive_service_oauth()
        assert result is None

    @patch("app.tasks.upload_to_google_drive.OAuthCredentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_refresh_error_raises(self, mock_settings, mock_creds_cls):
        """Test RefreshError is re-raised."""
        from google.auth.exceptions import RefreshError

        from app.tasks.upload_to_google_drive import get_drive_service_oauth

        mock_settings.google_drive_client_id = "id"
        mock_settings.google_drive_client_secret = "secret"
        mock_settings.google_drive_refresh_token = "token"

        mock_creds = MagicMock()
        mock_creds.refresh.side_effect = RefreshError("Token expired")
        mock_creds_cls.return_value = mock_creds

        with pytest.raises(RefreshError):
            get_drive_service_oauth()

    @patch("app.tasks.upload_to_google_drive.OAuthCredentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_general_exception_returns_none(self, mock_settings, mock_creds_cls):
        """Test general exception returns None."""
        from app.tasks.upload_to_google_drive import get_drive_service_oauth

        mock_settings.google_drive_client_id = "id"
        mock_settings.google_drive_client_secret = "secret"
        mock_settings.google_drive_refresh_token = "token"

        mock_creds_cls.side_effect = Exception("Unexpected error")

        result = get_drive_service_oauth()
        assert result is None


@pytest.mark.unit
class TestGetGoogleDriveService:
    """Tests for get_google_drive_service function."""

    @patch("app.tasks.upload_to_google_drive.get_drive_service_oauth")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_uses_oauth_when_configured(self, mock_settings, mock_oauth):
        """Test uses OAuth when google_drive_use_oauth is True."""
        from app.tasks.upload_to_google_drive import get_google_drive_service

        mock_settings.google_drive_use_oauth = True
        mock_service = MagicMock()
        mock_oauth.return_value = mock_service

        result = get_google_drive_service()
        assert result == mock_service
        mock_oauth.assert_called_once()

    @patch("app.tasks.upload_to_google_drive.build")
    @patch("app.tasks.upload_to_google_drive.Credentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_uses_service_account(self, mock_settings, mock_creds_cls, mock_build):
        """Test uses service account when OAuth not enabled."""
        from app.tasks.upload_to_google_drive import get_google_drive_service

        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_delegate_to = None

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_info.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = get_google_drive_service()
        assert result == mock_service

    @patch("app.tasks.upload_to_google_drive.build")
    @patch("app.tasks.upload_to_google_drive.Credentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_delegates_to_user(self, mock_settings, mock_creds_cls, mock_build):
        """Test delegates to user when configured."""
        from app.tasks.upload_to_google_drive import get_google_drive_service

        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_delegate_to = "user@example.com"

        mock_creds = MagicMock()
        mock_creds_cls.from_service_account_info.return_value = mock_creds

        get_google_drive_service()
        mock_creds.with_subject.assert_called_once_with("user@example.com")

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_when_no_credentials(self, mock_settings):
        """Test returns None when no credentials JSON configured."""
        from app.tasks.upload_to_google_drive import get_google_drive_service

        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = None

        result = get_google_drive_service()
        assert result is None

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_on_exception(self, mock_settings):
        """Test returns None on exception."""
        from app.tasks.upload_to_google_drive import get_google_drive_service

        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = "invalid json"

        result = get_google_drive_service()
        assert result is None


@pytest.mark.unit
class TestExtractMetadataFromFile:
    """Tests for extract_metadata_from_file function."""

    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_returns_empty_when_no_json(self, mock_exists):
        """Test returns empty dict when no JSON metadata file."""
        from app.tasks.upload_to_google_drive import extract_metadata_from_file

        mock_exists.return_value = False
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result == {}

    @patch("builtins.open", mock_open(read_data='{"document_type": "invoice"}'))
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_loads_metadata(self, mock_exists):
        """Test loads metadata from JSON file."""
        from app.tasks.upload_to_google_drive import extract_metadata_from_file

        mock_exists.return_value = True
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result["document_type"] == "invoice"

    @patch("builtins.open", side_effect=Exception("Read error"))
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_returns_empty_on_read_error(self, mock_exists, mock_file):
        """Test returns empty dict on read error."""
        from app.tasks.upload_to_google_drive import extract_metadata_from_file

        mock_exists.return_value = True
        result = extract_metadata_from_file("/tmp/test.pdf")
        assert result == {}


@pytest.mark.unit
class TestTruncatePropertyValue:
    """Tests for truncate_property_value function."""

    def test_returns_value_under_limit(self):
        """Test returns original value when under limit."""
        from app.tasks.upload_to_google_drive import truncate_property_value

        result = truncate_property_value("key", "short value")
        assert result == "short value"

    def test_truncates_long_value(self):
        """Test truncates value when over limit."""
        from app.tasks.upload_to_google_drive import truncate_property_value

        long_value = "a" * 200
        result = truncate_property_value("key", long_value, max_bytes=50)
        assert len(result.encode("utf-8")) <= 50
        assert result.endswith("...")

    def test_handles_non_string_value(self):
        """Test handles non-string value by converting to string."""
        from app.tasks.upload_to_google_drive import truncate_property_value

        result = truncate_property_value("key", 12345)
        assert result == "12345"

    def test_handles_unicode(self):
        """Test handles unicode characters properly."""
        from app.tasks.upload_to_google_drive import truncate_property_value

        result = truncate_property_value("key", "Hello 🌍", max_bytes=200)
        assert "Hello" in result


@pytest.mark.unit
class TestUploadToGoogleDriveTask:
    """Tests for upload_to_google_drive Celery task."""

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_file_not_found_raises(self, mock_exists, mock_log):
        """Test raises FileNotFoundError when file doesn't exist."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = False
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(FileNotFoundError):
            upload_to_google_drive(mock_self, "/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    def test_service_init_failure_raises(self, mock_service, mock_exists, mock_log):
        """Test raises when service initialization fails."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = True
        mock_service.return_value = None
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_google_drive(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_successful_upload_without_metadata(
        self, mock_settings, mock_extract, mock_media, mock_service_fn, mock_exists, mock_log
    ):
        """Test successful upload without metadata."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = "folder123"
        mock_extract.return_value = {}

        mock_service = MagicMock()
        mock_file_result = {"id": "file123", "webViewLink": "https://drive.google.com/file/d/file123"}
        mock_service.files.return_value.create.return_value.execute.return_value = mock_file_result
        mock_service_fn.return_value = mock_service

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf")
        assert result["status"] == "Completed"
        assert result["google_drive_file_id"] == "file123"

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_successful_upload_with_metadata(
        self, mock_settings, mock_extract, mock_media, mock_service_fn, mock_exists, mock_log
    ):
        """Test successful upload with metadata."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = "folder123"
        mock_extract.return_value = {"document_type": "invoice", "amount": 100, "nested": {"key": "val"}}

        mock_service = MagicMock()
        mock_file_result = {"id": "file456", "webViewLink": "https://drive.google.com/file/d/file456"}
        mock_service.files.return_value.create.return_value.execute.return_value = mock_file_result
        mock_service_fn.return_value = mock_service

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf", file_id=1)
        assert result["status"] == "Completed"
        assert result["metadata_included"] is True

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_upload_without_folder_id(
        self, mock_settings, mock_extract, mock_media, mock_service_fn, mock_exists, mock_log
    ):
        """Test upload without folder ID (no parents set)."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = None
        mock_extract.return_value = {}

        mock_service = MagicMock()
        mock_file_result = {"id": "file789", "webViewLink": "https://drive.google.com/file/d/file789"}
        mock_service.files.return_value.create.return_value.execute.return_value = mock_file_result
        mock_service_fn.return_value = mock_service

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf")
        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    def test_upload_exception_raises(self, mock_extract, mock_service_fn, mock_exists, mock_log):
        """Test upload exception is re-raised."""
        from app.tasks.upload_to_google_drive import upload_to_google_drive

        mock_exists.return_value = True
        mock_extract.return_value = {}
        mock_service = MagicMock()
        mock_service.files.return_value.create.return_value.execute.side_effect = Exception("API Error")
        mock_service_fn.return_value = mock_service

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_google_drive(mock_self, "/tmp/test.pdf")
