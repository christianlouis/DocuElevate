"""Tests for the webhook subsystem (utility, API, and task)."""

import hashlib
import hmac
import json
import socket
import time
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import pytest

from app.models import FileRecord, Pipeline, WebhookConfig, WebhookDeliveryAttempt
from app.utils.webhook import (
    _send_pinned_post,
    build_payload,
    compute_signature,
    deliver_webhook,
    dispatch_webhook_event,
    get_active_webhooks_for_event,
    verify_signature,
)

# ---------------------------------------------------------------------------
# Unit tests – compute_signature
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeSignature:
    """Tests for HMAC-SHA256 signature generation."""

    def test_signature_format(self):
        """Signature starts with 'sha256=' and is a hex digest."""
        sig = compute_signature(b'{"event":"test"}', "mysecret")
        assert sig.startswith("sha256=")
        # hex digest should be 64 chars
        assert len(sig.split("=")[1]) == 64

    def test_signature_matches_manual_hmac(self):
        """Signature matches a manually computed HMAC-SHA256."""
        payload = b'{"key":"value"}'
        secret = "s3cret"
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert compute_signature(payload, secret) == expected

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets must produce different signatures."""
        payload = b"same"
        assert compute_signature(payload, "secret1") != compute_signature(payload, "secret2")


# ---------------------------------------------------------------------------
# Unit tests – verify_signature
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVerifySignature:
    """Tests for webhook signature verification."""

    def test_valid_signature_returns_true(self):
        """The verifier accepts signatures produced by compute_signature."""
        payload = b'{"event":"document.processed"}'
        signature = compute_signature(payload, "secret")

        assert verify_signature(payload, "secret", signature) is True

    def test_invalid_signature_returns_false(self):
        """The verifier rejects signatures for a different secret or payload."""
        payload = b'{"event":"document.processed"}'
        signature = compute_signature(payload, "other-secret")

        assert verify_signature(payload, "secret", signature) is False

    @pytest.mark.parametrize("signature", [None, "", "bad", "sha1=abc"])
    def test_malformed_signature_returns_false(self, signature):
        """Missing or malformed signatures are rejected."""
        assert verify_signature(b"{}", "secret", signature) is False


# ---------------------------------------------------------------------------
# Unit tests – build_payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildPayload:
    """Tests for the webhook payload builder."""

    def test_contains_required_keys(self):
        """Payload contains event, timestamp, and data."""
        payload = build_payload("document.uploaded", {"file_id": 1})
        assert payload["event"] == "document.uploaded"
        assert "timestamp" in payload
        assert payload["data"] == {"file_id": 1}

    def test_timestamp_is_recent(self):
        """Timestamp should be close to current time."""
        before = time.time()
        payload = build_payload("document.processed", {})
        after = time.time()
        assert before <= payload["timestamp"] <= after


# ---------------------------------------------------------------------------
# Unit tests – deliver_webhook
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeliverWebhook:
    """Tests for the HTTP delivery function."""

    def test_success_returns_true(self, mocker):
        """A 200 response returns True."""
        mocker.patch("app.utils.webhook._resolve_public_address", return_value="93.184.216.34")
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post", return_value=(True, 200))

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is True
        mock_post.assert_called_once()

    def test_non_2xx_returns_false(self, mocker):
        """A non-2xx response returns False."""
        mocker.patch("app.utils.webhook._resolve_public_address", return_value="93.184.216.34")
        mocker.patch("app.utils.webhook._send_pinned_post", return_value=(False, 500))

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is False

    def test_request_exception_returns_false(self, mocker):
        """A network error returns False."""
        mocker.patch("app.utils.webhook._resolve_public_address", return_value="93.184.216.34")
        mocker.patch("app.utils.webhook._send_pinned_post", side_effect=OSError("fail"))

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is False

    def test_signature_header_included_when_secret(self, mocker):
        """X-Webhook-Signature header is present when a secret is supplied."""
        mocker.patch("app.utils.webhook._resolve_public_address", return_value="93.184.216.34")
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post", return_value=(True, 200))

        deliver_webhook("https://example.com/hook", {"event": "test"}, secret="abc")
        headers = mock_post.call_args.args[3]
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")

    def test_no_signature_header_without_secret(self, mocker):
        """X-Webhook-Signature header is absent when no secret is supplied."""
        mocker.patch("app.utils.webhook._resolve_public_address", return_value="93.184.216.34")
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post", return_value=(True, 200))

        deliver_webhook("https://example.com/hook", {"event": "test"})
        headers = mock_post.call_args.args[3]
        assert "X-Webhook-Signature" not in headers

    def test_private_target_is_blocked(self, mocker):
        """Private network webhook targets are not called."""
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post")

        result = deliver_webhook("https://10.0.0.5/hook", {"event": "test"})

        assert result is False
        mock_post.assert_not_called()

    def test_metadata_target_is_blocked(self, mocker):
        """Cloud metadata webhook targets are not called."""
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post")

        result = deliver_webhook("http://169.254.169.254/latest/meta-data", {"event": "test"})

        assert result is False
        mock_post.assert_not_called()

    def test_invalid_scheme_is_blocked(self, mocker):
        """Unsupported webhook URL schemes are not called."""
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post")

        result = deliver_webhook("file:///etc/passwd", {"event": "test"})

        assert result is False
        mock_post.assert_not_called()

    def test_missing_hostname_is_blocked(self, mocker):
        """Webhook URLs without a hostname are not called."""
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post")

        result = deliver_webhook("https:///missing-host", {"event": "test"})

        assert result is False
        mock_post.assert_not_called()

    def test_rebound_private_dns_answer_is_blocked(self, mocker):
        """A hostname is blocked when DNS returns any private address."""
        mocker.patch(
            "app.utils.webhook.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
            ],
        )
        mock_post = mocker.patch("app.utils.webhook._send_pinned_post")

        result = deliver_webhook("https://example.com/hook", {"event": "test"})

        assert result is False
        mock_post.assert_not_called()

    def test_tls_wrap_failure_closes_raw_socket(self, mocker):
        """The pinned socket is closed when TLS setup fails."""
        raw_socket = mocker.Mock()
        mocker.patch("app.utils.webhook.socket.create_connection", return_value=raw_socket)
        context = mocker.Mock()
        context.wrap_socket.side_effect = OSError("tls failure")
        mocker.patch("app.utils.webhook.ssl.create_default_context", return_value=context)

        with pytest.raises(OSError, match="tls failure"):
            _send_pinned_post(
                urlparse("https://example.com/hook"),
                "93.184.216.34",
                b"{}",
                {"Content-Type": "application/json"},
            )

        raw_socket.close.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests – get_active_webhooks_for_event (DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetActiveWebhooks:
    """Tests that active webhook configs are correctly filtered by event."""

    def test_returns_matching_webhooks(self, db_session):
        """Only webhooks subscribed to the given event are returned."""
        cfg1 = WebhookConfig(
            url="https://a.com/hook",
            secret="s1",
            events=json.dumps(["document.uploaded", "document.processed"]),
            is_active=True,
        )
        cfg2 = WebhookConfig(
            url="https://b.com/hook",
            events=json.dumps(["document.failed"]),
            is_active=True,
        )
        db_session.add_all([cfg1, cfg2])
        db_session.commit()

        with patch("app.utils.webhook.SessionLocal", return_value=db_session):
            results = get_active_webhooks_for_event("document.uploaded")

        assert len(results) == 1
        assert results[0]["url"] == "https://a.com/hook"

    def test_inactive_webhooks_excluded(self, db_session):
        """Inactive webhooks are not returned."""
        cfg = WebhookConfig(
            url="https://inactive.com/hook",
            events=json.dumps(["document.uploaded"]),
            is_active=False,
        )
        db_session.add(cfg)
        db_session.commit()

        with patch("app.utils.webhook.SessionLocal", return_value=db_session):
            results = get_active_webhooks_for_event("document.uploaded")

        assert results == []

    def test_returns_empty_when_no_match(self, db_session):
        """No webhooks returned when none match the event."""
        cfg = WebhookConfig(
            url="https://c.com/hook",
            events=json.dumps(["document.failed"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        with patch("app.utils.webhook.SessionLocal", return_value=db_session):
            results = get_active_webhooks_for_event("document.uploaded")

        assert results == []


# ---------------------------------------------------------------------------
# Unit tests – dispatch_webhook_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchWebhookEvent:
    """Tests for the high-level dispatch function."""

    def test_unknown_event_is_ignored(self, mocker):
        """Unknown events are silently ignored."""
        mock_get = mocker.patch("app.utils.webhook.get_active_webhooks_for_event")
        dispatch_webhook_event("unknown.event", {})
        mock_get.assert_not_called()

    def test_no_webhooks_does_not_fail(self, mocker):
        """No error when there are no matching webhooks."""
        mocker.patch("app.utils.webhook.get_active_webhooks_for_event", return_value=[])
        dispatch_webhook_event("document.uploaded", {"file_id": 1})

    def test_queues_celery_task_for_each_webhook(self, mocker):
        """A Celery task is queued for each matching webhook."""
        mocker.patch(
            "app.utils.webhook.get_active_webhooks_for_event",
            return_value=[
                {"id": 1, "url": "https://a.com", "secret": "s", "events": ["document.uploaded"]},
                {"id": 2, "url": "https://b.com", "secret": None, "events": ["document.uploaded"]},
            ],
        )
        mock_task = mocker.patch("app.tasks.webhook_tasks.deliver_webhook_task.delay")

        dispatch_webhook_event("document.uploaded", {"file_id": 42})

        assert mock_task.call_count == 2


# ---------------------------------------------------------------------------
# Integration tests – API endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWebhookAPI:
    """Tests for the /api/webhooks/ endpoints."""

    def _with_admin(self, client):
        """Return headers / approach to authenticate as admin for test client."""
        # FastAPI TestClient + SessionMiddleware: we can set session data by
        # using the app's dependency override or the session directly.
        # Simplest: override the _require_admin dependency.
        from app.api.webhooks import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True, "name": "test-admin"}
        return client

    def test_create_webhook(self, client):
        """POST /api/webhooks/ creates a new webhook."""
        self._with_admin(client)
        resp = client.post(
            "/api/webhooks/",
            json={
                "url": "https://example.com/webhook",
                "secret": "my-secret",
                "events": ["document.uploaded"],
                "description": "Test hook",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["url"] == "https://example.com/webhook"
        assert data["events"] == ["document.uploaded"]
        assert data["is_active"] is True
        assert data["has_secret"] is True
        assert "secret" not in data  # secret must not be exposed

    @patch("app.api.webhooks.process_document.delay")
    def test_inbound_pipeline_trigger_assigns_profile_and_queues_work(self, mock_delay, client, db_session, tmp_path):
        """Inbound triggers validate file/pipeline access before queueing processing."""
        source_file = tmp_path / "inbound.pdf"
        source_file.write_bytes(b"%PDF-1.4")
        pipeline = Pipeline(owner_id="anonymous", name="Inbound")
        file_record = FileRecord(
            owner_id=None,
            filehash="hash-inbound",
            original_filename="inbound.pdf",
            local_filename=str(source_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add_all([pipeline, file_record])
        db_session.commit()
        mock_delay.return_value = Mock(id="task-inbound")

        resp = client.post(
            f"/api/webhooks/inbound/pipelines/{pipeline.id}/trigger",
            json={"file_id": file_record.id, "force_cloud_ocr": True, "event_id": "evt-123"},
        )

        assert resp.status_code == 202
        assert resp.json() == {
            "status": "queued",
            "file_id": file_record.id,
            "pipeline_id": pipeline.id,
            "task_id": "task-inbound",
        }
        db_session.refresh(file_record)
        assert file_record.pipeline_id == pipeline.id
        assert file_record.pipeline_assignment_source == "inbound_webhook"
        assert "evt-123" in file_record.pipeline_assignment_reason
        mock_delay.assert_called_once_with(
            str(source_file),
            original_filename="inbound.pdf",
            file_id=file_record.id,
            force_cloud_ocr=True,
            owner_id=None,
        )

    def test_inbound_pipeline_trigger_rejects_missing_file(self, client, db_session):
        """Inbound triggers reject unknown documents."""
        pipeline = Pipeline(owner_id="anonymous", name="Inbound")
        db_session.add(pipeline)
        db_session.commit()

        resp = client.post(f"/api/webhooks/inbound/pipelines/{pipeline.id}/trigger", json={"file_id": 99999})

        assert resp.status_code == 404

    def test_inbound_pipeline_trigger_rejects_missing_local_file(self, client, db_session):
        """Inbound triggers do not queue work when the document file is unavailable."""
        pipeline = Pipeline(owner_id="anonymous", name="Inbound")
        file_record = FileRecord(
            owner_id=None,
            filehash="hash-missing",
            original_filename="missing.pdf",
            local_filename="/nonexistent/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add_all([pipeline, file_record])
        db_session.commit()

        resp = client.post(f"/api/webhooks/inbound/pipelines/{pipeline.id}/trigger", json={"file_id": file_record.id})

        assert resp.status_code == 409
        assert resp.json()["detail"] == "Local file not found on disk. Cannot trigger pipeline."

    def test_list_webhooks(self, client, db_session):
        """GET /api/webhooks/ returns all webhooks."""
        self._with_admin(client)
        # seed one
        cfg = WebhookConfig(
            url="https://list.example.com/hook",
            events=json.dumps(["document.processed"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        resp = client.get("/api/webhooks/")
        assert resp.status_code == 200
        items = resp.json()
        assert any(w["url"] == "https://list.example.com/hook" for w in items)

    def test_list_delivery_attempts(self, client, db_session):
        """GET /api/webhooks/delivery-attempts/ returns recent persisted deliveries."""
        self._with_admin(client)
        attempt = WebhookDeliveryAttempt(
            url="https://list.example.com/hook",
            event="document.processed",
            payload=json.dumps({"event": "document.processed"}),
            status="failed",
            attempt_number=2,
            error="timeout",
        )
        db_session.add(attempt)
        db_session.commit()

        resp = client.get("/api/webhooks/delivery-attempts/?status=failed")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["url"] == "https://list.example.com/hook"
        assert data[0]["event"] == "document.processed"
        assert data[0]["status"] == "failed"
        assert "payload" not in data[0]

    def test_event_catalog_returns_versioned_samples(self, client):
        """GET /api/webhooks/event-catalog/ describes supported events."""
        self._with_admin(client)

        resp = client.get("/api/webhooks/event-catalog/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["payload_version"] == "1.0"
        processed = next(event for event in data["events"] if event["event"] == "document.processed")
        assert processed["payload_version"] == "1.0"
        assert processed["sample_payload"]["event"] == "document.processed"
        assert processed["sample_payload"]["data"]["file_id"] == 42
        event_names = {event["event"] for event in data["events"]}
        assert {"document.routed", "document.metadata_updated"}.issubset(event_names)
        routed = next(event for event in data["events"] if event["event"] == "document.routed")
        assert routed["sample_payload"]["data"]["assignment_source"] == "routing_rule"
        metadata = next(event for event in data["events"] if event["event"] == "document.metadata_updated")
        assert "updated_fields" in metadata["sample_payload"]["data"]

    def test_replay_delivery_attempt_queues_current_webhook_config(self, client, db_session, mocker):
        """POST /api/webhooks/delivery-attempts/{id}/replay queues a new attempt."""
        self._with_admin(client)
        mock_task = mocker.patch("app.api.webhooks.deliver_webhook_task.delay")
        mock_task.return_value = Mock(id="task-replay")
        cfg = WebhookConfig(
            url="https://current.example.com/hook",
            secret="current-secret",
            events=json.dumps(["document.processed"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()
        attempt = WebhookDeliveryAttempt(
            webhook_config_id=cfg.id,
            url="https://old.example.com/hook",
            event="document.processed",
            payload=json.dumps({"event": "document.processed", "data": {"file_id": 42}}),
            status="failed",
            attempt_number=1,
            error="timeout",
        )
        db_session.add(attempt)
        db_session.commit()

        resp = client.post(f"/api/webhooks/delivery-attempts/{attempt.id}/replay")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["replay_of"] == attempt.id
        assert data["task_id"] == "task-replay"
        replay = db_session.query(WebhookDeliveryAttempt).filter(WebhookDeliveryAttempt.id == data["delivery_id"]).one()
        assert replay.status == "queued"
        assert replay.url == "https://current.example.com/hook"
        mock_task.assert_called_once_with(
            "https://current.example.com/hook",
            {"event": "document.processed", "data": {"file_id": 42}},
            "current-secret",
            cfg.id,
            replay.id,
        )

    def test_get_webhook(self, client, db_session):
        """GET /api/webhooks/{id} returns a single webhook."""
        self._with_admin(client)
        cfg = WebhookConfig(
            url="https://get.example.com/hook",
            events=json.dumps(["document.failed"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        resp = client.get(f"/api/webhooks/{cfg.id}")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://get.example.com/hook"

    def test_get_webhook_not_found(self, client):
        """GET /api/webhooks/9999 returns 404."""
        self._with_admin(client)
        resp = client.get("/api/webhooks/9999")
        assert resp.status_code == 404

    def test_update_webhook(self, client, db_session):
        """PUT /api/webhooks/{id} updates the webhook."""
        self._with_admin(client)
        cfg = WebhookConfig(
            url="https://old.example.com/hook",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        resp = client.put(
            f"/api/webhooks/{cfg.id}",
            json={"url": "https://new.example.com/hook", "is_active": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["url"] == "https://new.example.com/hook"
        assert data["is_active"] is False

    def test_update_webhook_not_found(self, client):
        """PUT /api/webhooks/9999 returns 404."""
        self._with_admin(client)
        resp = client.put("/api/webhooks/9999", json={"url": "https://x.com"})
        assert resp.status_code == 404

    def test_delete_webhook(self, client, db_session):
        """DELETE /api/webhooks/{id} removes the webhook."""
        self._with_admin(client)
        cfg = WebhookConfig(
            url="https://del.example.com/hook",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()
        wid = cfg.id

        resp = client.delete(f"/api/webhooks/{wid}")
        assert resp.status_code == 204

        # confirm it's gone
        resp2 = client.get(f"/api/webhooks/{wid}")
        assert resp2.status_code == 404

    def test_delete_webhook_not_found(self, client):
        """DELETE /api/webhooks/9999 returns 404."""
        self._with_admin(client)
        resp = client.delete("/api/webhooks/9999")
        assert resp.status_code == 404

    def test_create_webhook_invalid_event(self, client):
        """POST /api/webhooks/ rejects invalid events."""
        self._with_admin(client)
        resp = client.post(
            "/api/webhooks/",
            json={"url": "https://x.com/hook", "events": ["bad.event"]},
        )
        assert resp.status_code == 422

    def test_list_events(self, client):
        """GET /api/webhooks/events/ returns valid events."""
        self._with_admin(client)
        resp = client.get("/api/webhooks/events/")
        assert resp.status_code == 200
        events = resp.json()
        assert "document.uploaded" in events
        assert "document.processed" in events
        assert "document.failed" in events
        assert "document.routed" in events
        assert "document.metadata_updated" in events

    def test_requires_admin(self, client):
        """Endpoints return 403 without admin session."""
        # Remove the admin override
        from app.api.webhooks import _require_admin

        client.app.dependency_overrides.pop(_require_admin, None)
        resp = client.get("/api/webhooks/")
        assert resp.status_code == 403

    def test_create_webhook_without_secret(self, client):
        """POST /api/webhooks/ works without a secret."""
        self._with_admin(client)
        resp = client.post(
            "/api/webhooks/",
            json={"url": "https://nosecret.com/hook", "events": ["document.failed"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is False

    def test_update_webhook_events(self, client, db_session):
        """PUT /api/webhooks/{id} can update events."""
        self._with_admin(client)
        cfg = WebhookConfig(
            url="https://evup.example.com/hook",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        resp = client.put(
            f"/api/webhooks/{cfg.id}",
            json={"events": ["document.processed", "document.failed"]},
        )
        assert resp.status_code == 200
        assert set(resp.json()["events"]) == {"document.processed", "document.failed"}

    def test_update_webhook_invalid_event(self, client, db_session):
        """PUT /api/webhooks/{id} rejects invalid events."""
        self._with_admin(client)
        cfg = WebhookConfig(
            url="https://bdev.example.com/hook",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
        )
        db_session.add(cfg)
        db_session.commit()

        resp = client.put(
            f"/api/webhooks/{cfg.id}",
            json={"events": ["invalid.event"]},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Unit tests – Celery task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeliverWebhookTask:
    """Tests for the Celery webhook delivery task."""

    def test_success_returns_status_dict(self, mocker, db_session):
        """Task returns a dict on successful delivery."""
        mocker.patch("app.tasks.webhook_tasks.deliver_webhook", return_value=True)
        mocker.patch("app.tasks.webhook_tasks.SessionLocal", return_value=db_session)

        from app.tasks.webhook_tasks import deliver_webhook_task

        # Mock the task's request context for the log line
        deliver_webhook_task.request.retries = 0
        deliver_webhook_task.request.id = "task-success"

        result = deliver_webhook_task.__wrapped__("https://example.com/hook", {"event": "test"}, None, 123)
        assert result["status"] == "delivered"
        assert result["url"] == "https://example.com/hook"
        attempt = db_session.query(WebhookDeliveryAttempt).one()
        assert attempt.task_id == "task-success"
        assert attempt.webhook_config_id == 123
        assert attempt.status == "delivered"
        assert attempt.event == "test"

    def test_failure_raises_for_retry(self, mocker, db_session):
        """Task raises RuntimeError on delivery failure to trigger retry."""
        mocker.patch("app.tasks.webhook_tasks.deliver_webhook", return_value=False)
        mocker.patch("app.tasks.webhook_tasks.SessionLocal", return_value=db_session)

        from app.tasks.webhook_tasks import deliver_webhook_task

        deliver_webhook_task.request.retries = 0
        deliver_webhook_task.request.id = "task-failure"

        with pytest.raises(RuntimeError, match="Webhook delivery.*failed"):
            deliver_webhook_task.__wrapped__("https://example.com/hook", {"event": "test"}, None)
        attempt = db_session.query(WebhookDeliveryAttempt).one()
        assert attempt.task_id == "task-failure"
        assert attempt.status == "failed"
        assert "failed" in attempt.error

    def test_final_failure_logs_dead_letter_context(self, mocker):
        """After retry exhaustion, webhook failures are logged with dead-letter context."""
        mock_logger = mocker.patch("app.tasks.webhook_tasks.logger")
        mock_record = mocker.patch("app.tasks.webhook_tasks._record_delivery_attempt")

        from app.tasks.webhook_tasks import deliver_webhook_task

        deliver_webhook_task.on_failure(
            RuntimeError("delivery failed"),
            "task-dead",
            ("https://example.com/hook", {"event": "document.failed"}, None, 123, 456),
            {},
            None,
        )

        mock_record.assert_called_once_with(
            url="https://example.com/hook",
            payload={"event": "document.failed"},
            status="dead_lettered",
            attempt_number=deliver_webhook_task.max_retries + 1,
            task_id="task-dead",
            webhook_config_id=123,
            delivery_id=456,
            error="delivery failed",
        )
        mock_logger.error.assert_called_once_with(
            "Webhook delivery dead-lettered: task_id=%s url=%s event=%s attempts=%d error=%s",
            "task-dead",
            "https://example.com/hook",
            "document.failed",
            deliver_webhook_task.max_retries + 1,
            mocker.ANY,
        )


# ---------------------------------------------------------------------------
# Unit tests – document task webhook dispatch adapters
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDocumentTaskWebhookDispatch:
    """Cover best-effort webhook dispatch paths in document tasks."""

    def test_routed_event_payload(self, mocker):
        """Routing dispatch includes the selected profile and rule context."""
        dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")
        record = Mock(
            id=42,
            original_filename="invoice.pdf",
            pipeline_id=7,
            pipeline_assignment_source="routing_rule",
            pipeline_routing_rule_id=3,
            pipeline_assignment_reason="Matched invoices",
        )

        from app.tasks.process_document import _dispatch_routed_webhook

        _dispatch_routed_webhook(record, "task-route")

        dispatch.assert_called_once_with(
            "document.routed",
            {
                "file_id": 42,
                "filename": "invoice.pdf",
                "pipeline_id": 7,
                "assignment_source": "routing_rule",
                "routing_rule_id": 3,
                "reason": "Matched invoices",
            },
        )

    def test_routed_event_failure_is_non_fatal(self, mocker):
        """Routing continues when webhook dispatch fails."""
        mocker.patch("app.utils.webhook.dispatch_webhook_event", side_effect=RuntimeError("offline"))
        record = Mock(
            id=42,
            original_filename="invoice.pdf",
            pipeline_id=7,
            pipeline_assignment_source="routing_rule",
            pipeline_routing_rule_id=3,
            pipeline_assignment_reason="Matched invoices",
        )

        from app.tasks.process_document import _dispatch_routed_webhook

        _dispatch_routed_webhook(record, "task-route")

    def test_metadata_event_payload(self, mocker):
        """Metadata dispatch reports the stable file identity and changed keys."""
        dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")
        record = Mock(id=42, original_filename="invoice.pdf")

        from app.tasks.embed_metadata_into_pdf import _dispatch_metadata_updated_webhook

        _dispatch_metadata_updated_webhook(
            record,
            {"tags": ["invoice"], "document_type": "Invoice"},
            "task-metadata",
        )

        dispatch.assert_called_once_with(
            "document.metadata_updated",
            {
                "file_id": 42,
                "filename": "invoice.pdf",
                "updated_fields": ["document_type", "tags"],
            },
        )

    def test_metadata_event_skips_empty_metadata(self, mocker):
        """Empty metadata does not produce a misleading update event."""
        dispatch = mocker.patch("app.utils.webhook.dispatch_webhook_event")
        record = Mock(id=42, original_filename="invoice.pdf")

        from app.tasks.embed_metadata_into_pdf import _dispatch_metadata_updated_webhook

        _dispatch_metadata_updated_webhook(record, {}, "task-metadata")

        dispatch.assert_not_called()

    def test_metadata_event_failure_is_non_fatal(self, mocker):
        """Metadata persistence continues when webhook dispatch fails."""
        mocker.patch("app.utils.webhook.dispatch_webhook_event", side_effect=RuntimeError("offline"))
        record = Mock(id=42, original_filename="invoice.pdf")

        from app.tasks.embed_metadata_into_pdf import _dispatch_metadata_updated_webhook

        _dispatch_metadata_updated_webhook(record, {"tags": ["invoice"]}, "task-metadata")


@pytest.mark.unit
class TestWebhookDashboardTemplate:
    """Guard the admin dashboard's security and accessibility contract."""

    @staticmethod
    def _template() -> str:
        return Path("frontend/templates/webhooks_dashboard.html").read_text(encoding="utf-8")

    def test_mutations_include_csrf_header(self):
        """Save, delete, and replay requests share the page CSRF token."""
        template = self._template()

        assert 'meta[name="csrf-token"]' in template
        assert "'X-CSRF-Token': this.csrfToken" in template
        assert template.count("this.csrfHeaders()") >= 3

    def test_toast_and_delivery_table_are_accessible(self):
        """Feedback and delivery history expose screen-reader semantics."""
        template = self._template()

        assert 'role="status"' in template
        assert 'aria-live="polite"' in template
        assert '<caption class="sr-only">' in template
        assert template.count('<th scope="col"') == 4

    def test_dashboard_uses_translation_keys(self):
        """Dashboard headings and JavaScript feedback use the i18n catalog."""
        template = self._template()

        assert '{{ _("webhooks.heading") }}' in template
        assert '{{ _("webhooks.save_error") | tojson }}' in template
        assert '{{ _("webhooks.delete_confirm") | tojson }}' in template
        assert "x-text=\'hook.is_active ?" in template
        assert "x-text=\'editingId ?" in template
