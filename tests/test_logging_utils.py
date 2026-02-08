"""
Tests for app/utils/logging.py

Tests task progress logging functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.mark.unit
class TestTaskLogging:
    """Test task progress logging"""

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_basic(self, mock_processing_log, mock_session_local):
        """Test basic task progress logging"""
        from app.utils.logging import log_task_progress

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Mock ProcessingLog model
        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        # Call the function
        log_task_progress(
            task_id="task-123",
            step_name="processing",
            status="started",
            message="Processing document",
            file_id=456,
        )

        # Verify ProcessingLog was created with correct parameters
        mock_processing_log.assert_called_once_with(
            task_id="task-123",
            step_name="processing",
            status="started",
            message="Processing document",
            file_id=456,
        )

        # Verify database operations
        mock_db.add.assert_called_once_with(mock_log_entry)
        mock_db.commit.assert_called_once()

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_without_message(self, mock_processing_log, mock_session_local):
        """Test logging without message"""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        # Call without message
        log_task_progress(
            task_id="task-456", step_name="upload", status="completed", message=None, file_id=None
        )

        # Verify called with None for optional parameters
        mock_processing_log.assert_called_once_with(
            task_id="task-456", step_name="upload", status="completed", message=None, file_id=None
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_without_file_id(self, mock_processing_log, mock_session_local):
        """Test logging without file_id"""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        # Call without file_id
        log_task_progress(
            task_id="task-789", step_name="metadata", status="running", message="Extracting metadata"
        )

        # file_id should default to None
        mock_processing_log.assert_called_once()
        call_args = mock_processing_log.call_args
        assert call_args[1]["task_id"] == "task-789"
        assert call_args[1]["step_name"] == "metadata"
        assert call_args[1]["status"] == "running"

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_all_parameters(self, mock_processing_log, mock_session_local):
        """Test logging with all parameters"""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        # Call with all parameters
        log_task_progress(
            task_id="task-complete",
            step_name="finalization",
            status="success",
            message="Document processed successfully",
            file_id=999,
        )

        mock_processing_log.assert_called_once_with(
            task_id="task-complete",
            step_name="finalization",
            status="success",
            message="Document processed successfully",
            file_id=999,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_session_context_manager(self, mock_processing_log, mock_session_local):
        """Test that database session is properly managed with context manager"""
        from app.utils.logging import log_task_progress

        mock_session_context = MagicMock()
        mock_session_local.return_value = mock_session_context

        mock_db = MagicMock()
        mock_session_context.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        log_task_progress(task_id="test", step_name="test", status="test")

        # Verify context manager was used
        mock_session_context.__enter__.assert_called_once()
        mock_session_context.__exit__.assert_called_once()

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_with_different_statuses(self, mock_processing_log, mock_session_local):
        """Test logging with various status values"""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        statuses = ["pending", "processing", "completed", "failed", "error"]

        for status in statuses:
            log_task_progress(task_id=f"task-{status}", step_name="test", status=status)

            # Should be called for each status
            assert mock_processing_log.called
            mock_db.add.assert_called()
            mock_db.commit.assert_called()
