from unittest.mock import MagicMock

from app.scheduler import HeartbeatScheduler
from app.utils import upload_health


def test_missing_expired_or_invalid_marker_is_not_healthy(monkeypatch):
    client = MagicMock()
    client.get.return_value = None
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "stalled"
    from datetime import datetime, timedelta, timezone

    client.get.side_effect = None
    client.get.return_value = (
        datetime.now(timezone.utc) - timedelta(seconds=upload_health.HEARTBEAT_TTL + 1)
    ).isoformat()
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "stalled"
    client.get.side_effect = ConnectionError("redis unavailable")
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "unknown"
    client.get.side_effect = None
    client.get.return_value = "not-an-iso-timestamp"
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "unknown"


def test_recent_marker_is_healthy():
    from datetime import datetime, timezone

    client = MagicMock()
    client.get.return_value = datetime.now(timezone.utc).isoformat()
    assert upload_health.freshness(upload_health.SCHEDULER_KEY, client) == "healthy"


def test_mark_fresh_is_best_effort(monkeypatch):
    client = MagicMock()
    client.set.side_effect = ConnectionError("redis unavailable")
    upload_health.mark_fresh(upload_health.DISPATCHER_KEY, client)
    client.set.assert_called_once()


def test_health_markers_use_operational_redis_not_the_celery_broker(monkeypatch):
    client = MagicMock()
    redis_from_url = MagicMock(return_value=client)
    monkeypatch.setattr(upload_health.redis, "from_url", redis_from_url)
    monkeypatch.setattr(upload_health.settings, "redis_url", "redis://health:6379/2")
    monkeypatch.setattr(upload_health.settings, "celery_broker_url", "amqp://broker")

    assert upload_health._client() is client
    redis_from_url.assert_called_once_with("redis://health:6379/2", socket_connect_timeout=2, socket_timeout=2)


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
    assert routes["app.tasks.dispatch_uploads.dispatch_upload_item"]["queue"] == "upload_maintenance"
    assert routes["app.tasks.dispatch_uploads.dispatch_upload_outbox"]["queue"] == "upload_maintenance"
    assert routes["app.tasks.dispatch_uploads.reconcile_upload_states"]["queue"] == "upload_maintenance"


def test_document_pipeline_tasks_keep_the_normal_processing_queue():
    from app.celery_app import celery

    for task_name in (
        "app.tasks.process_document.process_document",
        "app.tasks.convert_to_pdf.convert_to_pdf",
    ):
        route = celery.amqp.router.route({}, task_name, (), {})
        queue = route["queue"]
        assert (queue.name if hasattr(queue, "name") else queue) == "document_processor"
