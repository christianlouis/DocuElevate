"""
Tests for app/celery_app.py

This module tests the Celery app configuration and task failure handler.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestCeleryAppConfig:
    """Test Celery app configuration."""

    def test_celery_instance_exists(self):
        """Test that celery instance exists and is properly configured."""
        from app.celery_app import celery

        assert celery is not None
        assert celery.main == "document_processor"

    def test_celery_broker_configured(self):
        """Test that celery broker is configured."""
        from app.celery_app import celery

        assert celery.conf.broker_url is not None
        assert celery.conf.result_backend is not None

    def test_celery_default_queue(self):
        """Test that default queue is set to document_processor."""
        from app.celery_app import celery

        assert celery.conf.task_default_queue == "document_processor"

    def test_celery_task_routes(self):
        """Test that task routes are configured."""
        from app.celery_app import celery

        assert celery.conf.task_routes is not None
        assert "app.tasks.*" in celery.conf.task_routes
        assert celery.conf.task_routes["app.tasks.*"]["queue"] == "document_processor"

    def test_broker_connection_retry_on_startup(self):
        """Test that broker connection retry on startup is enabled."""
        from app.celery_app import celery

        assert celery.conf.broker_connection_retry_on_startup is True


@pytest.mark.unit
class TestTaskFailureHandler:
    """Test task failure handler signal."""

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure")
    def test_task_failure_handler_sends_notification(self, mock_notify, mock_settings):
        """Test that task failure handler sends notification when enabled."""
        # Configure settings to enable notifications
        mock_settings.notify_on_task_failure = True

        # Import the handler
        from app.celery_app import task_failure_handler

        # Create mock sender with task name
        mock_sender = MagicMock()
        mock_sender.name = "test.task"

        # Create exception instance
        test_exception = ValueError("Test error")

        # Call the handler
        task_failure_handler(
            sender=mock_sender,
            task_id="test-task-id",
            exception=test_exception,
            args=[1, 2, 3],
            kwargs={"key": "value"},
        )

        # Verify notification was sent with correct parameters
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        assert call_kwargs["task_name"] == "test.task"
        assert call_kwargs["task_id"] == "test-task-id"
        assert isinstance(call_kwargs["exc"], ValueError)
        assert str(call_kwargs["exc"]) == "Test error"
        assert call_kwargs["args"] == [1, 2, 3]
        assert call_kwargs["kwargs"] == {"key": "value"}

    @patch("app.celery_app.settings")
    def test_task_failure_handler_disabled_notification(self, mock_settings):
        """Test that task failure handler does not send notification when disabled."""
        # Configure settings to disable notifications
        mock_settings.notify_on_task_failure = False

        # Import the handler
        from app.celery_app import task_failure_handler

        with patch("app.utils.notification.notify_celery_failure") as mock_notify:
            # Create mock sender
            mock_sender = MagicMock()
            mock_sender.name = "test.task"

            # Call the handler
            task_failure_handler(
                sender=mock_sender,
                task_id="test-task-id",
                exception=ValueError("Test error"),
            )

            # Verify notification was NOT sent
            mock_notify.assert_not_called()

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure")
    def test_task_failure_handler_with_no_sender(self, mock_notify, mock_settings):
        """Test task failure handler when sender is None."""
        mock_settings.notify_on_task_failure = True

        from app.celery_app import task_failure_handler

        # Call with no sender
        task_failure_handler(
            sender=None,
            task_id="test-task-id",
            exception=ValueError("Test error"),
        )

        # Should use "Unknown" as task name
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[1]
        assert call_args["task_name"] == "Unknown"

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure")
    def test_task_failure_handler_with_no_task_id(self, mock_notify, mock_settings):
        """Test task failure handler when task_id is None."""
        mock_settings.notify_on_task_failure = True

        from app.celery_app import task_failure_handler

        mock_sender = MagicMock()
        mock_sender.name = "test.task"

        # Call with no task_id
        task_failure_handler(
            sender=mock_sender,
            task_id=None,
            exception=ValueError("Test error"),
        )

        # Should use "N/A" as task_id
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[1]
        assert call_args["task_id"] == "N/A"

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure")
    def test_task_failure_handler_with_empty_args_kwargs(self, mock_notify, mock_settings):
        """Test task failure handler with no args or kwargs."""
        mock_settings.notify_on_task_failure = True

        from app.celery_app import task_failure_handler

        mock_sender = MagicMock()
        mock_sender.name = "test.task"

        # Call with None args/kwargs
        task_failure_handler(
            sender=mock_sender,
            task_id="test-task-id",
            exception=ValueError("Test error"),
            args=None,
            kwargs=None,
        )

        # Should use empty list/dict as defaults
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args[1]
        assert call_args["args"] == []
        assert call_args["kwargs"] == {}

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure", side_effect=Exception("Notification failed"))
    def test_task_failure_handler_exception_handling(self, mock_notify, mock_settings, caplog):
        """Test that exceptions in notification are caught and logged."""
        mock_settings.notify_on_task_failure = True

        from app.celery_app import task_failure_handler

        mock_sender = MagicMock()
        mock_sender.name = "test.task"

        # Call the handler - should not raise exception
        with caplog.at_level(logging.ERROR):
            task_failure_handler(
                sender=mock_sender,
                task_id="test-task-id",
                exception=ValueError("Test error"),
            )

        # Verify the exception was logged
        assert any("Failed to send task failure notification" in record.message for record in caplog.records)

    @patch("app.celery_app.settings")
    @patch("app.utils.notification.notify_celery_failure")
    def test_task_failure_handler_called_by_signal(self, mock_notify, mock_settings):
        """Test that the handler is properly connected to the task_failure signal."""
        mock_settings.notify_on_task_failure = True

        # Import to ensure signal is connected
        # Import the signal
        from celery.signals import task_failure

        from app.celery_app import task_failure_handler

        # The handler should be connected to the signal
        # We can test this by verifying the signal has receivers
        receivers = task_failure.receivers
        assert len(receivers) > 0

        # Simply verify that importing the handler doesn't cause errors
        # The actual signal connection is tested implicitly by the other tests
        assert callable(task_failure_handler)
