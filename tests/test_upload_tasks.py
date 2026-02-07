"""
Tests for upload tasks including OneDrive and S3.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.upload_to_s3 import upload_to_s3


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
