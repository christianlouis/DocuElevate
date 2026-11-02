from unittest.mock import MagicMock

from app.scheduler import HeartbeatScheduler
from app.utils import upload_health


def test_missing_or_expired_marker_is_not_healthy(monkeypatch):
    client = MagicMock()
    client.get.return_value = None
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "stalled"
    from datetime import datetime, timedelta, timezone

    client.get.side_effect = None
    client.get.return_value = (datetime.now(timezone.utc) - timedelta(seconds=upload_health.HEARTBEAT_TTL + 1)).isoformat()
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "stalled"
    client.get.side_effect = ConnectionError("redis unavailable")
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "unknown"


def test_mark_fresh_is_best_effort(monkeypatch):
    client = MagicMock()
    client.set.side_effect = ConnectionError("redis unavailable")
    upload_health.mark_fresh(upload_health.DISPATCHER_KEY, client)
    client.set.assert_called_once()


def test_heartbeat_scheduler_writes_process_marker(monkeypatch):
    marker = MagicMock()
    monkeypatch.setattr("app.scheduler.mark_fresh", marker)
    scheduler = object.__new__(HeartbeatScheduler)
    # The marker is emitted before Celery's normal tick; this call is isolated
    # from broker/database state by replacing the parent implementation.
    monkeypatch.setattr("app.scheduler.Scheduler.tick", lambda self, *a, **k: 100)
    assert scheduler.tick() == upload_health.HEARTBEAT_TTL / 2
    marker.assert_called_once_with(upload_health.SCHEDULER_KEY)


def test_upload_maintenance_tasks_use_dedicated_queue():
    from app.celery_app import celery

    routes = celery.conf.task_routes
    assert routes["app.tasks.dispatch_uploads.dispatch_upload_item"]["queue"] == "document_processor"
    assert routes["app.tasks.dispatch_uploads.dispatch_upload_outbox"]["queue"] == "upload_maintenance"
    assert routes["app.tasks.dispatch_uploads.reconcile_upload_states"]["queue"] == "upload_maintenance"
