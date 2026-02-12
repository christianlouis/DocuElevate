"""Additional tests for upload task modules."""

import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestUploadToNextcloud:
    """Tests for upload_to_nextcloud task."""

    @patch("app.tasks.upload_to_nextcloud.requests")
    @patch("app.tasks.upload_to_nextcloud.log_task_progress")
    def test_upload_no_url_configured(self, mock_log, mock_requests):
        """Test upload when nextcloud URL is not configured."""
        mock_self = MagicMock()
        mock_self.request.id = "test-task"

        with patch("app.tasks.upload_to_nextcloud.settings") as mock_settings:
            mock_settings.nextcloud_upload_url = None
            mock_settings.nextcloud_username = None
            mock_settings.nextcloud_password = None
            mock_settings.nextcloud_folder = None
            mock_settings.workdir = "/tmp"

            from app.tasks.upload_to_nextcloud import upload_to_nextcloud

            result = upload_to_nextcloud.__wrapped__(mock_self, "/nonexistent/file.pdf")


@pytest.mark.unit
class TestUploadToDropbox:
    """Tests for upload_to_dropbox task."""

    def test_validate_dropbox_settings_missing_all(self):
        """Test validation when all Dropbox settings are missing."""
        from app.tasks.upload_to_dropbox import _validate_dropbox_settings

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_app_key = None
            mock_settings.dropbox_app_secret = None

            result = _validate_dropbox_settings()
            assert result is False

    def test_get_dropbox_access_token_no_settings(self):
        """Test get_dropbox_access_token when settings are missing."""
        from app.tasks.upload_to_dropbox import get_dropbox_access_token

        with patch("app.tasks.upload_to_dropbox.settings") as mock_settings:
            mock_settings.dropbox_refresh_token = None
            mock_settings.dropbox_app_key = None
            mock_settings.dropbox_app_secret = None

            result = get_dropbox_access_token()
            assert result is None
