"""
Tests for upload tasks including OneDrive, S3, FTP, SFTP, WebDAV, Google Drive, and Email.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_s3 import upload_to_s3
from app.tasks.upload_to_ftp import upload_to_ftp
from app.tasks.upload_to_sftp import upload_to_sftp
from app.tasks.upload_to_webdav import upload_to_webdav
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_email import upload_to_email


@pytest.fixture
def mock_settings():
    """Mock settings for upload tests."""
    with patch("app.tasks.upload_to_onedrive.settings") as onedrive_settings, patch(
        "app.tasks.upload_to_s3.settings"
    ) as s3_settings:
        # OneDrive settings
        onedrive_settings.onedrive_client_id = "test_client_id"
        onedrive_settings.onedrive_client_secret = "test_secret"
        onedrive_settings.onedrive_refresh_token = "test_refresh_token"
        onedrive_settings.onedrive_folder_path = "test_folder"
        onedrive_settings.onedrive_tenant_id = "common"

        # S3 settings
        s3_settings.s3_bucket_name = "test-bucket"
        s3_settings.aws_access_key_id = "test_access_key"
        s3_settings.aws_secret_access_key = "test_secret_key"
        s3_settings.aws_region = "us-east-1"
        s3_settings.s3_folder_prefix = "documents"
        s3_settings.s3_storage_class = "STANDARD"
        s3_settings.s3_acl = None

        yield onedrive_settings, s3_settings


@pytest.mark.unit
def test_upload_to_onedrive_accepts_file_id(sample_text_file, mock_settings):
    """Test that upload_to_onedrive accepts file_id parameter."""
    with patch("app.tasks.upload_to_onedrive.get_onedrive_token") as mock_token, patch(
        "app.tasks.upload_to_onedrive.create_upload_session"
    ) as mock_session, patch("app.tasks.upload_to_onedrive.upload_large_file") as mock_upload, patch(
        "app.tasks.upload_to_onedrive.log_task_progress"
    ):

        # Setup mocks
        mock_token.return_value = "test_access_token"
        mock_session.return_value = "https://upload.url"
        mock_upload.return_value = {"webUrl": "https://onedrive.test/file"}

        # Call with file_id parameter using apply() to simulate task execution
        # This bypasses Celery and calls the function directly
        result = upload_to_onedrive.apply(args=[sample_text_file], kwargs={"file_id": 42}).get()

        assert result["status"] == "Completed"
        assert result["file_path"] == sample_text_file
        assert "onedrive_path" in result


@pytest.mark.unit
def test_upload_to_onedrive_without_file_id(sample_text_file, mock_settings):
    """Test that upload_to_onedrive works without file_id parameter."""
    with patch("app.tasks.upload_to_onedrive.get_onedrive_token") as mock_token, patch(
        "app.tasks.upload_to_onedrive.create_upload_session"
    ) as mock_session, patch("app.tasks.upload_to_onedrive.upload_large_file") as mock_upload, patch(
        "app.tasks.upload_to_onedrive.log_task_progress"
    ):

        # Setup mocks
        mock_token.return_value = "test_access_token"
        mock_session.return_value = "https://upload.url"
        mock_upload.return_value = {"webUrl": "https://onedrive.test/file"}

        # Call without file_id parameter - should use default None
        result = upload_to_onedrive.apply(args=[sample_text_file]).get()

        assert result["status"] == "Completed"
        assert result["file_path"] == sample_text_file


@pytest.mark.unit
def test_upload_to_s3_accepts_file_id(sample_text_file, mock_settings):
    """Test that upload_to_s3 accepts file_id parameter."""
    with patch("app.tasks.upload_to_s3.boto3.client") as mock_boto_client, patch(
        "app.tasks.upload_to_s3.log_task_progress"
    ):

        # Setup mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.upload_file.return_value = None

        # Call with file_id parameter using apply()
        result = upload_to_s3.apply(args=[sample_text_file], kwargs={"file_id": 99}).get()

        assert result["status"] == "Completed"
        assert result["file"] == sample_text_file
        assert result["s3_bucket"] == "test-bucket"
        assert "s3_key" in result


@pytest.mark.unit
def test_upload_to_s3_without_file_id(sample_text_file, mock_settings):
    """Test that upload_to_s3 works without file_id parameter."""
    with patch("app.tasks.upload_to_s3.boto3.client") as mock_boto_client, patch(
        "app.tasks.upload_to_s3.log_task_progress"
    ):

        # Setup mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.upload_file.return_value = None

        # Call without file_id parameter using apply()
        result = upload_to_s3.apply(args=[sample_text_file]).get()

        assert result["status"] == "Completed"
        assert result["file"] == sample_text_file


@pytest.mark.unit
def test_upload_to_onedrive_file_not_found(mock_settings):
    """Test that upload_to_onedrive raises error for missing file."""
    with patch("app.tasks.upload_to_onedrive.log_task_progress"):
        with pytest.raises(FileNotFoundError):
            upload_to_onedrive.apply(args=["/nonexistent/file.pdf"], kwargs={"file_id": 1}).get()


@pytest.mark.unit
def test_upload_to_s3_file_not_found(mock_settings):
    """Test that upload_to_s3 raises error for missing file."""
    with patch("app.tasks.upload_to_s3.log_task_progress"):
        with pytest.raises(FileNotFoundError):
            upload_to_s3.apply(args=["/nonexistent/file.pdf"], kwargs={"file_id": 1}).get()


@pytest.mark.unit
def test_upload_to_onedrive_logs_with_file_id(sample_text_file, mock_settings):
    """Test that upload_to_onedrive properly logs with file_id."""
    with patch("app.tasks.upload_to_onedrive.get_onedrive_token") as mock_token, patch(
        "app.tasks.upload_to_onedrive.create_upload_session"
    ) as mock_session, patch("app.tasks.upload_to_onedrive.upload_large_file") as mock_upload, patch(
        "app.tasks.upload_to_onedrive.log_task_progress"
    ) as mock_log:

        # Setup mocks
        mock_token.return_value = "test_access_token"
        mock_session.return_value = "https://upload.url"
        mock_upload.return_value = {"webUrl": "https://onedrive.test/file"}

        # Call with file_id
        upload_to_onedrive.apply(args=[sample_text_file], kwargs={"file_id": 123}).get()

        # Verify log_task_progress was called with file_id
        assert mock_log.called
        # Check that at least one call included the file_id parameter
        calls_with_file_id = [
            call for call in mock_log.call_args_list if "file_id" in call[1] and call[1]["file_id"] == 123
        ]
        assert len(calls_with_file_id) > 0


@pytest.mark.unit
def test_upload_to_s3_logs_with_file_id(sample_text_file, mock_settings):
    """Test that upload_to_s3 properly logs with file_id."""
    with patch("app.tasks.upload_to_s3.boto3.client") as mock_boto_client, patch(
        "app.tasks.upload_to_s3.log_task_progress"
    ) as mock_log:

        # Setup mock S3 client
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.upload_file.return_value = None

        # Call with file_id
        upload_to_s3.apply(args=[sample_text_file], kwargs={"file_id": 456}).get()

        # Verify log_task_progress was called with file_id
        assert mock_log.called
        # Check that at least one call included the file_id parameter
        calls_with_file_id = [
            call for call in mock_log.call_args_list if "file_id" in call[1] and call[1]["file_id"] == 456
        ]
        assert len(calls_with_file_id) > 0


# Tests for newly standardized upload tasks

@pytest.mark.unit
def test_upload_to_ftp_accepts_file_id(sample_text_file):
    """Test that upload_to_ftp accepts file_id parameter."""
    with patch("app.tasks.upload_to_ftp.settings") as mock_settings, \
         patch("app.tasks.upload_to_ftp.ftplib.FTP") as mock_ftp, \
         patch("app.tasks.upload_to_ftp.log_task_progress"):
        
        # Setup settings
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "test_user"
        mock_settings.ftp_password = "test_pass"
        mock_settings.ftp_folder = "uploads"
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = True
        
        # Setup mock FTP
        mock_ftp_instance = Mock()
        mock_ftp.return_value = mock_ftp_instance
        
        # Call with file_id parameter
        result = upload_to_ftp.apply(args=[sample_text_file], kwargs={"file_id": 100}).get()
        
        assert result["status"] == "Completed"
        assert result["file"] == sample_text_file
        assert result["ftp_host"] == "ftp.example.com"


@pytest.mark.unit
def test_upload_to_ftp_without_file_id(sample_text_file):
    """Test that upload_to_ftp works without file_id parameter."""
    with patch("app.tasks.upload_to_ftp.settings") as mock_settings, \
         patch("app.tasks.upload_to_ftp.ftplib.FTP") as mock_ftp, \
         patch("app.tasks.upload_to_ftp.log_task_progress"):
        
        # Setup settings
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_username = "test_user"
        mock_settings.ftp_password = "test_pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = True
        
        # Setup mock FTP
        mock_ftp_instance = Mock()
        mock_ftp.return_value = mock_ftp_instance
        
        # Call without file_id parameter
        result = upload_to_ftp.apply(args=[sample_text_file]).get()
        
        assert result["status"] == "Completed"


@pytest.mark.unit
def test_upload_to_sftp_accepts_file_id(sample_text_file):
    """Test that upload_to_sftp accepts file_id parameter."""
    with patch("app.tasks.upload_to_sftp.settings") as mock_settings, \
         patch("app.tasks.upload_to_sftp.paramiko.SSHClient") as mock_ssh, \
         patch("app.tasks.upload_to_sftp.log_task_progress"), \
         patch("app.tasks.upload_to_sftp.extract_remote_path") as mock_extract, \
         patch("app.tasks.upload_to_sftp.get_unique_filename") as mock_unique:
        
        # Setup settings
        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "test_user"
        mock_settings.sftp_password = "test_pass"
        mock_settings.sftp_folder = "/uploads"
        mock_settings.workdir = "/tmp"
        
        # Setup mocks
        mock_ssh_instance = Mock()
        mock_sftp = Mock()
        mock_ssh.return_value = mock_ssh_instance
        mock_ssh_instance.open_sftp.return_value = mock_sftp
        mock_extract.return_value = "/uploads/test.txt"
        mock_unique.return_value = "/uploads/test.txt"
        
        # Call with file_id parameter
        result = upload_to_sftp.apply(args=[sample_text_file], kwargs={"file_id": 200}).get()
        
        assert result["status"] == "Completed"
        assert result["file_path"] == sample_text_file
        assert "sftp_path" in result


@pytest.mark.unit
def test_upload_to_webdav_accepts_file_id(sample_text_file):
    """Test that upload_to_webdav accepts file_id parameter."""
    with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
         patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
         patch("app.tasks.upload_to_webdav.log_task_progress"):
        
        # Setup settings
        mock_settings.webdav_url = "https://webdav.example.com/"
        mock_settings.webdav_username = "test_user"
        mock_settings.webdav_password = "test_pass"
        mock_settings.webdav_folder = "uploads"
        mock_settings.webdav_verify_ssl = True
        
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_put.return_value = mock_response
        
        # Call with file_id parameter
        result = upload_to_webdav.apply(args=[sample_text_file], kwargs={"file_id": 300}).get()
        
        assert result["status"] == "Completed"
        assert result["file"] == sample_text_file
        assert "url" in result


@pytest.mark.unit
def test_upload_to_google_drive_accepts_file_id(sample_text_file):
    """Test that upload_to_google_drive accepts file_id parameter."""
    with patch("app.tasks.upload_to_google_drive.get_google_drive_service") as mock_service, \
         patch("app.tasks.upload_to_google_drive.MediaFileUpload") as mock_media, \
         patch("app.tasks.upload_to_google_drive.extract_metadata_from_file") as mock_metadata, \
         patch("app.tasks.upload_to_google_drive.settings") as mock_settings, \
         patch("app.tasks.upload_to_google_drive.log_task_progress"):
        
        # Setup settings
        mock_settings.google_drive_folder_id = "test_folder_id"
        
        # Setup mocks
        mock_drive_service = Mock()
        mock_service.return_value = mock_drive_service
        mock_metadata.return_value = {}
        
        mock_files = Mock()
        mock_drive_service.files.return_value = mock_files
        mock_create = Mock()
        mock_files.create.return_value = mock_create
        mock_create.execute.return_value = {
            "id": "file123",
            "name": "test.txt",
            "webViewLink": "https://drive.google.com/file/d/file123"
        }
        
        # Call with file_id parameter
        result = upload_to_google_drive.apply(args=[sample_text_file], kwargs={"file_id": 400}).get()
        
        assert result["status"] == "Completed"
        assert result["file_path"] == sample_text_file
        assert "google_drive_file_id" in result


@pytest.mark.unit
def test_upload_to_email_accepts_file_id(sample_text_file):
    """Test that upload_to_email accepts file_id parameter."""
    with patch("app.tasks.upload_to_email.settings") as mock_settings, \
         patch("app.tasks.upload_to_email.smtplib.SMTP") as mock_smtp, \
         patch("app.tasks.upload_to_email.get_email_template") as mock_template, \
         patch("app.tasks.upload_to_email.extract_metadata_from_file") as mock_metadata, \
         patch("app.tasks.upload_to_email.log_task_progress"), \
         patch("app.tasks.upload_to_email._prepare_recipients") as mock_recipients, \
         patch("app.tasks.upload_to_email._send_email_with_smtp") as mock_send, \
         patch("app.tasks.upload_to_email.attach_logo") as mock_logo:
        
        # Setup settings
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_port = 587
        mock_settings.email_username = "test@example.com"
        mock_settings.email_password = "test_pass"
        mock_settings.email_use_tls = True
        mock_settings.email_sender = "sender@example.com"
        mock_settings.external_hostname = "docuelevate.example.com"
        
        # Setup mocks
        mock_recipients.return_value = (["recipient@example.com"], None)
        mock_send.return_value = None
        mock_metadata.return_value = {}
        mock_logo.return_value = False
        
        mock_template_obj = Mock()
        mock_template_obj.render.return_value = "<html>Test email</html>"
        mock_template.return_value = mock_template_obj
        
        # Call with file_id parameter
        result = upload_to_email.apply(args=[sample_text_file], kwargs={"file_id": 500}).get()
        
        assert result["status"] == "Completed"
        assert result["file"] == sample_text_file
        assert "recipients" in result


@pytest.mark.unit
def test_upload_to_ftp_file_not_found():
    """Test that upload_to_ftp raises error for missing file."""
    with patch("app.tasks.upload_to_ftp.settings") as mock_settings, \
         patch("app.tasks.upload_to_ftp.log_task_progress"):
        
        mock_settings.ftp_host = "ftp.example.com"
        
        with pytest.raises(FileNotFoundError):
            upload_to_ftp.apply(args=["/nonexistent/file.pdf"], kwargs={"file_id": 1}).get()


@pytest.mark.unit
def test_upload_to_sftp_file_not_found():
    """Test that upload_to_sftp raises error for missing file."""
    with patch("app.tasks.upload_to_sftp.settings") as mock_settings, \
         patch("app.tasks.upload_to_sftp.log_task_progress"):
        
        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "test_user"
        
        with pytest.raises(FileNotFoundError):
            upload_to_sftp.apply(args=["/nonexistent/file.pdf"], kwargs={"file_id": 1}).get()


@pytest.mark.unit
def test_upload_to_webdav_file_not_found():
    """Test that upload_to_webdav raises error for missing file."""
    with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
         patch("app.tasks.upload_to_webdav.log_task_progress"):
        
        mock_settings.webdav_url = "https://webdav.example.com/"
        
        with pytest.raises(FileNotFoundError):
            upload_to_webdav.apply(args=["/nonexistent/file.pdf"], kwargs={"file_id": 1}).get()


@pytest.mark.unit
def test_all_upload_tasks_have_consistent_signature(sample_text_file):
    """Test that all upload tasks accept file_id as a keyword parameter."""
    # This test verifies that all upload tasks can be called with the same signature
    # as used in send_to_all.py: task.delay(file_path, file_id)
    
    upload_tasks = [
        (upload_to_s3, "app.tasks.upload_to_s3"),
        (upload_to_ftp, "app.tasks.upload_to_ftp"),
        (upload_to_sftp, "app.tasks.upload_to_sftp"),
        (upload_to_webdav, "app.tasks.upload_to_webdav"),
        (upload_to_google_drive, "app.tasks.upload_to_google_drive"),
        (upload_to_email, "app.tasks.upload_to_email"),
    ]
    
    for task, module_path in upload_tasks:
        # Verify that the task has the expected signature by inspecting its function
        import inspect
        sig = inspect.signature(task.run)
        params = list(sig.parameters.keys())
        
        # Should have at least file_path and file_id parameters
        assert "file_path" in params, f"{task.name} missing file_path parameter"
        assert "file_id" in params, f"{task.name} missing file_id parameter"
        
        # file_id should have a default value (None)
        assert sig.parameters["file_id"].default is None, f"{task.name} file_id should default to None"
