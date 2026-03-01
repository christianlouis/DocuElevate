"""Tests for the webhook subsystem (utility, API, and task)."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app.models import WebhookConfig
from app.utils.webhook import (
    build_payload,
    compute_signature,
    deliver_webhook,
    dispatch_webhook_event,
    get_active_webhooks_for_event,
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
        mock_post = mocker.patch("app.utils.webhook.requests.post")
        mock_post.return_value = MagicMock(ok=True, status_code=200)

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is True
        mock_post.assert_called_once()

    def test_non_2xx_returns_false(self, mocker):
        """A non-2xx response returns False."""
        mock_post = mocker.patch("app.utils.webhook.requests.post")
        mock_post.return_value = MagicMock(ok=False, status_code=500)

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is False

    def test_request_exception_returns_false(self, mocker):
        """A network error returns False."""
        import requests

        mocker.patch("app.utils.webhook.requests.post", side_effect=requests.ConnectionError("fail"))

        result = deliver_webhook("https://example.com/hook", {"event": "test"})
        assert result is False

    def test_signature_header_included_when_secret(self, mocker):
        """X-Webhook-Signature header is present when a secret is supplied."""
        mock_post = mocker.patch("app.utils.webhook.requests.post")
        mock_post.return_value = MagicMock(ok=True, status_code=200)

        deliver_webhook("https://example.com/hook", {"event": "test"}, secret="abc")
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert "X-Webhook-Signature" in headers
        assert headers["X-Webhook-Signature"].startswith("sha256=")

    def test_no_signature_header_without_secret(self, mocker):
        """X-Webhook-Signature header is absent when no secret is supplied."""
        mock_post = mocker.patch("app.utils.webhook.requests.post")
        mock_post.return_value = MagicMock(ok=True, status_code=200)

        deliver_webhook("https://example.com/hook", {"event": "test"})
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert "X-Webhook-Signature" not in headers


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

    def test_success_returns_status_dict(self, mocker):
        """Task returns a dict on successful delivery."""
        mocker.patch("app.tasks.webhook_tasks.deliver_webhook", return_value=True)

        from app.tasks.webhook_tasks import deliver_webhook_task

        # Mock the task's request context for the log line
        deliver_webhook_task.request.retries = 0

        result = deliver_webhook_task.__wrapped__("https://example.com/hook", {"event": "test"}, None)
        assert result["status"] == "delivered"
        assert result["url"] == "https://example.com/hook"

    def test_failure_raises_for_retry(self, mocker):
        """Task raises RuntimeError on delivery failure to trigger retry."""
        mocker.patch("app.tasks.webhook_tasks.deliver_webhook", return_value=False)

        from app.tasks.webhook_tasks import deliver_webhook_task

        deliver_webhook_task.request.retries = 0

        with pytest.raises(RuntimeError, match="Webhook delivery.*failed"):
            deliver_webhook_task.__wrapped__("https://example.com/hook", {"event": "test"}, None)
