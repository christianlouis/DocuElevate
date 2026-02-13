"""Tests for app/tasks/upload_to_google_drive.py module."""

import json
from unittest.mock import Mock, patch

import pytest
from google.auth.exceptions import RefreshError

from app.tasks.upload_to_google_drive import (
    extract_metadata_from_file,
    get_drive_service_oauth,
    get_google_drive_service,
    truncate_property_value,
    upload_to_google_drive,
)


@pytest.mark.unit
class TestGetDriveServiceOAuth:
    """Tests for get_drive_service_oauth function."""

    @patch("app.tasks.upload_to_google_drive.build")
    @patch("app.tasks.upload_to_google_drive.OAuthCredentials")
    @patch("app.tasks.upload_to_google_drive.Request")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_creates_service_with_oauth(self, mock_settings, mock_request, mock_creds, mock_build):
        """Test creates Google Drive service with OAuth."""
        mock_settings.google_drive_client_id = "client_id"
        mock_settings.google_drive_client_secret = "client_secret"
        mock_settings.google_drive_refresh_token = "refresh_token"

        mock_credentials = Mock()
        mock_creds.return_value = mock_credentials
        mock_service = Mock()
        mock_build.return_value = mock_service

        result = get_drive_service_oauth()

        assert result == mock_service
        mock_credentials.refresh.assert_called_once()

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_when_credentials_incomplete(self, mock_settings):
        """Test returns None when OAuth credentials are incomplete."""
        mock_settings.google_drive_client_id = None
        mock_settings.google_drive_client_secret = "secret"
        mock_settings.google_drive_refresh_token = "token"

        result = get_drive_service_oauth()

        assert result is None

    @patch("app.tasks.upload_to_google_drive.OAuthCredentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_handles_refresh_error(self, mock_settings, mock_creds):
        """Test handles token refresh error."""
        mock_settings.google_drive_client_id = "client_id"
        mock_settings.google_drive_client_secret = "client_secret"
        mock_settings.google_drive_refresh_token = "refresh_token"

        mock_credentials = Mock()
        mock_credentials.refresh.side_effect = RefreshError("Token expired")
        mock_creds.return_value = mock_credentials

        with pytest.raises(RefreshError):
            get_drive_service_oauth()


@pytest.mark.unit
class TestGetGoogleDriveService:
    """Tests for get_google_drive_service function."""

    @patch("app.tasks.upload_to_google_drive.get_drive_service_oauth")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_uses_oauth_when_configured(self, mock_settings, mock_oauth):
        """Test uses OAuth service when configured."""
        mock_settings.google_drive_use_oauth = True
        mock_service = Mock()
        mock_oauth.return_value = mock_service

        result = get_google_drive_service()

        assert result == mock_service
        mock_oauth.assert_called_once()

    @patch("app.tasks.upload_to_google_drive.build")
    @patch("app.tasks.upload_to_google_drive.Credentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_uses_service_account_by_default(self, mock_settings, mock_creds, mock_build):
        """Test uses service account by default."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_delegate_to = None

        mock_credentials = Mock()
        mock_creds.from_service_account_info.return_value = mock_credentials
        mock_service = Mock()
        mock_build.return_value = mock_service

        result = get_google_drive_service()

        assert result == mock_service

    @patch("app.tasks.upload_to_google_drive.settings")
    def test_returns_none_when_no_credentials(self, mock_settings):
        """Test returns None when no credentials configured."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = None

        result = get_google_drive_service()

        assert result is None

    @patch("app.tasks.upload_to_google_drive.Credentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_delegates_to_user_when_configured(self, mock_settings, mock_creds):
        """Test delegates to user when configured."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_delegate_to = "user@example.com"

        mock_credentials = Mock()
        mock_delegated_creds = Mock()
        mock_credentials.with_subject.return_value = mock_delegated_creds
        mock_creds.from_service_account_info.return_value = mock_credentials

        get_google_drive_service()

        mock_credentials.with_subject.assert_called_once_with("user@example.com")

    @patch("app.tasks.upload_to_google_drive.Credentials")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_handles_invalid_json_credentials(self, mock_settings, mock_creds):
        """Test handles invalid JSON credentials."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = "invalid json {"

        result = get_google_drive_service()

        assert result is None


@pytest.mark.unit
class TestExtractMetadataFromFile:
    """Tests for extract_metadata_from_file function."""

    def test_returns_empty_dict_when_no_metadata(self, tmp_path):
        """Test returns empty dict when no metadata file exists."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        result = extract_metadata_from_file(str(file_path))

        assert result == {}

    def test_loads_metadata_from_json_file(self, tmp_path):
        """Test loads metadata from JSON file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        metadata = {"document_type": "invoice", "amount": 100.00}
        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(metadata))

        result = extract_metadata_from_file(str(file_path))

        assert result == metadata

    def test_handles_invalid_json_gracefully(self, tmp_path):
        """Test handles invalid JSON gracefully."""
        file_path = tmp_path / "test.pdf"
        file_path.write_text("test content")

        json_path = tmp_path / "test.json"
        json_path.write_text("invalid json {")

        result = extract_metadata_from_file(str(file_path))

        assert result == {}


@pytest.mark.unit
class TestTruncatePropertyValue:
    """Tests for truncate_property_value function."""

    def test_returns_original_value_when_under_limit(self):
        """Test returns original value when under byte limit."""
        result = truncate_property_value("short_key", "short value")
        assert result == "short value"

    def test_truncates_long_value(self):
        """Test truncates long value to fit byte limit."""
        long_value = "x" * 200
        result = truncate_property_value("key", long_value, max_bytes=100)
        assert len(result.encode("utf-8")) < 100
        assert result.endswith("...")

    def test_handles_unicode_characters(self):
        """Test handles Unicode characters correctly."""
        unicode_value = "日本語テキスト" * 20  # Japanese text
        result = truncate_property_value("key", unicode_value, max_bytes=50)
        assert len(result.encode("utf-8")) < 100  # Should be truncated

    def test_handles_non_string_values(self):
        """Test converts non-string values to string."""
        result = truncate_property_value("key", 12345)
        assert result == "12345"

    def test_respects_key_size_in_calculation(self):
        """Test respects key size in byte calculation."""
        long_key = "very_long_key_name_that_takes_bytes"
        value = "x" * 100
        result = truncate_property_value(long_key, value, max_bytes=100)
        total_bytes = len(long_key.encode("utf-8")) + len(result.encode("utf-8"))
        assert total_bytes <= 100


@pytest.mark.unit
class TestUploadToGoogleDriveTask:
    """Tests for upload_to_google_drive task."""

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_uploads_file_successfully(
        self, mock_settings, mock_media, mock_exists, mock_log, mock_extract, mock_service
    ):
        """Test uploads file to Google Drive successfully."""
        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = "folder_123"

        mock_extract.return_value = {}

        # Mock Google Drive service
        mock_drive_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock(
            return_value={
                "id": "file_123",
                "name": "test.pdf",
                "webViewLink": "https://drive.google.com/file/d/file_123",
            }
        )
        mock_create.execute = mock_execute
        mock_files.create.return_value = mock_create
        mock_drive_service.files.return_value = mock_files
        mock_service.return_value = mock_drive_service

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Completed"
        assert result["google_drive_file_id"] == "file_123"
        assert "webViewLink" in result["google_drive_web_link"]

    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_raises_error_when_file_not_found(self, mock_exists, mock_log):
        """Test raises error when file not found."""
        mock_exists.return_value = False

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(FileNotFoundError):
            upload_to_google_drive(mock_self, "/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    def test_raises_error_when_service_init_fails(self, mock_exists, mock_log, mock_service):
        """Test raises error when service initialization fails."""
        mock_exists.return_value = True
        mock_service.return_value = None

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to initialize Google Drive service"):
            upload_to_google_drive(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_includes_metadata_in_upload(
        self, mock_settings, mock_media, mock_exists, mock_log, mock_extract, mock_service
    ):
        """Test includes metadata in upload."""
        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = None

        metadata = {"document_type": "invoice", "amount": "100.00", "date": "2024-01-01"}
        mock_extract.return_value = metadata

        mock_drive_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock(
            return_value={
                "id": "file_123",
                "name": "test.pdf",
                "webViewLink": "https://drive.google.com/file/d/file_123",
                "properties": {"document_type": "invoice"},
            }
        )
        mock_create.execute = mock_execute
        mock_files.create.return_value = mock_create
        mock_drive_service.files.return_value = mock_files
        mock_service.return_value = mock_drive_service

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf", include_metadata=True)

        assert result["metadata_included"] is True

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_skips_nested_metadata_objects(
        self, mock_settings, mock_media, mock_exists, mock_log, mock_extract, mock_service
    ):
        """Test skips nested objects in metadata."""
        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = None

        metadata = {"simple_field": "value", "nested_object": {"key": "value"}, "nested_list": [1, 2, 3]}
        mock_extract.return_value = metadata

        mock_drive_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock(
            return_value={
                "id": "file_123",
                "name": "test.pdf",
                "webViewLink": "https://drive.google.com/file/d/file_123",
            }
        )
        mock_create.execute = mock_execute
        mock_files.create.return_value = mock_create
        mock_drive_service.files.return_value = mock_files
        mock_service.return_value = mock_drive_service

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_google_drive(mock_self, "/tmp/test.pdf", include_metadata=True)

        # Verify the create call was made
        mock_files.create.assert_called_once()
        call_args = mock_files.create.call_args
        file_metadata = call_args.kwargs["body"]

        # Nested objects should not be in properties
        if "properties" in file_metadata:
            assert "nested_object" not in file_metadata["properties"]
            assert "nested_list" not in file_metadata["properties"]

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_handles_upload_exception(self, mock_settings, mock_media, mock_exists, mock_log, mock_service):
        """Test handles upload exception."""
        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = None

        mock_drive_service = Mock()
        mock_files = Mock()
        mock_files.create.side_effect = Exception("Upload failed")
        mock_drive_service.files.return_value = mock_files
        mock_service.return_value = mock_drive_service

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_google_drive(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_google_drive.get_google_drive_service")
    @patch("app.tasks.upload_to_google_drive.extract_metadata_from_file")
    @patch("app.tasks.upload_to_google_drive.log_task_progress")
    @patch("app.tasks.upload_to_google_drive.os.path.exists")
    @patch("app.tasks.upload_to_google_drive.MediaFileUpload")
    @patch("app.tasks.upload_to_google_drive.settings")
    def test_sets_parent_folder_when_configured(
        self, mock_settings, mock_media, mock_exists, mock_log, mock_extract, mock_service
    ):
        """Test sets parent folder when configured."""
        mock_exists.return_value = True
        mock_settings.google_drive_folder_id = "parent_folder_123"
        mock_extract.return_value = {}

        mock_drive_service = Mock()
        mock_files = Mock()
        mock_create = Mock()
        mock_execute = Mock(
            return_value={
                "id": "file_123",
                "name": "test.pdf",
                "webViewLink": "https://drive.google.com/file/d/file_123",
            }
        )
        mock_create.execute = mock_execute
        mock_files.create.return_value = mock_create
        mock_drive_service.files.return_value = mock_files
        mock_service.return_value = mock_drive_service

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        upload_to_google_drive(mock_self, "/tmp/test.pdf")

        # Verify parent folder was set
        call_args = mock_files.create.call_args
        file_metadata = call_args.kwargs["body"]
        assert file_metadata["parents"] == ["parent_folder_123"]
