"""
Tests for app/utils/logging.py

Tests task progress logging functionality.
"""

import logging
from unittest.mock import MagicMock, Mock, patch

import pytest


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
            detail=None,
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
        log_task_progress(task_id="task-456", step_name="upload", status="completed", message=None, file_id=None)

        # Verify called with None for optional parameters
        mock_processing_log.assert_called_once_with(
            task_id="task-456", step_name="upload", status="completed", message=None, file_id=None, detail=None
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
        log_task_progress(task_id="task-789", step_name="metadata", status="running", message="Extracting metadata")

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
            detail=None,
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

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    def test_log_task_progress_with_explicit_detail(self, mock_processing_log, mock_session_local):
        """Test logging with explicit detail preserves it."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_log_entry = Mock()
        mock_processing_log.return_value = mock_log_entry

        log_task_progress(
            task_id="task-explicit",
            step_name="test_step",
            status="success",
            message="Short message",
            detail="Verbose detail output",
        )

        mock_processing_log.assert_called_once_with(
            task_id="task-explicit",
            step_name="test_step",
            status="success",
            message="Short message",
            file_id=None,
            detail="Verbose detail output",
        )


@pytest.mark.unit
class TestTaskLogCollector:
    """Test the TaskLogCollector handler."""

    def test_collector_buffers_log_messages(self):
        """Test that the collector buffers messages by task ID."""
        from app.utils.logging import TaskLogCollector

        collector = TaskLogCollector()
        collector.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_collector")
        logger.addHandler(collector)
        logger.setLevel(logging.DEBUG)

        logger.info("[abc12345-task] Step 1 starting")
        logger.info("[abc12345-task] Step 1 complete")
        logger.info("[other-task-id] Different task")

        result = collector.drain("abc12345-task")
        assert "Step 1 starting" in result
        assert "Step 1 complete" in result
        assert "Different task" not in result

        # After drain, buffer should be empty
        assert collector.drain("abc12345-task") == ""

        # Other task still has its messages
        result2 = collector.drain("other-task-id")
        assert "Different task" in result2

        logger.removeHandler(collector)

    def test_collector_ignores_short_ids(self):
        """Test that the collector ignores short bracketed strings."""
        from app.utils.logging import TaskLogCollector

        collector = TaskLogCollector()
        collector.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_short_ids")
        logger.addHandler(collector)
        logger.setLevel(logging.DEBUG)

        logger.info("[OK] short id")
        assert collector.drain("OK") == ""

        logger.removeHandler(collector)

    def test_collector_handles_malformed_brackets(self):
        """Test that the collector handles messages with [ but no ]."""
        from app.utils.logging import TaskLogCollector

        collector = TaskLogCollector()
        collector.setFormatter(logging.Formatter("%(message)s"))

        logger = logging.getLogger("test_malformed")
        logger.addHandler(collector)
        logger.setLevel(logging.DEBUG)

        logger.info("[no closing bracket")
        logger.info("no brackets at all")
        logger.info("")

        # Should not raise and should not buffer anything
        assert collector.drain("no closing bracket") == ""

        logger.removeHandler(collector)

    def test_collector_handles_exception_in_emit(self):
        """Test that the collector handles exceptions gracefully during emit."""
        from app.utils.logging import TaskLogCollector

        collector = TaskLogCollector()
        # Don't set a formatter to trigger an edge case

        logger = logging.getLogger("test_exception")
        logger.addHandler(collector)
        logger.setLevel(logging.DEBUG)

        # This should not raise even if format() fails
        try:
            # Try to trigger an exception by causing issues with bracket parsing
            logger.info("][ backwards brackets")
            # Should handle gracefully
        except Exception:
            pytest.fail("Collector should handle exceptions gracefully")

        logger.removeHandler(collector)


@pytest.mark.unit
class TestLogTaskProgressWithFileProcessingStep:
    """Test log_task_progress with FileProcessingStep interactions."""

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging.FileProcessingStep")
    @patch("app.utils.logging.datetime")
    def test_creates_new_file_processing_step_with_in_progress_status(
        self, mock_datetime, mock_file_step, mock_processing_log, mock_session_local
    ):
        """Test creating a new FileProcessingStep with in_progress status."""
        from app.utils.logging import log_task_progress

        # Setup mocks
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # No existing step record
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock datetime
        from datetime import datetime as dt
        from datetime import timezone

        mock_now = dt(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        # Mock FileProcessingStep creation
        mock_step = Mock()
        mock_file_step.return_value = mock_step

        log_task_progress(
            task_id="task-123",
            step_name="processing",
            status="in_progress",
            message="Starting processing",
            file_id=1,
        )

        # Verify FileProcessingStep was created with started_at
        mock_file_step.assert_called_once()
        call_kwargs = mock_file_step.call_args[1]
        assert call_kwargs["file_id"] == 1
        assert call_kwargs["step_name"] == "processing"
        assert call_kwargs["status"] == "in_progress"
        assert call_kwargs["started_at"] == mock_now
        assert call_kwargs["completed_at"] is None

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging.FileProcessingStep")
    @patch("app.utils.logging.datetime")
    def test_creates_new_file_processing_step_with_success_status(
        self, mock_datetime, mock_file_step, mock_processing_log, mock_session_local
    ):
        """Test creating a new FileProcessingStep with success status."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_db.query.return_value.filter.return_value.first.return_value = None

        from datetime import datetime as dt
        from datetime import timezone

        mock_now = dt(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        mock_step = Mock()
        mock_file_step.return_value = mock_step

        log_task_progress(
            task_id="task-456",
            step_name="upload",
            status="success",
            message="Upload complete",
            file_id=2,
        )

        call_kwargs = mock_file_step.call_args[1]
        assert call_kwargs["status"] == "success"
        assert call_kwargs["started_at"] is None  # Not in_progress
        assert call_kwargs["completed_at"] == mock_now  # success sets completed_at
        assert call_kwargs["error_message"] is None

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging.FileProcessingStep")
    @patch("app.utils.logging.datetime")
    def test_creates_new_file_processing_step_with_failure_status(
        self, mock_datetime, mock_file_step, mock_processing_log, mock_session_local
    ):
        """Test creating a new FileProcessingStep with failure status."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_db.query.return_value.filter.return_value.first.return_value = None

        from datetime import datetime as dt
        from datetime import timezone

        mock_now = dt(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        mock_step = Mock()
        mock_file_step.return_value = mock_step

        log_task_progress(
            task_id="task-789",
            step_name="convert",
            status="failure",
            message="Conversion failed",
            file_id=3,
        )

        call_kwargs = mock_file_step.call_args[1]
        assert call_kwargs["status"] == "failure"
        assert call_kwargs["completed_at"] == mock_now
        assert call_kwargs["error_message"] == "Conversion failed"

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging.datetime")
    def test_updates_existing_file_processing_step_in_progress_without_started_at(
        self, mock_datetime, mock_processing_log, mock_session_local
    ):
        """Test updating existing FileProcessingStep to in_progress when started_at is not set."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Existing step without started_at
        mock_existing_step = Mock()
        mock_existing_step.started_at = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing_step

        from datetime import datetime as dt
        from datetime import timezone

        mock_now = dt(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        log_task_progress(
            task_id="task-update",
            step_name="ocr",
            status="in_progress",
            message="OCR starting",
            file_id=4,
        )

        # Verify started_at was set
        assert mock_existing_step.started_at == mock_now
        assert mock_existing_step.status == "in_progress"

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging.datetime")
    def test_updates_existing_file_processing_step_to_failure_with_detail(
        self, mock_datetime, mock_processing_log, mock_session_local
    ):
        """Test updating existing FileProcessingStep to failure with detail."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        mock_existing_step = Mock()
        mock_existing_step.started_at = None
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing_step

        from datetime import datetime as dt
        from datetime import timezone

        mock_now = dt(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        mock_datetime.timezone = timezone

        log_task_progress(
            task_id="task-fail",
            step_name="metadata",
            status="failure",
            message=None,  # No message
            file_id=5,
            detail="Detailed error information",
        )

        # Verify error_message uses detail when message is None
        assert mock_existing_step.error_message == "Detailed error information"
        assert mock_existing_step.status == "failure"

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging._collector")
    @patch("app.utils.logging._ensure_collector_installed")
    def test_log_task_progress_collects_buffered_logs(
        self, mock_ensure, mock_collector, mock_processing_log, mock_session_local
    ):
        """Test that log_task_progress collects buffered logs when detail is not provided."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Mock collector to return buffered logs
        mock_collector.drain.return_value = "Buffered log line 1\nBuffered log line 2"

        log_task_progress(
            task_id="task-with-logs",
            step_name="test",
            status="success",
            message="Task complete",
        )

        # Verify collector was used
        mock_ensure.assert_called_once()
        mock_collector.drain.assert_called_once_with("task-with-logs")

        # Verify detail was set from collected logs
        call_kwargs = mock_processing_log.call_args[1]
        assert call_kwargs["detail"] == "Buffered log line 1\nBuffered log line 2"

    @patch("app.utils.logging.SessionLocal")
    @patch("app.utils.logging.ProcessingLog")
    @patch("app.utils.logging._collector")
    @patch("app.utils.logging._ensure_collector_installed")
    def test_log_task_progress_skips_collection_when_no_task_id(
        self, mock_ensure, mock_collector, mock_processing_log, mock_session_local
    ):
        """Test that log_task_progress skips collection when task_id is None."""
        from app.utils.logging import log_task_progress

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        log_task_progress(
            task_id=None,
            step_name="test",
            status="success",
            message="No task",
        )

        # Verify collector was NOT used
        mock_ensure.assert_not_called()
        mock_collector.drain.assert_not_called()


@pytest.mark.unit
class TestEnsureCollectorInstalled:
    """Test the _ensure_collector_installed function."""

    @patch("app.utils.logging._collector_installed", False)
    @patch("app.utils.logging.logging.getLogger")
    def test_ensure_collector_installed_adds_handler(self, mock_get_logger):
        """Test that _ensure_collector_installed adds handler when not installed."""
        from app.utils.logging import _collector, _ensure_collector_installed

        mock_root = Mock()
        mock_root.handlers = []
        mock_get_logger.return_value = mock_root

        _ensure_collector_installed()

        # Verify handler was added
        mock_root.addHandler.assert_called_once_with(_collector)

    @patch("app.utils.logging._collector_installed", False)
    @patch("app.utils.logging.logging.getLogger")
    def test_ensure_collector_installed_skips_if_already_in_handlers(self, mock_get_logger):
        """Test that _ensure_collector_installed doesn't add duplicate handler."""
        from app.utils.logging import _collector, _ensure_collector_installed

        mock_root = Mock()
        # Collector already in handlers
        mock_root.handlers = [_collector]
        mock_get_logger.return_value = mock_root

        _ensure_collector_installed()

        # Verify handler was NOT added again
        mock_root.addHandler.assert_not_called()
