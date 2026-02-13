"""
Tests for app/celery_worker.py

This module tests the Celery worker configuration, task imports, and beat schedule.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from celery.schedules import crontab


@pytest.mark.unit
class TestCeleryWorkerConfig:
    """Test Celery worker configuration."""

    def test_test_task_function(self):
        """Test the test_task function returns expected value."""
        from app.celery_worker import test_task

        result = test_task()
        assert result == "Celery is working!"

    def test_celery_instance_exists(self):
        """Test that celery instance exists in module."""
        from app import celery_worker

        assert hasattr(celery_worker, "celery")
        assert celery_worker.celery is not None

    def test_task_routes_exists(self):
        """Test that task routes configuration exists."""
        from app import celery_worker

        # Task routes should be configured
        assert hasattr(celery_worker.celery.conf, "task_routes")

    def test_all_task_imports_successful(self):
        """Test that all task modules are imported successfully."""
        # Just import the module to verify no import errors
        from app import celery_worker

        # Module imported successfully
        assert celery_worker is not None


@pytest.mark.unit
class TestBeatScheduleConfiguration:
    """Test Celery beat schedule configuration."""

    def test_beat_schedule_structure(self):
        """Test that beat schedule has expected structure."""
        from app.celery_worker import celery

        # Beat schedule should be a dictionary
        assert isinstance(celery.conf.beat_schedule, dict)

        # Should include credential check tasks
        assert "check-credentials-regularly" in celery.conf.beat_schedule
        assert "check-credentials-daily" in celery.conf.beat_schedule
        assert "monitor-stalled-steps" in celery.conf.beat_schedule

    def test_credential_check_schedule(self):
        """Test credential check schedule configuration."""
        from app.celery_worker import celery

        schedule = celery.conf.beat_schedule.get("check-credentials-regularly")
        assert schedule is not None
        assert schedule["task"] == "app.tasks.check_credentials.check_credentials"
        assert "schedule" in schedule
        assert schedule["options"]["expires"] == 240

    def test_daily_credential_check_schedule(self):
        """Test daily credential check schedule."""
        from app.celery_worker import celery

        schedule = celery.conf.beat_schedule.get("check-credentials-daily")
        assert schedule is not None
        assert schedule["task"] == "app.tasks.check_credentials.check_credentials"
        assert "schedule" in schedule
        assert schedule["options"]["expires"] == 3600

    def test_monitor_stalled_steps_schedule(self):
        """Test monitor stalled steps schedule."""
        from app.celery_worker import celery

        schedule = celery.conf.beat_schedule.get("monitor-stalled-steps")
        assert schedule is not None
        assert schedule["task"] == "app.tasks.monitor_stalled_steps.monitor_stalled_steps"
        assert "schedule" in schedule
        assert schedule["options"]["expires"] == 55

    def test_no_none_entries_in_beat_schedule(self):
        """Test that None entries are filtered from beat schedule."""
        from app.celery_worker import celery

        # No None values in beat schedule
        for key, value in celery.conf.beat_schedule.items():
            assert value is not None, f"Beat schedule entry '{key}' should not be None"
