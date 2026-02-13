"""
Tests for app/tasks/upload_with_rclone.py module.

Extends existing tests with comprehensive coverage for upload_with_rclone
and send_to_all_rclone_destinations Celery tasks.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from app.tasks.upload_with_rclone import send_to_all_rclone_destinations, upload_with_rclone


@pytest.mark.unit
class TestUploadWithRcloneExtended:
    """Extended tests for upload_with_rclone task."""

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_successful_upload(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test successful rclone upload."""
        mock_settings.workdir = str(tmp_path)

        # Create test file and rclone config
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        # Mock successful subprocess calls
        mock_mkdir = Mock()
        mock_mkdir.returncode = 0
        mock_upload = Mock()
        mock_upload.returncode = 0
        mock_upload.stdout = ""
        mock_upload.stderr = ""
        mock_link = Mock()
        mock_link.returncode = 0
        mock_link.stdout = "https://drive.google.com/file/abc123\n"

        mock_run.side_effect = [mock_mkdir, mock_upload, mock_link]

        result = upload_with_rclone(str(test_file), "gdrive:uploads")

        assert result["status"] == "Completed"
        assert result["destination"] == "gdrive:uploads"
        assert result["public_url"] == "https://drive.google.com/file/abc123"

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_successful_upload_no_public_url(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test successful upload when public link is not available."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        mock_mkdir = Mock()
        mock_mkdir.returncode = 0
        mock_upload = Mock()
        mock_upload.returncode = 0
        mock_link = Mock()
        mock_link.returncode = 1  # Public link not available

        mock_run.side_effect = [mock_mkdir, mock_upload, mock_link]

        result = upload_with_rclone(str(test_file), "gdrive:uploads")

        assert result["status"] == "Completed"
        assert result["public_url"] is None

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_upload_link_exception(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test that link failure does not fail the upload."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        mock_mkdir = Mock()
        mock_mkdir.returncode = 0
        mock_upload = Mock()
        mock_upload.returncode = 0

        # First two calls succeed, link raises exception
        mock_run.side_effect = [mock_mkdir, mock_upload, subprocess.SubprocessError("link failed")]

        result = upload_with_rclone(str(test_file), "gdrive:uploads")

        assert result["status"] == "Completed"
        assert result["public_url"] is None

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_mkdir_failure(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test rclone mkdir failure."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        mock_run.side_effect = subprocess.CalledProcessError(1, "rclone", stderr=b"mkdir failed")

        with pytest.raises(RuntimeError, match="Rclone error"):
            upload_with_rclone(str(test_file), "gdrive:uploads")

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_upload_command_failure(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test rclone copy command failure."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        mock_mkdir = Mock()
        mock_mkdir.returncode = 0

        mock_run.side_effect = [
            mock_mkdir,
            subprocess.CalledProcessError(1, "rclone", stderr="upload failed"),
        ]

        with pytest.raises(RuntimeError, match="Rclone error"):
            upload_with_rclone(str(test_file), "gdrive:uploads")

    @patch("app.tasks.upload_with_rclone.log_task_progress")
    def test_os_error_handling(self, mock_log, tmp_path):
        """Test OSError during rclone execution."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype = drive\n")

        with patch("app.tasks.upload_with_rclone.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)

            with patch("app.tasks.upload_with_rclone.subprocess.run", side_effect=OSError("Permission denied")):
                with pytest.raises(RuntimeError, match="Error uploading"):
                    upload_with_rclone(str(test_file), "gdrive:uploads")

    @patch("app.tasks.upload_with_rclone.log_task_progress")
    def test_validates_remote_name_special_chars(self, mock_log, tmp_path):
        """Test that special characters in remote name are rejected."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with pytest.raises(ValueError, match="Invalid remote name"):
            upload_with_rclone(str(test_file), "rem ote:path")

    @patch("app.tasks.upload_with_rclone.log_task_progress")
    def test_validates_remote_name_with_underscore_hyphen(self, mock_log, tmp_path):
        """Test that underscores and hyphens in remote names are valid."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with patch("app.tasks.upload_with_rclone.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            # No rclone.conf -> ValueError for config not found
            with pytest.raises(ValueError, match="Rclone configuration not found"):
                upload_with_rclone(str(test_file), "my-remote_1:path")


@pytest.mark.unit
class TestSendToAllRcloneDestinations:
    """Tests for send_to_all_rclone_destinations task."""

    def test_file_not_found(self):
        """Test raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            send_to_all_rclone_destinations("/nonexistent/file.pdf")

    @patch("app.tasks.upload_with_rclone.upload_with_rclone")
    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_successful_queue_to_all_destinations(self, mock_settings, mock_log, mock_run, mock_upload, tmp_path):
        """Test queuing uploads to all configured remotes."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype=drive\n[s3]\ntype=s3\n")

        mock_remotes = Mock()
        mock_remotes.returncode = 0
        mock_remotes.stdout = "gdrive:\ns3:\n"
        mock_run.return_value = mock_remotes

        mock_task = Mock()
        mock_task.id = "task-123"
        mock_upload.delay.return_value = mock_task

        result = send_to_all_rclone_destinations(str(test_file))

        assert result["status"] == "Queued"
        assert "tasks" in result
        assert len(result["tasks"]) == 2

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_no_rclone_config(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test error when rclone config is missing."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        with pytest.raises(ValueError, match="Rclone configuration not found"):
            send_to_all_rclone_destinations(str(test_file))

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_listremotes_failure(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test error when listremotes command fails."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype=drive\n")

        mock_run.side_effect = subprocess.SubprocessError("rclone not found")

        with pytest.raises(RuntimeError, match="Error setting up"):
            send_to_all_rclone_destinations(str(test_file))

    @patch("app.tasks.upload_with_rclone.upload_with_rclone")
    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_uses_custom_path_settings(self, mock_settings, mock_log, mock_run, mock_upload, tmp_path):
        """Test that custom path settings are used for each remote."""
        mock_settings.workdir = str(tmp_path)
        mock_settings.rclone_gdrive_path = "Documents/Uploads"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype=drive\n")

        mock_remotes = Mock()
        mock_remotes.returncode = 0
        mock_remotes.stdout = "gdrive:\n"
        mock_run.return_value = mock_remotes

        mock_task = Mock()
        mock_task.id = "task-123"
        mock_upload.delay.return_value = mock_task

        result = send_to_all_rclone_destinations(str(test_file))

        assert result["status"] == "Queued"
        # Check the destination includes the custom path
        call_args = mock_upload.delay.call_args
        assert "Documents/Uploads" in call_args[0][1]

    @patch("app.tasks.upload_with_rclone.subprocess.run")
    @patch("app.tasks.upload_with_rclone.log_task_progress")
    @patch("app.tasks.upload_with_rclone.settings")
    def test_listremotes_nonzero_return_code(self, mock_settings, mock_log, mock_run, tmp_path):
        """Test error when listremotes returns non-zero exit code."""
        mock_settings.workdir = str(tmp_path)

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test content")

        rclone_config = tmp_path / "rclone.conf"
        rclone_config.write_text("[gdrive]\ntype=drive\n")

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "config error"
        mock_run.return_value = mock_result

        with pytest.raises(RuntimeError, match="Failed to list rclone remotes"):
            send_to_all_rclone_destinations(str(test_file))
