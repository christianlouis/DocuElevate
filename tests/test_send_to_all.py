"""Tests for app/tasks/send_to_all.py module."""

from unittest.mock import MagicMock, patch

import pytest

from app.tasks.send_to_all import (
    _should_upload_to_dropbox,
    _should_upload_to_email,
    _should_upload_to_ftp,
    _should_upload_to_google_drive,
    _should_upload_to_nextcloud,
    _should_upload_to_onedrive,
    _should_upload_to_paperless,
    _should_upload_to_s3,
    _should_upload_to_sftp,
    _should_upload_to_webdav,
    get_configured_services_from_validator,
    send_to_all_destinations,
)


@pytest.mark.unit
class TestShouldUploadFunctions:
    """Test the _should_upload_to_* helper functions."""

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_dropbox_all_configured(self, mock_settings):
        """Test Dropbox upload check when all credentials are configured."""
        mock_settings.dropbox_app_key = "key"
        mock_settings.dropbox_app_secret = "secret"
        mock_settings.dropbox_refresh_token = "token"

        assert _should_upload_to_dropbox() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_dropbox_missing_credentials(self, mock_settings):
        """Test Dropbox upload check when credentials are missing."""
        mock_settings.dropbox_app_key = None
        mock_settings.dropbox_app_secret = None
        mock_settings.dropbox_refresh_token = None

        assert _should_upload_to_dropbox() is False

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_nextcloud_configured(self, mock_settings):
        """Test Nextcloud upload check."""
        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"

        assert _should_upload_to_nextcloud() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_paperless_configured(self, mock_settings):
        """Test Paperless upload check."""
        mock_settings.paperless_ngx_api_token = "token"
        mock_settings.paperless_host = "https://paperless.example.com"

        assert _should_upload_to_paperless() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_google_drive_oauth(self, mock_settings):
        """Test Google Drive upload check with OAuth."""
        mock_settings.google_drive_use_oauth = True
        mock_settings.google_drive_client_id = "client_id"
        mock_settings.google_drive_client_secret = "client_secret"
        mock_settings.google_drive_refresh_token = "refresh_token"
        mock_settings.google_drive_folder_id = "folder_id"

        assert _should_upload_to_google_drive() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_google_drive_service_account(self, mock_settings):
        """Test Google Drive upload check with service account."""
        mock_settings.google_drive_use_oauth = False
        mock_settings.google_drive_credentials_json = '{"type": "service_account"}'
        mock_settings.google_drive_folder_id = "folder_id"

        assert _should_upload_to_google_drive() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_webdav_configured(self, mock_settings):
        """Test WebDAV upload check."""
        mock_settings.webdav_url = "https://webdav.example.com"
        mock_settings.webdav_username = "user"
        mock_settings.webdav_password = "pass"

        assert _should_upload_to_webdav() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_ftp_configured(self, mock_settings):
        """Test FTP upload check."""
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"

        assert _should_upload_to_ftp() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_sftp_with_password(self, mock_settings):
        """Test SFTP upload check with password auth."""
        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_username = "user"
        mock_settings.sftp_password = "pass"
        mock_settings.sftp_private_key = None

        assert _should_upload_to_sftp() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_sftp_with_key(self, mock_settings):
        """Test SFTP upload check with key auth."""
        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_username = "user"
        mock_settings.sftp_password = None
        mock_settings.sftp_private_key = "/path/to/key"

        assert _should_upload_to_sftp() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_email_configured(self, mock_settings):
        """Test email upload check."""
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_username = "user"
        mock_settings.email_password = "pass"
        mock_settings.email_default_recipient = "recipient@example.com"

        assert _should_upload_to_email() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_onedrive_configured(self, mock_settings):
        """Test OneDrive upload check."""
        mock_settings.onedrive_client_id = "client_id"
        mock_settings.onedrive_client_secret = "client_secret"
        mock_settings.onedrive_refresh_token = "refresh_token"

        assert _should_upload_to_onedrive() is True

    @patch("app.tasks.send_to_all.settings")
    def test_should_upload_to_s3_configured(self, mock_settings):
        """Test S3 upload check."""
        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key_id"
        mock_settings.aws_secret_access_key = "secret_key"

        assert _should_upload_to_s3() is True


