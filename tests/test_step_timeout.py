"""
Tests for app/utils/step_timeout.py

This module tests step timeout detection and handling logic.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestStepTimeout:
    """Test step timeout utilities."""

    @patch("app.utils.step_timeout.settings")
    def test_get_step_timeout_default(self, mock_settings):
        """Test get_step_timeout returns default value."""
        from app.utils.step_timeout import DEFAULT_STEP_TIMEOUT, get_step_timeout

        # No custom timeout in settings
        del mock_settings.step_timeout

        timeout = get_step_timeout()
        assert timeout == DEFAULT_STEP_TIMEOUT
        assert timeout == 600

    @patch("app.utils.step_timeout.settings")
    def test_get_step_timeout_custom(self, mock_settings):
        """Test get_step_timeout returns custom value from settings."""
        from app.utils.step_timeout import get_step_timeout

        # Custom timeout in settings
        mock_settings.step_timeout = 300

        timeout = get_step_timeout()
        assert timeout == 300

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_no_steps(self, mock_logger):
        """Test mark_stalled_steps_as_failed when no stalled steps exist."""
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Mock database session with proper query chain
        mock_db = MagicMock()
        # Set up the query chain to return empty list (single .filter() call with multiple conditions)
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Run function
        count = mark_stalled_steps_as_failed(mock_db)

        # No steps should be marked
        assert count == 0

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_with_stalled_steps(self, mock_logger):
        """Test mark_stalled_steps_as_failed marks stalled steps."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Create mock stalled steps
        step1 = MagicMock(spec=FileProcessingStep)
        step1.file_id = 1
        step1.step_name = "ocr"
        step1.status = "in_progress"
        step1.started_at = datetime.utcnow() - timedelta(seconds=700)

        step2 = MagicMock(spec=FileProcessingStep)
        step2.file_id = 2
        step2.step_name = "metadata"
        step2.status = "in_progress"
        step2.started_at = datetime.utcnow() - timedelta(seconds=800)

        # Mock database session
        mock_db = MagicMock()
        # Set up the query chain to return stalled steps (single .filter() call with multiple conditions)
        mock_db.query.return_value.filter.return_value.all.return_value = [step1, step2]

        # Run function
        count = mark_stalled_steps_as_failed(mock_db)

        # Both steps should be marked as failed
        assert count == 2
        assert step1.status == "failure"
        assert step2.status == "failure"
        assert step1.completed_at is not None
        assert step2.completed_at is not None
        assert "timeout" in step1.error_message.lower()
        assert "timeout" in step2.error_message.lower()
        mock_db.commit.assert_called_once()

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_custom_timeout(self, mock_logger):
        """Test mark_stalled_steps_as_failed with custom timeout."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Create mock step that's stalled with custom timeout
        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 1
        step.step_name = "ocr"
        step.status = "in_progress"
        step.started_at = datetime.utcnow() - timedelta(seconds=200)  # 200 seconds ago

        # Mock database session
        mock_db = MagicMock()
        # Set up the query chain to return stalled step (single .filter() call with multiple conditions)
        mock_db.query.return_value.filter.return_value.all.return_value = [step]

        # Run function with 150 second timeout
        count = mark_stalled_steps_as_failed(mock_db, timeout_seconds=150)

        # Step should be marked as failed
        assert count == 1
        assert step.status == "failure"
        assert "150 seconds" in step.error_message

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_for_specific_file(self, mock_logger):
        """Test mark_stalled_steps_as_failed for specific file."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Create mock stalled step
        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 42
        step.step_name = "ocr"
        step.status = "in_progress"
        step.started_at = datetime.utcnow() - timedelta(seconds=700)

        # Mock database session with file filter
        mock_db = MagicMock()
        # Set up the query chain with file filter (first .filter() for conditions, second for file_id)
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [step]

        # Run function for specific file
        count = mark_stalled_steps_as_failed(mock_db, file_id=42)

        # Step should be marked as failed
        assert count == 1
        assert step.status == "failure"

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_error_message_format(self, mock_logger):
        """Test that error message includes all necessary details."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Create mock stalled step
        started_time = datetime.utcnow() - timedelta(seconds=700)
        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 1
        step.step_name = "ocr"
        step.status = "in_progress"
        step.started_at = started_time

        # Mock database session
        mock_db = MagicMock()
        # Set up the query chain to return stalled step (single .filter() call with multiple conditions)
        mock_db.query.return_value.filter.return_value.all.return_value = [step]

        # Run function
        count = mark_stalled_steps_as_failed(mock_db, timeout_seconds=600)

        # Check error message content
        assert count == 1
        error_msg = step.error_message
        assert "600 seconds" in error_msg
        assert "timeout" in error_msg.lower()
        assert str(started_time) in error_msg

    @patch("app.utils.step_timeout.logger")
    def test_mark_stalled_steps_as_failed_logging(self, mock_logger):
        """Test that mark_stalled_steps_as_failed logs warnings and errors."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        # Create mock stalled step
        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 1
        step.step_name = "ocr"
        step.status = "in_progress"
        step.started_at = datetime.utcnow() - timedelta(seconds=700)

        # Mock database session
        mock_db = MagicMock()
        # Set up the query chain to return stalled step (single .filter() call with multiple conditions)
        mock_db.query.return_value.filter.return_value.all.return_value = [step]

        # Run function
        count = mark_stalled_steps_as_failed(mock_db)

        # Verify logging
        assert count == 1
        mock_logger.warning.assert_called_once()
        mock_logger.error.assert_called_once()

    @patch("app.utils.step_timeout.logger")
    def test_check_and_recover_stalled_file_found(self, mock_logger):
        """Test check_and_recover_stalled_file when stalled steps found."""
        from app.models import FileProcessingStep
        from app.utils.step_timeout import check_and_recover_stalled_file

        # Create mock stalled step
        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 42
        step.step_name = "ocr"
        step.status = "in_progress"
        step.started_at = datetime.utcnow() - timedelta(seconds=700)

        # Mock database session
        mock_db = MagicMock()
        # Set up the query chain with file filter (first .filter() for conditions, second for file_id)
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = [step]

        # Run function
        result = check_and_recover_stalled_file(mock_db, 42)

        # Should return True when stalled steps found
        assert result is True

    @patch("app.utils.step_timeout.logger")
    def test_check_and_recover_stalled_file_not_found(self, mock_logger):
        """Test check_and_recover_stalled_file when no stalled steps."""
        from app.utils.step_timeout import check_and_recover_stalled_file

        # Mock database session with no stalled steps
        mock_db = MagicMock()
        # Set up the query chain with file filter (first .filter() for conditions, second for file_id)
        mock_db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

        # Run function
        result = check_and_recover_stalled_file(mock_db, 42)

        # Should return False when no stalled steps
        assert result is False

    def test_default_step_timeout_constant(self):
        """Test that DEFAULT_STEP_TIMEOUT is defined correctly."""
        from app.utils.step_timeout import DEFAULT_STEP_TIMEOUT

        assert DEFAULT_STEP_TIMEOUT == 600
        assert isinstance(DEFAULT_STEP_TIMEOUT, int)
