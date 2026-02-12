"""Comprehensive tests for app/tasks/upload_to_ftp.py to improve coverage."""

import ftplib
from unittest.mock import MagicMock, mock_open, patch

import pytest


class FakeFTPTLS:
    """Fake FTP_TLS class for testing (isinstance-compatible)."""

    def __init__(self):
        pass

    def connect(self, host, port):
        pass

    def login(self, user, passwd):
        pass

    def prot_p(self):
        pass

    def cwd(self, path):
        pass

    def storbinary(self, cmd, fp):
        pass

    def quit(self):
        pass

    def mkd(self, path):
        pass


class FakeFTP:
    """Fake FTP class for testing (isinstance-compatible)."""

    def __init__(self):
        pass

    def connect(self, host, port):
        pass

    def login(self, user, passwd):
        pass

    def cwd(self, path):
        pass

    def storbinary(self, cmd, fp):
        pass

    def quit(self):
        pass

    def mkd(self, path):
        pass


@pytest.mark.unit
class TestUploadToFtpTask:
    """Tests for upload_to_ftp Celery task."""

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    def test_file_not_found_raises(self, mock_exists, mock_log):
        """Test raises FileNotFoundError when file doesn't exist."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            upload_to_ftp("/nonexistent/file.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_ftp_host_not_configured_raises(self, mock_settings, mock_exists, mock_log):
        """Test raises ValueError when FTP host not configured."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = None

        with pytest.raises(ValueError, match="FTP host is not configured"):
            upload_to_ftp("/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_successful_ftps_upload(self, mock_settings, mock_exists, mock_log):
        """Test successful upload via FTPS."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FakeFTPTLS):
            result = upload_to_ftp("/tmp/test.pdf")
            assert result["status"] == "Completed"
            assert result["ftp_host"] == "ftp.example.com"
            assert result["used_tls"] is True

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_ftps_fallback_to_ftp(self, mock_settings, mock_exists, mock_log):
        """Test fallback to plain FTP when FTPS fails."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        class FailingFTPTLS:
            def __init__(self):
                pass

            def connect(self, host, port):
                raise Exception("TLS not supported")

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FailingFTPTLS):
            with patch("app.tasks.upload_to_ftp.ftplib.FTP", FakeFTP):
                result = upload_to_ftp("/tmp/test.pdf")
                assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_ftps_fails_plaintext_forbidden(self, mock_settings, mock_exists, mock_log):
        """Test raises when FTPS fails and plaintext is forbidden."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = False

        class FailingFTPTLS:
            def __init__(self):
                pass

            def connect(self, host, port):
                raise Exception("TLS failed")

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FailingFTPTLS):
            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_ftp("/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_plain_ftp_when_tls_disabled(self, mock_settings, mock_exists, mock_log):
        """Test plain FTP when TLS is explicitly disabled."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = True

        with patch("app.tasks.upload_to_ftp.ftplib.FTP", FakeFTP):
            result = upload_to_ftp("/tmp/test.pdf")
            assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_tls_disabled_plaintext_forbidden(self, mock_settings, mock_exists, mock_log):
        """Test raises when TLS disabled and plaintext forbidden."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_use_tls = False
        mock_settings.ftp_allow_plaintext = False

        with pytest.raises(Exception, match="Failed to upload"):
            upload_to_ftp("/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_upload_with_folder(self, mock_settings, mock_exists, mock_log):
        """Test upload to specific folder."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = "/documents/uploaded"
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FakeFTPTLS):
            result = upload_to_ftp("/tmp/test.pdf")
            assert result["status"] == "Completed"
            assert "/documents/uploaded" in result["ftp_path"]

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_upload_creates_folder_structure(self, mock_settings, mock_exists, mock_log):
        """Test creates folder structure when directory doesn't exist."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = "/new/folder"
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        class FTPTLSWithCwdFail(FakeFTPTLS):
            """FTP_TLS that fails on first cwd, then succeeds after mkd."""

            def __init__(self):
                super().__init__()
                self._cwd_calls = 0

            def cwd(self, path):
                self._cwd_calls += 1
                if self._cwd_calls <= 1:
                    raise ftplib.error_perm("550 No such directory")

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FTPTLSWithCwdFail):
            result = upload_to_ftp("/tmp/test.pdf")
            assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_folder_change_error(self, mock_settings, mock_exists, mock_log):
        """Test error when changing/creating directory."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = "/restricted"
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        class FTPTLSCwdFail(FakeFTPTLS):
            def cwd(self, path):
                raise ftplib.error_perm("550 Permission denied")

            def mkd(self, path):
                raise ftplib.Error("Cannot create directory")

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FTPTLSCwdFail):
            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_ftp("/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    def test_upload_storbinary_failure(self, mock_settings, mock_exists, mock_log):
        """Test failure during file transfer."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = 21
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        class FTPTLSStorFail(FakeFTPTLS):
            def storbinary(self, cmd, fp):
                raise Exception("Transfer error")

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FTPTLSStorFail):
            with pytest.raises(Exception, match="Failed to upload"):
                upload_to_ftp("/tmp/test.pdf")

    @patch("app.tasks.upload_to_ftp.log_task_progress")
    @patch("app.tasks.upload_to_ftp.os.path.exists")
    @patch("app.tasks.upload_to_ftp.settings")
    @patch("builtins.open", mock_open(read_data=b"%PDF-1.4"))
    def test_default_port(self, mock_settings, mock_exists, mock_log):
        """Test default port 21 is used when port is None."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        mock_exists.return_value = True
        mock_settings.ftp_host = "ftp.example.com"
        mock_settings.ftp_port = None
        mock_settings.ftp_username = "user"
        mock_settings.ftp_password = "pass"
        mock_settings.ftp_folder = None
        mock_settings.ftp_use_tls = True
        mock_settings.ftp_allow_plaintext = True

        connect_args = {}

        class FTPTLSCapture(FakeFTPTLS):
            def connect(self, host, port):
                connect_args["host"] = host
                connect_args["port"] = port

        with patch("app.tasks.upload_to_ftp.ftplib.FTP_TLS", FTPTLSCapture):
            result = upload_to_ftp("/tmp/test.pdf")
            assert result["status"] == "Completed"
            assert connect_args["port"] == 21
