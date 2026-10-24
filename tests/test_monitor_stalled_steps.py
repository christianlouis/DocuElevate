"""
Tests for app/tasks/monitor_stalled_steps.py

This module tests the periodic task that monitors and recovers stalled processing steps.
"""

from datetime import datetime, timedelta, timezone
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

        # Terminal failures must reach Celery as failures.
        with pytest.raises(Exception, match="Database error"):
            monitor_stalled_steps()
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
    @patch("app.tasks.monitor_stalled_steps.time.sleep")
    def test_transient_query_error_retries_with_fresh_session(self, mock_sleep, mock_session_local, mock_mark_stalled):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        first, second = MagicMock(), MagicMock()
        first.__enter__.side_effect = OperationalError("unexpected EOF", None, None)
        second.__enter__.return_value = MagicMock()
        mock_session_local.side_effect = [first, second]
        mock_mark_stalled.return_value = 0

        assert monitor_stalled_steps() == {"recovered": 0}
        assert mock_session_local.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    @patch("app.tasks.monitor_stalled_steps.time.sleep")
    def test_transient_commit_error_retries_and_returns_recovered(
        self, mock_sleep, mock_session_local, mock_mark_stalled
    ):
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

        with pytest.raises(OperationalError):
            monitor_stalled_steps()
        mock_session_local.assert_called_once_with()

    @patch("app.tasks.monitor_stalled_steps.mark_stalled_steps_as_failed")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    @patch("app.tasks.monitor_stalled_steps.time.sleep")
    def test_transient_errors_exhaust_bounded_attempts(self, mock_sleep, mock_session_local, mock_mark_stalled):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        db = MagicMock()
        db.__enter__.return_value = db
        mock_session_local.return_value = db
        mock_mark_stalled.side_effect = OperationalError("connection reset by peer", None, None)

        with pytest.raises(OperationalError):
            monitor_stalled_steps()
        assert mock_session_local.call_count == 3
        assert [call.args[0] for call in mock_sleep.call_args_list] == [1, 2]

    @patch("app.tasks.monitor_stalled_steps.logger")
    @patch("app.tasks.monitor_stalled_steps.time.sleep")
    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_real_helper_commit_disconnect_rolls_back_and_retries_fresh_session(
        self, mock_session_local, mock_sleep, mock_logger
    ):
        """A commit disconnect must not produce a success log for the failed attempt."""
        from app.models import FileProcessingStep
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        step = MagicMock(spec=FileProcessingStep)
        step.file_id = 7
        step.step_name = "ocr"
        step.started_at = datetime.now(timezone.utc) - timedelta(seconds=700)
        first_db = MagicMock()
        first_db.__enter__.return_value = first_db
        first_db.query.return_value.filter.return_value.with_for_update.return_value.all.return_value = [step]
        first_db.commit.side_effect = OperationalError("SSL bad record mac", None, None)
        second_db = MagicMock()
        second_db.__enter__.return_value = second_db
        second_db.query.return_value.filter.return_value.with_for_update.return_value.all.return_value = []
        mock_session_local.side_effect = [first_db, second_db]

        assert monitor_stalled_steps() == {"recovered": 0}
        first_db.rollback.assert_called_once_with()
        first_db.__exit__.assert_called_once()
        assert mock_session_local.call_count == 2
        mock_sleep.assert_called_once_with(1)
        mock_logger.error.assert_not_called()

    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_real_helper_nontransient_error_propagates_exact_exception(self, mock_session_local):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        error = OperationalError("syntax error", None, None)
        db = MagicMock()
        db.__enter__.return_value = db
        query = db.query.return_value.filter.return_value.with_for_update.return_value
        query.all.side_effect = error
        mock_session_local.return_value = db

        with pytest.raises(OperationalError) as raised:
            monitor_stalled_steps()
        assert raised.value is error
        db.rollback.assert_called_once_with()

    @patch("app.tasks.monitor_stalled_steps.SessionLocal")
    def test_real_helper_rollback_failure_preserves_original_exception(self, mock_session_local):
        from app.tasks.monitor_stalled_steps import monitor_stalled_steps

        error = OperationalError("connection reset by peer", None, None)
        db = MagicMock()
        db.__enter__.return_value = db
        query = db.query.return_value.filter.return_value.with_for_update.return_value
        query.all.side_effect = error
        db.rollback.side_effect = RuntimeError("rollback failed")
        mock_session_local.return_value = db

        with patch("app.tasks.monitor_stalled_steps.time.sleep"):
            with pytest.raises(OperationalError) as raised:
                monitor_stalled_steps()
        assert raised.value is error

    def test_connection_invalidated_is_transient(self):
        from app.tasks.monitor_stalled_steps import _is_transient_disconnect

        error = OperationalError("database unavailable", None, None)
        error.connection_invalidated = True
        assert _is_transient_disconnect(error) is True

    @patch("app.utils.step_timeout.logger")
    def test_real_helper_locks_rows_and_logs_primitive_snapshot_after_commit(self, mock_logger):
        from app.utils.step_timeout import mark_stalled_steps_as_failed

        class Step:
            file_id = 7
            step_name = "ocr"

            def __init__(self):
                self._started_at = datetime.now(timezone.utc) - timedelta(seconds=700)
                self.after_commit = False
                self.status = "in_progress"

            @property
            def started_at(self):
                if self.after_commit:
                    raise AssertionError("postcommit ORM access")
                return self._started_at

            @started_at.setter
            def started_at(self, value):
                self._started_at = value

        step = Step()
        db = MagicMock()
        query = db.query.return_value.filter.return_value.with_for_update.return_value
        query.all.return_value = [step]

        def commit():
            step.after_commit = True

        db.commit.side_effect = commit
        assert mark_stalled_steps_as_failed(db) == 1
        db.query.return_value.filter.return_value.with_for_update.assert_called_once_with(skip_locked=True)
        mock_logger.error.assert_called_once()
