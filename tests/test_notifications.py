import pytest

from app.config import settings
from app.utils.notification import notify_file_processed, send_notification


@pytest.mark.unit
class TestFileProcessedNotification:
    """Test file processing notification functionality"""

    def test_notify_file_processed_when_enabled(self, mocker):
        """Test that notification is sent when NOTIFY_ON_FILE_PROCESSED is True"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True

        filename = "test_document.pdf"
        file_size = 1024 * 1024  # 1 MB
        metadata = {"document_type": "Invoice", "tags": ["financial", "urgent"]}
        destinations = ["Dropbox", "Google Drive"]

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is True
            mock_send.assert_called_once()

            # Check the call arguments
            call_args = mock_send.call_args
            assert "test_document.pdf" in call_args[1]["title"]
            assert "Invoice" in call_args[1]["message"]
            assert "financial, urgent" in call_args[1]["message"]
            assert "Dropbox, Google Drive" in call_args[1]["message"]
            assert call_args[1]["notification_type"] == "success"
        finally:
            settings.notify_on_file_processed = original_value

    def test_notify_file_processed_when_disabled(self, mocker):
        """Test that notification is not sent when NOTIFY_ON_FILE_PROCESSED is False"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = False

        filename = "test_document.pdf"
        file_size = 1024 * 1024
        metadata = {"document_type": "Invoice", "tags": []}
        destinations = ["Dropbox"]

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is False
            mock_send.assert_not_called()
        finally:
            settings.notify_on_file_processed = original_value

    def test_notify_file_processed_with_no_destinations(self, mocker):
        """Test notification when no destinations are configured"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True

        filename = "test_document.pdf"
        file_size = 512 * 1024  # 512 KB
        metadata = {"document_type": "Receipt", "tags": []}
        destinations = []

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is True
            mock_send.assert_called_once()

            # Check that message indicates no destinations
            call_args = mock_send.call_args
            assert "None configured" in call_args[1]["message"]
        finally:
            settings.notify_on_file_processed = original_value

    def test_notify_file_processed_formats_file_size_mb(self, mocker):
        """Test that file size is formatted correctly for MB"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True

        filename = "large_document.pdf"
        file_size = 5 * 1024 * 1024  # 5 MB
        metadata = {"document_type": "Contract", "tags": []}
        destinations = ["Dropbox"]

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is True
            call_args = mock_send.call_args
            assert "5.00 MB" in call_args[1]["message"]
        finally:
            settings.notify_on_file_processed = original_value

    def test_notify_file_processed_formats_file_size_kb(self, mocker):
        """Test that file size is formatted correctly for KB"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True

        filename = "small_document.pdf"
        file_size = 512 * 1024  # 512 KB
        metadata = {"document_type": "Note", "tags": []}
        destinations = ["Dropbox"]

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is True
            call_args = mock_send.call_args
            assert "512.00 KB" in call_args[1]["message"]
        finally:
            settings.notify_on_file_processed = original_value

    def test_notify_file_processed_with_missing_metadata_fields(self, mocker):
        """Test that notification handles missing metadata fields gracefully"""
        # Arrange
        mock_send = mocker.patch("app.utils.notification.send_notification")
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True

        filename = "document.pdf"
        file_size = 1024 * 1024
        metadata = {}  # Empty metadata
        destinations = ["Dropbox"]

        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)

            # Assert
            assert result is True
            mock_send.assert_called_once()

            # Check that defaults are used
            call_args = mock_send.call_args
            assert "Unknown" in call_args[1]["message"]  # Default document type
            assert "None" in call_args[1]["message"]  # No tags
        finally:
            settings.notify_on_file_processed = original_value
