"""
Tests for app/celery_worker.py

Targets all statements and branches in the Celery worker configuration module,
including module-level task imports, beat schedule construction, the conditional
IMAP / Uptime Kuma entries, and the None-entry filter.

Because celery_worker.py fires ``check_credentials.apply_async()`` at import
time (which requires a live Redis broker), every test mocks that call via
``importlib.reload`` so the module can be exercised without external services.
"""

import importlib
from unittest.mock import patch

import pytest

from app.config import settings


def _reload_celery_worker():
    """Reload celery_worker with ``apply_async`` mocked to avoid Redis."""
    with patch("app.tasks.check_credentials.check_credentials.apply_async"):
        import app.celery_worker

        importlib.reload(app.celery_worker)
        return app.celery_worker


@pytest.mark.unit
class TestCeleryWorkerConfig:
    """Test Celery worker configuration (imports, task routes, side effects)."""

    def test_test_task_function(self):
        """Test the test_task function returns expected value."""
        mod = _reload_celery_worker()
        result = mod.test_task()
        assert result == "Celery is working!"

    def test_celery_instance_exists(self):
        """Test that celery instance exists in module."""
        mod = _reload_celery_worker()
        assert hasattr(mod, "celery")
        assert mod.celery is not None

    def test_task_routes_configured(self):
        """Test that task routes are set."""
        mod = _reload_celery_worker()
        routes = mod.celery.conf.task_routes
        assert routes is not None
        assert "app.tasks.*" in routes

    def test_all_task_imports_successful(self):
        """Test that all task modules are imported without errors."""
        mod = _reload_celery_worker()
        assert mod is not None

    def test_register_settings_reload_signal_called(self):
        """Test that register_settings_reload_signal is called at module load."""
        with (
            patch("app.tasks.check_credentials.check_credentials.apply_async"),
            patch("app.utils.settings_sync.register_settings_reload_signal") as mock_reg,
        ):
            import app.celery_worker

            importlib.reload(app.celery_worker)
            mock_reg.assert_called_once()

    def test_check_credentials_apply_async_called(self):
        """Test that check_credentials.apply_async is called at module load."""
        with patch("app.tasks.check_credentials.check_credentials.apply_async") as mock_apply:
            import app.celery_worker

            importlib.reload(app.celery_worker)
            mock_apply.assert_called_once_with(countdown=10)


@pytest.mark.unit
class TestBeatScheduleConfiguration:
    """Test Celery beat schedule configuration (lines 56-97)."""

    def test_beat_schedule_always_present_entries(self):
        """Test that the three unconditional entries are always present."""
        mod = _reload_celery_worker()
        schedule = mod.celery.conf.beat_schedule
        assert isinstance(schedule, dict)
        assert "check-credentials-regularly" in schedule
        assert "check-credentials-daily" in schedule
        assert "monitor-stalled-steps" in schedule

    def test_credential_check_regular_schedule(self):
        """Test 'check-credentials-regularly' entry."""
        mod = _reload_celery_worker()
        entry = mod.celery.conf.beat_schedule["check-credentials-regularly"]
        assert entry["task"] == "app.tasks.check_credentials.check_credentials"
        assert "schedule" in entry
        assert entry["options"]["expires"] == 240

    def test_credential_check_daily_schedule(self):
        """Test 'check-credentials-daily' entry."""
        mod = _reload_celery_worker()
        entry = mod.celery.conf.beat_schedule["check-credentials-daily"]
        assert entry["task"] == "app.tasks.check_credentials.check_credentials"
        assert entry["options"]["expires"] == 3600

    def test_monitor_stalled_steps_schedule(self):
        """Test 'monitor-stalled-steps' entry."""
        mod = _reload_celery_worker()
        entry = mod.celery.conf.beat_schedule["monitor-stalled-steps"]
        assert entry["task"] == "app.tasks.monitor_stalled_steps.monitor_stalled_steps"
        assert entry["options"]["expires"] == 55

    def test_no_none_entries_in_beat_schedule(self):
        """Test that None entries are filtered from beat schedule."""
        mod = _reload_celery_worker()
        for key, value in mod.celery.conf.beat_schedule.items():
            assert value is not None, f"Beat schedule entry '{key}' should not be None"

    # -- Conditional schedule entries ----------------------------------------

    def test_imap_schedule_absent_when_not_configured(self):
        """Test IMAP polling absent when neither imap host is set."""
        mod = _reload_celery_worker()
        assert "poll-inboxes-every-minute" not in mod.celery.conf.beat_schedule

    def test_uptime_kuma_schedule_absent_when_not_configured(self):
        """Test Uptime Kuma ping absent when url is not set."""
        mod = _reload_celery_worker()
        assert "ping-uptime-kuma" not in mod.celery.conf.beat_schedule

    def test_imap_schedule_present_when_imap1_configured(self):
        """Test IMAP polling present when imap1_host is set."""
        original = settings.imap1_host
        try:
            settings.imap1_host = "imap.example.com"
            mod = _reload_celery_worker()
            assert "poll-inboxes-every-minute" in mod.celery.conf.beat_schedule
            entry = mod.celery.conf.beat_schedule["poll-inboxes-every-minute"]
            assert entry["task"] == "app.tasks.imap_tasks.pull_all_inboxes"
            assert entry["options"]["expires"] == 55
        finally:
            settings.imap1_host = original

    def test_imap_schedule_present_when_imap2_configured(self):
        """Test IMAP polling present when imap2_host is set."""
        original = settings.imap2_host
        try:
            settings.imap2_host = "imap2.example.com"
            mod = _reload_celery_worker()
            assert "poll-inboxes-every-minute" in mod.celery.conf.beat_schedule
        finally:
            settings.imap2_host = original

    def test_uptime_kuma_schedule_present_when_configured(self):
        """Test Uptime Kuma ping present when uptime_kuma_url is set."""
        orig_url = settings.uptime_kuma_url
        orig_interval = settings.uptime_kuma_ping_interval
        try:
            settings.uptime_kuma_url = "https://uptime.example.com/api/push/abc"
            settings.uptime_kuma_ping_interval = 3
            mod = _reload_celery_worker()
            assert "ping-uptime-kuma" in mod.celery.conf.beat_schedule
            entry = mod.celery.conf.beat_schedule["ping-uptime-kuma"]
            assert entry["task"] == "app.tasks.uptime_kuma_tasks.ping_uptime_kuma"
            assert entry["options"]["expires"] == 55
        finally:
            settings.uptime_kuma_url = orig_url
            settings.uptime_kuma_ping_interval = orig_interval
