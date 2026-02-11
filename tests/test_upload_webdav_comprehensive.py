"""Comprehensive tests for upload_to_webdav task."""
import os
import pytest
from unittest.mock import patch, Mock, MagicMock
from requests.exceptions import ConnectionError, Timeout, RequestException

from app.tasks.upload_to_webdav import upload_to_webdav

_TEST_CREDENTIAL = "test_pass"  # noqa: S105
_TEST_CUSTOM_CREDENTIAL = "custom_password123"  # noqa: S105


@pytest.mark.unit
class TestUploadToWebDAV:
    """Comprehensive tests for WebDAV upload task."""

    def test_upload_success_with_file_id(self, sample_text_file):
        """Test successful upload with file_id parameter."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress") as mock_log:
            
            # Setup settings
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            # Setup mock response - 201 Created
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            # Execute upload
            result = upload_to_webdav.apply(args=[sample_text_file], kwargs={"file_id": 100}).get()
            
            # Verify result
            assert result["status"] == "Completed"
            assert result["file"] == sample_text_file
            assert "url" in result
            assert "webdav.example.com" in result["url"]
            
            # Verify requests.put was called correctly
            assert mock_put.called
            call_args = mock_put.call_args
            assert call_args[1]["auth"] == ("test_user", _TEST_CREDENTIAL)
            assert call_args[1]["verify"] is True
            assert call_args[1]["timeout"] == 30
            
            # Verify logging was called with file_id
            assert mock_log.called
            log_calls_with_file_id = [
                call for call in mock_log.call_args_list 
                if call[1].get("file_id") == 100
            ]
            assert len(log_calls_with_file_id) > 0

    def test_upload_success_without_file_id(self, sample_text_file):
        """Test successful upload without file_id parameter."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = ""
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 200  # 200 OK is also valid
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            assert result["status"] == "Completed"
            assert result["file"] == sample_text_file

    def test_upload_success_status_204(self, sample_text_file):
        """Test successful upload with 204 No Content status."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = None
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 204  # 204 No Content
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            assert result["status"] == "Completed"

    def test_missing_webdav_url(self, sample_text_file):
        """Test that missing WebDAV URL raises ValueError."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = None
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            
            with pytest.raises(ValueError, match="WebDAV URL is not configured"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_file_not_found(self):
        """Test that missing file raises FileNotFoundError."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            
            with pytest.raises(FileNotFoundError, match="File not found"):
                upload_to_webdav.apply(args=["/nonexistent/file.pdf"]).get()

    def test_http_error_response(self, sample_text_file):
        """Test handling of HTTP error responses (4xx, 5xx)."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            # Simulate 401 Unauthorized
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_put.return_value = mock_response
            
            with pytest.raises(Exception, match="Failed to upload.*401"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_http_404_not_found(self, sample_text_file):
        """Test handling of 404 Not Found response."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "nonexistent"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_put.return_value = mock_response
            
            with pytest.raises(Exception, match="Failed to upload.*404"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_http_500_server_error(self, sample_text_file):
        """Test handling of 500 Internal Server Error."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_put.return_value = mock_response
            
            with pytest.raises(Exception, match="Failed to upload.*500"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_connection_error(self, sample_text_file):
        """Test handling of connection errors."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            # Simulate connection error
            mock_put.side_effect = ConnectionError("Connection refused")
            
            with pytest.raises(Exception, match="Error uploading.*Connection refused"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_timeout_error(self, sample_text_file):
        """Test handling of timeout errors."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            # Simulate timeout
            mock_put.side_effect = Timeout("Request timed out")
            
            with pytest.raises(Exception, match="Error uploading.*timed out"):
                upload_to_webdav.apply(args=[sample_text_file]).get()

    def test_url_construction_with_trailing_slash(self, sample_text_file):
        """Test URL construction when base URL has trailing slash."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify URL construction
            called_url = mock_put.call_args[0][0]
            assert called_url.startswith("https://webdav.example.com/")
            assert "uploads" in called_url
            assert os.path.basename(sample_text_file) in called_url

    def test_url_construction_without_trailing_slash(self, sample_text_file):
        """Test URL construction when base URL has no trailing slash."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "documents"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify URL construction
            called_url = mock_put.call_args[0][0]
            assert "webdav.example.com" in called_url
            assert "documents" in called_url

    def test_folder_path_with_leading_slash(self, sample_text_file):
        """Test folder path normalization when it starts with /."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "/uploads/documents"  # Leading slash
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify the leading slash was removed in URL construction
            called_url = mock_put.call_args[0][0]
            # Should not have double slashes like //uploads
            assert "//" not in called_url.replace("https://", "")

    def test_empty_folder_path(self, sample_text_file):
        """Test upload with empty folder path (root directory)."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = ""  # Empty folder
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            assert result["status"] == "Completed"

    def test_ssl_verification_enabled(self, sample_text_file):
        """Test that SSL verification is enabled when configured."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify SSL verification was enabled
            call_kwargs = mock_put.call_args[1]
            assert call_kwargs["verify"] is True

    def test_ssl_verification_disabled(self, sample_text_file):
        """Test that SSL verification can be disabled."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = False
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify SSL verification was disabled
            call_kwargs = mock_put.call_args[1]
            assert call_kwargs["verify"] is False

    def test_authentication_credentials(self, sample_text_file):
        """Test that authentication credentials are properly passed."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "custom_user"
            mock_settings.webdav_password = _TEST_CUSTOM_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify correct credentials were used
            call_kwargs = mock_put.call_args[1]
            assert call_kwargs["auth"] == ("custom_user", _TEST_CUSTOM_CREDENTIAL)

    def test_logging_on_success(self, sample_text_file):
        """Test that progress is logged on successful upload."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress") as mock_log:
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            upload_to_webdav.apply(args=[sample_text_file], kwargs={"file_id": 42}).get()
            
            # Verify logging calls
            assert mock_log.call_count >= 2  # At least in_progress and success
            
            # Check for success log
            success_calls = [
                call for call in mock_log.call_args_list
                if call[0][2] == "success"
            ]
            assert len(success_calls) >= 1

    def test_logging_on_failure(self, sample_text_file):
        """Test that progress is logged on failed upload."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress") as mock_log:
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_put.return_value = mock_response
            
            with pytest.raises(Exception):
                upload_to_webdav.apply(args=[sample_text_file], kwargs={"file_id": 42}).get()
            
            # Check for failure log
            failure_calls = [
                call for call in mock_log.call_args_list
                if call[0][2] == "failure"
            ]
            assert len(failure_calls) >= 1

    def test_file_content_uploaded(self, sample_text_file):
        """Test that file content is actually read and uploaded."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Verify data was passed to PUT request
            call_kwargs = mock_put.call_args[1]
            assert "data" in call_kwargs
            # Data should be a file-like object from open()
            assert call_kwargs["data"] is not None

    def test_return_value_structure(self, sample_text_file):
        """Test that return value has correct structure."""
        with patch("app.tasks.upload_to_webdav.settings") as mock_settings, \
             patch("app.tasks.upload_to_webdav.requests.put") as mock_put, \
             patch("app.tasks.upload_to_webdav.log_task_progress"):
            
            mock_settings.webdav_url = "https://webdav.example.com/"
            mock_settings.webdav_username = "test_user"
            mock_settings.webdav_password = _TEST_CREDENTIAL
            mock_settings.webdav_folder = "uploads"
            mock_settings.webdav_verify_ssl = True
            mock_settings.http_request_timeout = 30
            
            mock_response = Mock()
            mock_response.status_code = 201
            mock_put.return_value = mock_response
            
            result = upload_to_webdav.apply(args=[sample_text_file]).get()
            
            # Check return value structure
            assert isinstance(result, dict)
            assert "status" in result
            assert "file" in result
            assert "url" in result
            assert result["status"] == "Completed"
            assert result["file"] == sample_text_file

    def test_module_importable(self):
        """Test that upload_to_webdav module is importable."""
        from app.tasks.upload_to_webdav import upload_to_webdav
        assert callable(upload_to_webdav)

    def test_task_has_retry_configuration(self):
        """Test that the task has retry configuration from BaseTaskWithRetry."""
        from app.tasks.upload_to_webdav import upload_to_webdav
        
        # BaseTaskWithRetry should provide retry configuration
        assert hasattr(upload_to_webdav, 'max_retries')
        # BaseTaskWithRetry configures 3 retries
        assert upload_to_webdav.max_retries == 3
