"""
Tests for app/tasks/upload_to_nextcloud.py module.

Covers the upload_to_nextcloud Celery task including configuration validation,
WebDAV upload, directory creation, and error handling.
"""

from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestUploadToNextcloud:
    """Tests for upload_to_nextcloud Celery task."""

    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    def test_file_not_found(self, mock_log):
        """Test that missing file raises FileNotFoundError."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        with pytest.raises(FileNotFoundError):
            upload_to_nextcloud.__wrapped__("/nonexistent/file.pdf", file_id=1)

    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_skipped_when_not_configured(self, mock_settings, mock_log, tmp_path):
        """Test upload skipped when Nextcloud URL not configured."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = None
        mock_settings.nextcloud_username = None
        mock_settings.nextcloud_password = None

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Skipped"

    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_skipped_when_username_missing(self, mock_settings, mock_log, tmp_path):
        """Test upload skipped when username is missing."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav"
        mock_settings.nextcloud_username = None
        mock_settings.nextcloud_password = "password"  # noqa: S105

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Skipped"

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_successful_upload_201(self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path):
        """Test successful file upload with 201 response."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        # Mock the PUT response for file upload
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        # Mock PROPFIND for existence check
        mock_propfind_response = Mock()
        mock_propfind_response.text = ""
        mock_requests.request.return_value = mock_propfind_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert result["response_code"] == 201

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_successful_upload_204(self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path):
        """Test successful file upload with 204 (No Content / overwrite) response."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        mock_put_response = Mock()
        mock_put_response.status_code = 204
        mock_requests.put.return_value = mock_put_response

        mock_propfind_response = Mock()
        mock_propfind_response.text = ""
        mock_requests.request.return_value = mock_propfind_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert result["response_code"] == 204

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_upload_failure_status_code(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test upload failure with non-success status code."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        mock_put_response = Mock()
        mock_put_response.status_code = 500
        mock_put_response.text = "Internal Server Error"
        mock_requests.put.return_value = mock_put_response

        mock_propfind_response = Mock()
        mock_propfind_response.text = ""
        mock_requests.request.return_value = mock_propfind_response

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_creates_parent_directories(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test that parent directories are created via MKCOL."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = "documents"
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "documents/subfolder/test.pdf"
        mock_unique.return_value = "documents/subfolder/test.pdf"

        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        mock_request_response = Mock()
        mock_request_response.text = ""
        mock_requests.request.return_value = mock_request_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        # Verify MKCOL calls were made for parent directories
        mkcol_calls = [c for c in mock_requests.request.call_args_list if c[0][0] == "MKCOL"]
        assert len(mkcol_calls) >= 1

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_connection_error(self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path):
        """Test handling of connection errors during upload."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        mock_requests.put.side_effect = Exception("Connection refused")
        mock_requests.request.return_value = Mock(text="")

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_url_trailing_slash_normalization(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test that URLs without trailing slashes are handled."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        mock_request_response = Mock()
        mock_request_response.text = ""
        mock_requests.request.return_value = mock_request_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_file_exists_check_returns_true(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test that check_exists_in_nextcloud correctly identifies existing files."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"

        # Mock PROPFIND to return file exists (path in response text)
        mock_propfind_response = Mock()
        mock_propfind_response.text = "test.pdf"
        mock_requests.request.return_value = mock_propfind_response

        # get_unique_filename should be called and will use check_exists_in_nextcloud
        def mock_get_unique(path, check_fn):
            # Call check_fn to exercise the inner function
            exists = check_fn(path)
            return "test_1.pdf" if exists else path

        mock_unique.side_effect = mock_get_unique

        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_file_exists_check_exception_handling(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test that check_exists_in_nextcloud handles exceptions gracefully."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        mock_extract.return_value = "test.pdf"

        # Mock get_unique_filename to call check function with exception
        def mock_get_unique(path, check_fn):
            # Mock PROPFIND to raise exception
            mock_requests.request.side_effect = Exception("Network error")
            # Call check_fn to exercise exception handling
            exists = check_fn(path)
            # Should return False when exception occurs
            assert exists is False
            return path

        mock_unique.side_effect = mock_get_unique

        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_nextcloud.get_unique_filename")
    @patch("app.tasks.upload_to_nextcloud.extract_remote_path")
    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    @patch("app.tasks.upload_to_nextcloud.settings")
    def test_empty_parent_dirs_handling(
        self, mock_settings, mock_log, mock_requests, mock_extract, mock_unique, tmp_path
    ):
        """Test handling of empty parent directory paths."""
        from app.tasks.upload_to_nextcloud import upload_to_nextcloud

        mock_settings.nextcloud_upload_url = "https://nextcloud.example.com/remote.php/dav/"
        mock_settings.nextcloud_username = "user"
        mock_settings.nextcloud_password = "pass"  # noqa: S105
        mock_settings.nextcloud_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        # Return a path with no parent directory (file in root)
        mock_extract.return_value = "test.pdf"
        mock_unique.return_value = "test.pdf"

        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_requests.put.return_value = mock_put_response

        mock_propfind_response = Mock()
        mock_propfind_response.text = ""
        mock_requests.request.return_value = mock_propfind_response

        result = upload_to_nextcloud.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        # No MKCOL calls should be made for root-level files
        mkcol_calls = [c for c in mock_requests.request.call_args_list if c[0][0] == "MKCOL"]
        assert len(mkcol_calls) == 0
