"""Additional tests for upload_to_ftp task."""

import ftplib
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.tasks.upload_to_ftp import upload_to_ftp


@pytest.mark.unit
class TestUploadToFtp:
    """Tests for upload_to_ftp task."""

    def test_module_imports(self):
        """Test that the module can be imported."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        assert callable(upload_to_ftp)

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_uploads_file_with_ftps(self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp_tls):
        """Test uploads file using FTPS (FTP with TLS)."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = "/uploads"
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        mock_ftp = Mock()
        mock_ftp_tls.return_value = mock_ftp

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_ftp(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Completed"
        assert result["used_tls"] is True
        mock_ftp.login.assert_called_once()
        mock_ftp.prot_p.assert_called_once()

    @patch("app.tasks.upload_to_ftp.ftplib.FTP")
    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_falls_back_to_plaintext_ftp(
        self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp_tls, mock_ftp
    ):
        """Test falls back to plaintext FTP when FTPS fails."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        # FTPS fails
        mock_ftp_tls_instance = Mock()
        mock_ftp_tls_instance.connect.side_effect = Exception("TLS not supported")
        mock_ftp_tls.return_value = mock_ftp_tls_instance

        # Plaintext FTP succeeds
        mock_ftp_instance = Mock()
        mock_ftp.return_value = mock_ftp_instance

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_ftp(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Completed"
        assert result["used_tls"] is False

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_raises_error_when_ftps_fails_and_plaintext_forbidden(
        self, mock_settings, mock_exists, mock_log, mock_ftp_tls
    ):
        """Test raises error when FTPS fails and plaintext is forbidden."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = False

        mock_ftp_tls_instance = Mock()
        mock_ftp_tls_instance.connect.side_effect = Exception("TLS not supported")
        mock_ftp_tls.return_value = mock_ftp_tls_instance

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="FTPS connection failed and plaintext FTP is forbidden"):
            upload_to_ftp(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    def test_raises_error_when_file_not_found(self, mock_exists, mock_log):
        """Test raises error when file not found."""
        mock_exists.return_value = False

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(FileNotFoundError):
            upload_to_ftp(mock_self, "/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_raises_error_when_ftp_host_not_configured(self, mock_settings, mock_exists, mock_log):
        """Test raises error when FTP host not configured."""
        mock_exists.return_value = True
        mock_settings.ftp_host = None

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(ValueError, match="FTP host is not configured"):
            upload_to_ftp(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_creates_directory_structure(self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp_tls):
        """Test creates directory structure if it doesn't exist."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = "/uploads/documents"
        mock_settings.ftp_use_tls = True

        mock_ftp = Mock()
        mock_ftp.cwd.side_effect = [ftplib.error_perm("No such directory"), None]
        mock_ftp_tls.return_value = mock_ftp

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_ftp(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Completed"
        mock_ftp.mkd.assert_called()

    @patch("app.tasks.upload_to_ftp.ftplib.FTP")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_uses_plaintext_ftp_when_tls_disabled(self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp):
        """Test uses plaintext FTP when TLS is explicitly disabled."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = True

        mock_ftp_instance = Mock()
        mock_ftp.return_value = mock_ftp_instance

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_ftp(mock_self, "/tmp/test.pdf")

        assert result["status"] == "Completed"
        assert result["used_tls"] is False

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_raises_error_when_plaintext_forbidden_and_tls_disabled(self, mock_settings, mock_exists, mock_log):
        """Test raises error when plaintext is forbidden and TLS is disabled."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = False

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Plaintext FTP is forbidden"):
            upload_to_ftp(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_removes_leading_slash_from_folder(self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp_tls):
        """Test removes leading slash from folder path."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = "/uploads"
        mock_settings.ftp_use_tls = True

        mock_ftp = Mock()
        mock_ftp_tls.return_value = mock_ftp

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        upload_to_ftp(mock_self, "/tmp/test.pdf")

        # Verify cwd was called with folder without leading slash
        mock_ftp.cwd.assert_called_with("uploads")

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_handles_directory_creation_error(self, mock_settings, mock_exists, mock_log, mock_ftp_tls):
        """Test handles directory creation error."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = "/uploads"
        mock_settings.ftp_use_tls = True

        mock_ftp = Mock()
        mock_ftp.cwd.side_effect = ftplib.error_perm("Permission denied")
        mock_ftp.mkd.side_effect = ftplib.error_perm("Cannot create directory")
        mock_ftp_tls.return_value = mock_ftp

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        with pytest.raises(Exception, match="Failed to change/create directory"):
            upload_to_ftp(mock_self, "/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS")
    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", create=True)
    def test_returns_ftp_path_in_result(self, mock_open, mock_settings, mock_exists, mock_log, mock_ftp_tls):
        """Test returns FTP path in result."""
        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "password"
        mock_settings.ftp_folder = "/uploads"
        mock_settings.ftp_use_tls = True

        mock_ftp = Mock()
        mock_ftp_tls.return_value = mock_ftp

        mock_self = Mock()
        mock_self.request.id = "test-task-id"

        result = upload_to_ftp(mock_self, "/tmp/test.pdf")

        assert "ftp_path" in result
        assert result["ftp_path"] == "/uploads/test.pdf"
