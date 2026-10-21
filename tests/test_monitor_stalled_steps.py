"""
Tests for app/tasks/monitor_stalled_steps.py

This module tests the periodic task that monitors and recovers stalled processing steps.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError


@pytest.mark.unit
class TestMonitorStalledSteps:
    """Test monitor_stalled_steps task."""

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_monitor_stalled_steps_no_stalled(self, mock_session_local, mock_mark_stalled):
        """Test monitor_stalled_steps when no stalled steps found."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # No stalled steps
        mock_mark_stalled.return_value = 0

        # Run task
        result = monitor_stalled_steps()

        # Verify result
        assert result == {"recovered": 0}
        mock_mark_stalled.assert_called_once_with(mock_db)

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_monitor_stalled_steps_with_stalled(self, mock_session_local, mock_mark_stalled):
        """Test monitor_stalled_steps when stalled steps are found."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Found 3 stalled steps
        mock_mark_stalled.return_value = 3

        # Run task
        result = monitor_stalled_steps()

        # Verify result
        assert result == {"recovered": 3}
        mock_mark_stalled.assert_called_once_with(mock_db)

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    @patch("app.tasks.monitor_stalled_steps.logger")
    def test_monitor_stalled_steps_logs_recovery(self, mock_logger, mock_session_local, mock_mark_stalled):
        """Test that monitor_stalled_steps logs recovery actions."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Found 2 stalled steps
        mock_mark_stalled.return_value = 2

        # Run task
        result = monitor_stalled_steps()

        # Verify logging
        mock_logger.warning.assert_called_once()
        log_message = mock_logger.warning.call_args[0][0]
        assert "Recovered 2 stalled step(s)" in log_message

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    @patch("app.tasks.monitor_stalled_steps.logger")
    def test_monitor_stalled_steps_logs_debug_when_none(self, mock_logger, mock_session_local, mock_mark_stalled):
        """Test that monitor_stalled_steps logs debug message when no stalled steps."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # No stalled steps
        mock_mark_stalled.return_value = 0

        # Run task
        result = monitor_stalled_steps()

        # Verify debug logging
        mock_logger.debug.assert_called_once()
        log_message = mock_logger.debug.call_args[0][0]
        assert "No stalled steps found" in log_message

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    @patch("app.tasks.monitor_stalled_steps.logger")
    def test_monitor_stalled_steps_handles_exceptions(self, mock_logger, mock_session_local, mock_mark_stalled):
        """Test that monitor_stalled_steps handles exceptions gracefully."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        # Simulate an exception
        mock_mark_stalled.side_effect = Exception("Database error")

        # Run task
        result = monitor_stalled_steps()

        # Verify error handling
        assert result == {"error": "Database error", "recovered": 0}
        mock_logger.error.assert_called_once()

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_monitor_stalled_steps_uses_context_manager(self, mock_session_local, mock_mark_stalled):
        """Test that monitor_stalled_steps uses context manager for database session."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Mock database session
        mock_db = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_db)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_session_local.return_value = mock_context

        mock_mark_stalled.return_value = 0

        # Run task
        result = monitor_stalled_steps()

        # Verify context manager was used
        mock_context.__enter__.assert_called_once()
        mock_context.__exit__.assert_called_once()

    def test_monitor_stalled_steps_is_celery_task(self):
        """Test that monitor_stalled_steps is registered as a Celery task."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Should have task attributes
        assert hasattr(monitor_stalled_steps, "apply_async")
        assert hasattr(monitor_stalled_steps, "delay")
        assert callable(monitor_stalled_steps)

    def test_monitor_stalled_steps_task_name(self):
        """Test that monitor_stalled_steps has correct task name."""
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        # Check task name
        assert monitor_stalled_steps.name == "app.tasks.monitor_stalled_steps.monitor_stalled_steps"

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_transient_query_error_retries_with_fresh_session(self, mock_session_local, mock_mark_stalled):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        first, second = MagicMock(), MagicMock()
        first.__enter__.side_effect = OperationalError("unexpected EOF", None, None)
        second.__enter__.return_value = MagicMock()
        mock_session_local.side_effect = [first, second]
        mock_mark_stalled.return_value = 0

        assert monitor_stalled_steps() == {"recovered": 0}
        assert mock_session_local.call_count == 2

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_transient_commit_error_retries_and_returns_recovered(self, mock_session_local, mock_mark_stalled):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        first_db, second_db = MagicMock(), MagicMock()
        first_db.__enter__.return_value = first_db
        second_db.__enter__.return_value = second_db
        first, second = first_db, second_db
        mock_session_local.side_effect = [first, second]
        mock_mark_stalled.side_effect = [
            OperationalError("SSL bad record mac", None, None),
            1,
        ]

        assert monitor_stalled_steps() == {"recovered": 1}
        assert mock_session_local.call_count == 2

    @pytest.mark.parametrize("message", ["syntax error", "permission denied"])
    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_nontransient_error_is_terminal(self, mock_session_local, mock_mark_stalled, message):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        db = MagicMock()
        db.__enter__.return_value = db
        mock_session_local.return_value = db
        mock_mark_stalled.side_effect = OperationalError(message, None, None)

        result = monitor_stalled_steps()
        assert result["recovered"] == 0
        assert "error" in result
        mock_session_local.assert_called_once_with()

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_transient_errors_exhaust_bounded_attempts(self, mock_session_local, mock_mark_stalled):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        db = MagicMock()
        db.__enter__.return_value = db
        mock_session_local.return_value = db
        mock_mark_stalled.side_effect = OperationalError("connection reset by peer", None, None)

        result = monitor_stalled_steps()
        assert result["recovered"] == 0
        assert "error" in result
        assert mock_session_local.call_count == 3
