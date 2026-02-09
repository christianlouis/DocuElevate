"""Tests for app/tasks/upload_with_rclone.py module."""
import os
import pytest
from unittest.mock import patch, MagicMock

from app.tasks.upload_with_rclone import upload_with_rclone


@pytest.mark.unit
class TestUploadWithRclone:
    """Tests for upload_with_rclone task."""

    def test_raises_file_not_found(self):
        """Test raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            upload_with_rclone("/nonexistent/file.pdf", "remote:path")

    def test_raises_value_error_invalid_destination(self, tmp_path):
        """Test raises ValueError for invalid destination format."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test")

        with pytest.raises(ValueError, match="Invalid destination format"):
            upload_with_rclone(str(test_file), "invalid_destination")

    def test_raises_value_error_invalid_remote_name(self, tmp_path):
        """Test raises ValueError for invalid remote name."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test")

        with pytest.raises(ValueError, match="Invalid remote name"):
            upload_with_rclone(str(test_file), ":path")

    def test_raises_value_error_no_config(self, tmp_path):
        """Test raises ValueError when rclone config not found."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"test")

        with patch("app.tasks.upload_with_rclone.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)

            with pytest.raises(ValueError, match="Rclone configuration not found"):
                upload_with_rclone(str(test_file), "gdrive:uploads")