@pytest.mark.unit
class TestGetConfiguredServicesFromValidator:
    """Test get_configured_services_from_validator function."""

    @patch("app.tasks.send_to_all.get_provider_status")
    def test_returns_configured_services(self, mock_get_status):
        """Test that configured services are returned correctly."""
        mock_get_status.return_value = {
            "Dropbox": {"configured": True},
            "NextCloud": {"configured": False},
            "S3 Storage": {"configured": True},
        }

        result = get_configured_services_from_validator()

        assert result["dropbox"] is True
        assert result["nextcloud"] is False
        assert result["s3"] is True

    @patch("app.tasks.send_to_all.get_provider_status")
    def test_handles_missing_providers(self, mock_get_status):
        """Test handling when some providers are not in status."""
        mock_get_status.return_value = {
            "Dropbox": {"configured": True},
        }

        result = get_configured_services_from_validator()

        assert result["dropbox"] is True
        # Other services not in result


@pytest.mark.unit
class TestSendToAllDestinations:
    """Test send_to_all_destinations task."""

    @patch("app.tasks.send_to_all.log_task_progress")
    def test_file_not_found_error(self, mock_log):
        """Test that FileNotFoundError is raised when file doesn't exist."""
        result = send_to_all_destinations.apply(args=["/nonexistent/file.pdf"])

        # When task raises an exception, result.failed() returns True
        assert result.failed()
        # The exception should be FileNotFoundError
        assert isinstance(result.result, FileNotFoundError)

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all.upload_to_dropbox")
    def test_queues_single_configured_service(self, mock_upload, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test queueing upload to a single configured service."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_should.return_value = True
        # Mock all other services to return False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False
        mock_upload.delay.return_value = MagicMock(id="task-123")

        result = send_to_all_destinations.apply(args=[str(test_file), False, 1])

        assert result.result["status"] == "Queued"
        mock_upload.delay.assert_called_once()

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all.upload_to_dropbox")
    @patch("app.tasks.send_to_all.upload_to_s3")
    def test_queues_multiple_services(
        self, mock_s3_upload, mock_dropbox_upload, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should_s3, mock_should_dropbox, mock_settings, mock_log, mock_session_local, tmp_path
    ):
        """Test queueing uploads to multiple services."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_should_dropbox.return_value = True
        mock_should_s3.return_value = True
        # Mock all other services to return False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_dropbox_upload.delay.return_value = MagicMock(id="dropbox-task")
        mock_s3_upload.delay.return_value = MagicMock(id="s3-task")

        result = send_to_all_destinations.apply(args=[str(test_file), False, 1])

        assert result.result["status"] == "Queued"
        mock_dropbox_upload.delay.assert_called_once()
        mock_s3_upload.delay.assert_called_once()

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    def test_skips_unconfigured_services(self, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test that unconfigured services are skipped."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        # Set all _should_upload_* functions to return False
        mock_should.return_value = False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False

        result = send_to_all_destinations.apply(args=[str(test_file), False, 1])

        # No uploads should be queued
        assert result.result["status"] == "Queued"
        # Check that message indicates 0 uploads
        assert "0 upload" in result.result["tasks"] or len(result.result["tasks"]) == 0

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all.upload_to_dropbox")
    def test_with_file_id_parameter(self, mock_upload, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should, mock_settings, mock_session_local, mock_log, tmp_path):
        """Test send_to_all with explicit file_id parameter."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_should.return_value = True
        # Mock all other services to return False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False
        mock_upload.delay.return_value = MagicMock(id="task-123")

        result = send_to_all_destinations.apply(args=[str(test_file), False, 42])

        mock_upload.delay.assert_called_once()
        # Verify file_id was passed to the upload task
        call_kwargs = mock_upload.delay.call_args[1]
        assert call_kwargs.get("file_id") == 42

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all.get_configured_services_from_validator")
    @patch("app.tasks.send_to_all.upload_to_dropbox")
    def test_uses_validator_when_enabled(self, mock_upload, mock_validator, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should_dropbox, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test that validator is used when use_validator=True."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_validator.return_value = {"dropbox": True}
        # Mock all should_upload functions to return False (they won't be called when validator is used, but just in case)
        mock_should_dropbox.return_value = False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False
        mock_upload.delay.return_value = MagicMock(id="task-123")

        result = send_to_all_destinations.apply(args=[str(test_file), True, 1])

        mock_validator.assert_called_once()
        mock_upload.delay.assert_called_once()

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all.get_configured_services_from_validator")
    def test_validator_exception_fallback(self, mock_validator, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should_dropbox, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test fallback to individual checks when validator fails."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_validator.side_effect = Exception("Validator error")
        # Set all _should_upload_* functions to return False
        mock_should_dropbox.return_value = False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False

        # Should not raise, should fall back to individual checks
        result = send_to_all_destinations.apply(args=[str(test_file), True, 1])

        assert result.result["status"] == "Queued"

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    @patch("app.tasks.send_to_all.upload_to_dropbox")
    def test_handles_upload_task_queue_error(self, mock_upload, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test handling when queueing upload task fails."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_should.return_value = True
        # Mock all other services to return False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False
        mock_upload.delay.side_effect = Exception("Queue error")

        # Should not raise, should log error
        result = send_to_all_destinations.apply(args=[str(test_file), False, 1])

        assert result.result["status"] == "Queued"
        # Error should be recorded in results
        assert "dropbox_error" in result.result["tasks"]

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.settings")
    def test_fallback_file_id_lookup(self, mock_settings, mock_session_local, mock_log, tmp_path):
        """Test file_id lookup fallback when not provided."""
        from app.models import FileRecord

        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_settings.workdir = str(tmp_path)

        # Mock database session
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_file_record = MagicMock(spec=FileRecord)
        mock_file_record.id = 123
        mock_query.first.return_value = mock_file_record
        mock_db.query.return_value.filter.return_value = mock_query
        mock_session_local.return_value.__enter__.return_value = mock_db

        result = send_to_all_destinations.apply(args=[str(test_file), False, None])

        # Should attempt database lookup
        mock_db.query.assert_called()

    @patch("app.tasks.send_to_all.SessionLocal")
    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.settings")
    @patch("app.tasks.send_to_all._should_upload_to_dropbox")
    @patch("app.tasks.send_to_all._should_upload_to_nextcloud")
    @patch("app.tasks.send_to_all._should_upload_to_paperless")
    @patch("app.tasks.send_to_all._should_upload_to_google_drive")
    @patch("app.tasks.send_to_all._should_upload_to_webdav")
    @patch("app.tasks.send_to_all._should_upload_to_ftp")
    @patch("app.tasks.send_to_all._should_upload_to_sftp")
    @patch("app.tasks.send_to_all._should_upload_to_email")
    @patch("app.tasks.send_to_all._should_upload_to_onedrive")
    @patch("app.tasks.send_to_all._should_upload_to_s3")
    def test_should_upload_check_exception_handling(self, mock_s3, mock_onedrive, mock_email, mock_sftp, mock_ftp, mock_webdav, mock_google, mock_paperless, mock_nextcloud, mock_should, mock_settings, mock_log, mock_session_local, tmp_path):
        """Test that exceptions in should_upload checks are handled."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test")

        mock_should.side_effect = Exception("Configuration check error")
        # Mock all other services to return False
        mock_nextcloud.return_value = False
        mock_paperless.return_value = False
        mock_google.return_value = False
        mock_webdav.return_value = False
        mock_ftp.return_value = False
        mock_sftp.return_value = False
        mock_email.return_value = False
        mock_onedrive.return_value = False
        mock_s3.return_value = False

        # Should not raise, should treat as not configured
        result = send_to_all_destinations.apply(args=[str(test_file), False, 1])

        assert result.result["status"] == "Queued"
