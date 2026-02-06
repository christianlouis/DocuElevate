import os
import unittest
from unittest.mock import patch, MagicMock
from app.utils.notification import notify_file_processed, send_notification
from app.config import settings


class TestFileProcessedNotification(unittest.TestCase):
    """Test file processing notification functionality"""
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_when_enabled(self, mock_send):
        """Test that notification is sent when NOTIFY_ON_FILE_PROCESSED is True"""
        # Arrange
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True
        
        filename = "test_document.pdf"
        file_size = 1024 * 1024  # 1 MB
        metadata = {
            'document_type': 'Invoice',
            'tags': ['financial', 'urgent']
        }
        destinations = ['Dropbox', 'Google Drive']
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertTrue(result)
            mock_send.assert_called_once()
            
            # Check the call arguments
            call_args = mock_send.call_args
            self.assertIn("test_document.pdf", call_args[1]['title'])
            self.assertIn("Invoice", call_args[1]['message'])
            self.assertIn("financial, urgent", call_args[1]['message'])
            self.assertIn("Dropbox, Google Drive", call_args[1]['message'])
            self.assertEqual(call_args[1]['notification_type'], "success")
        finally:
            settings.notify_on_file_processed = original_value
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_when_disabled(self, mock_send):
        """Test that notification is not sent when NOTIFY_ON_FILE_PROCESSED is False"""
        # Arrange
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = False
        
        filename = "test_document.pdf"
        file_size = 1024 * 1024
        metadata = {'document_type': 'Invoice', 'tags': []}
        destinations = ['Dropbox']
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertFalse(result)
            mock_send.assert_not_called()
        finally:
            settings.notify_on_file_processed = original_value
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_with_no_destinations(self, mock_send):
        """Test notification when no destinations are configured"""
        # Arrange
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True
        
        filename = "test_document.pdf"
        file_size = 512 * 1024  # 512 KB
        metadata = {
            'document_type': 'Receipt',
            'tags': []
        }
        destinations = []
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertTrue(result)
            mock_send.assert_called_once()
            
            # Check that message indicates no destinations
            call_args = mock_send.call_args
            self.assertIn("None configured", call_args[1]['message'])
        finally:
            settings.notify_on_file_processed = original_value
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_formats_file_size_mb(self, mock_send):
        """Test that file size is formatted correctly for MB"""
        # Arrange
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True
        
        filename = "large_document.pdf"
        file_size = 5 * 1024 * 1024  # 5 MB
        metadata = {'document_type': 'Contract', 'tags': []}
        destinations = ['Dropbox']
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertTrue(result)
            call_args = mock_send.call_args
            self.assertIn("5.00 MB", call_args[1]['message'])
        finally:
            settings.notify_on_file_processed = original_value
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_formats_file_size_kb(self, mock_send):
        """Test that file size is formatted correctly for KB"""
        # Arrange
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True
        
        filename = "small_document.pdf"
        file_size = 512 * 1024  # 512 KB
        metadata = {'document_type': 'Note', 'tags': []}
        destinations = ['Dropbox']
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertTrue(result)
            call_args = mock_send.call_args
            self.assertIn("512.00 KB", call_args[1]['message'])
        finally:
            settings.notify_on_file_processed = original_value
    
    @patch('app.utils.notification.send_notification')
    def test_notify_file_processed_with_missing_metadata_fields(self, mock_send):
        """Test that notification handles missing metadata fields gracefully"""
        # Arrange
        mock_send.return_value = True
        original_value = settings.notify_on_file_processed
        settings.notify_on_file_processed = True
        
        filename = "document.pdf"
        file_size = 1024 * 1024
        metadata = {}  # Empty metadata
        destinations = ['Dropbox']
        
        try:
            # Act
            result = notify_file_processed(filename, file_size, metadata, destinations)
            
            # Assert
            self.assertTrue(result)
            mock_send.assert_called_once()
            
            # Check that defaults are used
            call_args = mock_send.call_args
            self.assertIn("Unknown", call_args[1]['message'])  # Default document type
            self.assertIn("None", call_args[1]['message'])  # No tags
        finally:
            settings.notify_on_file_processed = original_value


if __name__ == '__main__':
    unittest.main()
