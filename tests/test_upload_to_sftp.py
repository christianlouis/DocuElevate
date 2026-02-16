"""Tests for app/tasks/upload_to_sftp.py module."""

from unittest.mock import MagicMock, patch

import paramiko
import pytest

from app.tasks.upload_to_sftp import upload_to_sftp


@pytest.mark.unit
class TestUploadToSFTP:
    """Tests for SFTP upload functionality."""

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_with_key_authentication(self, mock_settings, mock_ssh_class, tmp_path):
        """Test SFTP upload using SSH key authentication."""
        # Setup
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = None
        mock_settings.sftp_private_key = str(tmp_path / "key.pem")
        mock_settings.sftp_private_key_passphrase = "passphrase"
        mock_settings.sftp_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = False

        # Create mock key file
        key_file = tmp_path / "key.pem"
        key_file.write_text("fake key")

        # Mock SSH and SFTP
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_sftp.stat.side_effect = FileNotFoundError
        mock_ssh_class.return_value = mock_ssh

        # Execute
        task = upload_to_sftp.apply(args=[str(test_file)])

        # Verify
        assert task.result["status"] == "Completed"
        mock_ssh.connect.assert_called_once()
        connect_kwargs = mock_ssh.connect.call_args[1]
        assert connect_kwargs["key_filename"] == str(tmp_path / "key.pem")
        assert connect_kwargs["passphrase"] == "passphrase"
        mock_sftp.put.assert_called_once()

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_with_password_authentication(self, mock_settings, mock_ssh_class, tmp_path):
        """Test SFTP upload using password authentication."""
        # Setup
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = "testpass"
        mock_settings.sftp_private_key = None
        mock_settings.sftp_folder = "/uploads"
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = False

        # Mock SSH and SFTP
        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_sftp.stat.side_effect = FileNotFoundError
        mock_ssh_class.return_value = mock_ssh

        # Execute
        task = upload_to_sftp.apply(args=[str(test_file)])

        # Verify
        assert task.result["status"] == "Completed"
        connect_kwargs = mock_ssh.connect.call_args[1]
        assert connect_kwargs["password"] == "testpass"
        assert "key_filename" not in connect_kwargs

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_with_disabled_host_key_verification(self, mock_settings, mock_ssh_class, tmp_path):
        """Test SFTP upload with host key verification disabled."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = "testpass"
        mock_settings.sftp_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = True

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_sftp.stat.side_effect = FileNotFoundError
        mock_ssh_class.return_value = mock_ssh

        # Execute
        task = upload_to_sftp.apply(args=[str(test_file)])

        # Verify AutoAddPolicy was set
        mock_ssh.set_missing_host_key_policy.assert_called()
        # Check that it was called with AutoAddPolicy (not RejectPolicy)
        call_arg = mock_ssh.set_missing_host_key_policy.call_args[0][0]
        assert isinstance(call_arg, paramiko.AutoAddPolicy)

    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_file_not_found(self, mock_settings):
        """Test SFTP upload with non-existent file."""
        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"

        with pytest.raises(FileNotFoundError):
            upload_to_sftp.apply(args=["/nonexistent/file.pdf"])

    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_missing_configuration(self, mock_settings, tmp_path):
        """Test SFTP upload with missing configuration."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = None
        mock_settings.sftp_port = None
        mock_settings.sftp_username = None

        result = upload_to_sftp.apply(args=[str(test_file)])

        assert result.result["status"] == "Skipped"
        assert "not configured" in result.result["reason"]

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_no_authentication_method(self, mock_settings, mock_ssh_class, tmp_path):
        """Test SFTP upload with no authentication method available."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = None
        mock_settings.sftp_private_key = None
        mock_settings.sftp_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = False

        mock_ssh = MagicMock()
        mock_ssh_class.return_value = mock_ssh

        with pytest.raises(Exception, match="No authentication method"):
            upload_to_sftp.apply(args=[str(test_file)])

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_creates_remote_directories(self, mock_settings, mock_ssh_class, tmp_path):
        """Test that remote directories are created as needed."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = "testpass"
        mock_settings.sftp_folder = "/remote/nested/path"
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = False

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        # Simulate directories not existing
        mock_sftp.stat.side_effect = FileNotFoundError
        mock_ssh_class.return_value = mock_ssh

        # Execute
        task = upload_to_sftp.apply(args=[str(test_file)])

        # Verify mkdir was called for each directory level
        mkdir_calls = [call[0][0] for call in mock_sftp.mkdir.call_args_list]
        assert any("/remote" in call for call in mkdir_calls)
        assert any("/remote/nested" in call for call in mkdir_calls)
        assert any("/remote/nested/path" in call for call in mkdir_calls)

    @patch("app.tasks.upload_to_sftp.paramiko.SSHClient")
    @patch("app.tasks.upload_to_sftp.settings")
    def test_upload_connection_error_cleanup(self, mock_settings, mock_ssh_class, tmp_path):
        """Test that connections are cleaned up on error."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        mock_settings.sftp_host = "sftp.example.com"
        mock_settings.sftp_port = 22
        mock_settings.sftp_username = "testuser"
        mock_settings.sftp_password = "testpass"
        mock_settings.sftp_folder = ""
        mock_settings.workdir = str(tmp_path)
        mock_settings.sftp_disable_host_key_verification = False

        mock_ssh = MagicMock()
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        mock_sftp.put.side_effect = Exception("Upload failed")
        mock_ssh_class.return_value = mock_ssh

        with pytest.raises(Exception, match="Upload failed"):
            upload_to_sftp.apply(args=[str(test_file)])

        # Verify cleanup was attempted
        mock_sftp.close.assert_called_once()
        mock_ssh.close.assert_called_once()
