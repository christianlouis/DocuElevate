"""Extended tests for app/tasks/check_credentials.py module."""
import pytest
from unittest.mock import patch, MagicMock

from app.tasks.check_credentials import (
    sync_test_openai_connection,
    sync_test_azure_connection,
    sync_test_dropbox_token,
    sync_test_google_drive_token,
    sync_test_onedrive_token,
)


@pytest.mark.unit
class TestSyncTestFunctions:
    """Tests for synchronous test wrapper functions."""

    @patch("app.tasks.check_credentials.test_openai_connection")
    def test_sync_openai_connection(self, mock_test):
        """Test sync_test_openai_connection wrapper."""
        # Mock the inner function
        mock_inner = MagicMock(return_value={"status": "error", "message": "test"})
        with patch("app.tasks.check_credentials.unwrap_decorated_function", return_value=mock_inner):
            result = sync_test_openai_connection()
            assert isinstance(result, dict)

    @patch("app.tasks.check_credentials.test_azure_connection")
    def test_sync_azure_connection(self, mock_test):
        """Test sync_test_azure_connection wrapper."""
        mock_inner = MagicMock(return_value={"status": "error", "message": "test"})
        with patch("app.tasks.check_credentials.unwrap_decorated_function", return_value=mock_inner):
            result = sync_test_azure_connection()
            assert isinstance(result, dict)

    @patch("app.tasks.check_credentials.test_dropbox_token")
    def test_sync_dropbox_token(self, mock_test):
        """Test sync_test_dropbox_token wrapper."""
        mock_inner = MagicMock(return_value={"status": "error", "message": "test"})
        with patch("app.tasks.check_credentials.unwrap_decorated_function", return_value=mock_inner):
            result = sync_test_dropbox_token()
            assert isinstance(result, dict)

    @patch("app.tasks.check_credentials.test_google_drive_token")
    def test_sync_google_drive_token(self, mock_test):
        """Test sync_test_google_drive_token wrapper."""
        mock_inner = MagicMock(return_value={"status": "error", "message": "test"})
        with patch("app.tasks.check_credentials.unwrap_decorated_function", return_value=mock_inner):
            result = sync_test_google_drive_token()
            assert isinstance(result, dict)

    @patch("app.tasks.check_credentials.test_onedrive_token")
    def test_sync_onedrive_token(self, mock_test):
        """Test sync_test_onedrive_token wrapper."""
        mock_inner = MagicMock(return_value={"status": "error", "message": "test"})
        with patch("app.tasks.check_credentials.unwrap_decorated_function", return_value=mock_inner):
            result = sync_test_onedrive_token()
            assert isinstance(result, dict)
