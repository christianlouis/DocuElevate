"""Tests for app/tasks/upload_to_s3.py module."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.tasks.upload_to_s3 import upload_to_s3


@pytest.mark.unit
class TestUploadToS3:
    """Tests for S3 upload functionality."""

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_success_with_folder_prefix(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test successful S3 upload with folder prefix."""
        # Setup
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"
        mock_settings.aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_folder_prefix = "documents"
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = "private"

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Execute
        result = upload_to_s3.apply(args=[str(test_file)])

        # Verify
        assert result.result["status"] == "Completed"
        assert result.result["s3_bucket"] == "my-bucket"
        assert result.result["s3_key"] == "documents/test.pdf"

        mock_s3.upload_file.assert_called_once()
        call_args = mock_s3.upload_file.call_args
        assert call_args[0][0] == str(test_file)
        assert call_args[0][1] == "my-bucket"
        assert call_args[0][2] == "documents/test.pdf"
        assert call_args[1]["ExtraArgs"]["StorageClass"] == "STANDARD"
        assert call_args[1]["ExtraArgs"]["ACL"] == "private"

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_without_folder_prefix(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test S3 upload without folder prefix."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "us-west-2"
        mock_settings.s3_folder_prefix = None
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        result = upload_to_s3.apply(args=[str(test_file)])

        assert result.result["s3_key"] == "test.pdf"
        # Verify ACL not included when None
        extra_args = mock_s3.upload_file.call_args[1]["ExtraArgs"]
        assert "ACL" not in extra_args

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_with_folder_prefix_no_trailing_slash(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test that folder prefix gets trailing slash added."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "us-west-2"
        mock_settings.s3_folder_prefix = "uploads/docs"  # No trailing slash
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        result = upload_to_s3.apply(args=[str(test_file)])

        # Should add trailing slash
        assert result.result["s3_key"] == "uploads/docs/test.pdf"

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_file_not_found(self, mock_settings, mock_log):
        """Test S3 upload with non-existent file."""
        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"

        result = upload_to_s3.apply(args=["/nonexistent/file.pdf"])
        assert isinstance(result.result, FileNotFoundError)

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_missing_bucket_name(self, mock_settings, mock_log, tmp_path):
        """Test S3 upload with missing bucket name."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = None
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"

        result = upload_to_s3.apply(args=[str(test_file)])
        assert isinstance(result.result, ValueError)
        assert "bucket name" in str(result.result)

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_missing_credentials(self, mock_settings, mock_log, tmp_path):
        """Test S3 upload with missing AWS credentials."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = None
        mock_settings.aws_secret_access_key = None

        result = upload_to_s3.apply(args=[str(test_file)])
        assert isinstance(result.result, ValueError)
        assert "credentials" in str(result.result)

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_client_error(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test S3 upload with boto3 ClientError."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_folder_prefix = None
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        error_response = {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}}
        mock_s3.upload_file.side_effect = ClientError(error_response, "upload_file")
        mock_boto_client.return_value = mock_s3

        result = upload_to_s3.apply(args=[str(test_file)])
        assert isinstance(result.result, Exception)
        assert "Failed to upload" in str(result.result)

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_generic_exception(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test S3 upload with generic exception."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_folder_prefix = None
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = Exception("Network error")
        mock_boto_client.return_value = mock_s3

        result = upload_to_s3.apply(args=[str(test_file)])
        assert isinstance(result.result, Exception)
        assert "Error uploading" in str(result.result)

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_with_different_storage_classes(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test S3 upload with different storage classes."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "us-east-1"
        mock_settings.s3_folder_prefix = None
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Test INTELLIGENT_TIERING
        mock_settings.s3_storage_class = "INTELLIGENT_TIERING"
        result = upload_to_s3.apply(args=[str(test_file)])
        extra_args = mock_s3.upload_file.call_args[1]["ExtraArgs"]
        assert extra_args["StorageClass"] == "INTELLIGENT_TIERING"

    @patch("app.tasks.upload_to_s3.log_task_progress")
    @patch("app.tasks.upload_to_s3.boto3.client")
    @patch("app.tasks.upload_to_s3.settings")
    def test_upload_url_generation(self, mock_settings, mock_boto_client, mock_log, tmp_path):
        """Test that the S3 URL is properly generated."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.s3_bucket_name = "my-bucket"
        mock_settings.aws_access_key_id = "key"
        mock_settings.aws_secret_access_key = "secret"
        mock_settings.aws_region = "eu-west-1"
        mock_settings.s3_folder_prefix = "docs"
        mock_settings.s3_storage_class = "STANDARD"
        mock_settings.s3_acl = None

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        result = upload_to_s3.apply(args=[str(test_file)])

        expected_url = "https://my-bucket.s3.eu-west-1.amazonaws.com/docs/test.pdf"
        assert result.result["s3_url"] == expected_url
