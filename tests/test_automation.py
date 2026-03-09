"""Tests for the Zapier / Make.com automation integration.

Covers:
- Automation hook utility functions (payload builder, DB queries, dispatch)
- Automation hook Celery task
- REST hooks API endpoints (subscribe, unsubscribe, list, sample, events)
- Incoming action endpoints (upload)
- Integration with existing webhook dispatch
"""

import json
import time
from unittest.mock import MagicMock

import pytest

from app.models import AutomationHook
from app.utils.automation_hooks import (
    SAMPLE_PAYLOADS,
    build_zapier_payload,
    dispatch_automation_hooks,
    get_active_hooks_for_event,
)
from app.utils.webhook import VALID_EVENTS

# ---------------------------------------------------------------------------
# Unit tests – build_zapier_payload
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildZapierPayload:
    """Tests for the Zapier-compatible payload builder."""

    def test_contains_required_keys(self):
        """Payload must contain id, event, timestamp, plus data fields."""
        payload = build_zapier_payload("document.uploaded", {"document_id": 1})
        assert "id" in payload
        assert "event" in payload
        assert "timestamp" in payload
        assert "document_id" in payload

    def test_id_starts_with_evt(self):
        """ID field must start with 'evt_' for Zapier deduplication."""
        payload = build_zapier_payload("document.uploaded", {"document_id": 1})
        assert payload["id"].startswith("evt_")

    def test_event_matches_input(self):
        """Event field must match the event argument."""
        payload = build_zapier_payload("document.processed", {"document_id": 2})
        assert payload["event"] == "document.processed"

    def test_timestamp_is_recent(self):
        """Timestamp should be close to current time."""
        before = time.time()
        payload = build_zapier_payload("document.uploaded", {})
        after = time.time()
        assert before <= payload["timestamp"] <= after

    def test_data_is_flat(self):
        """Data fields should be merged into top level (flat, no nested 'data' key)."""
        payload = build_zapier_payload("document.uploaded", {"filename": "test.pdf", "size": 1024})
        assert payload["filename"] == "test.pdf"
        assert payload["size"] == 1024
        assert "data" not in payload

    def test_unique_ids(self):
        """Each call should produce a unique ID."""
        ids = {build_zapier_payload("document.uploaded", {})["id"] for _ in range(50)}
        assert len(ids) == 50


# ---------------------------------------------------------------------------
# Unit tests – SAMPLE_PAYLOADS
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSamplePayloads:
    """Tests for the sample payloads used by Zapier field mapping."""

    def test_all_events_have_samples(self):
        """Every valid event should have a sample payload."""
        for event in VALID_EVENTS:
            assert event in SAMPLE_PAYLOADS, f"Missing sample payload for {event}"

    def test_samples_contain_id_and_event(self):
        """Each sample should contain id and event keys."""
        for event, sample in SAMPLE_PAYLOADS.items():
            assert "id" in sample, f"Sample for {event} missing 'id'"
            assert sample["event"] == event


# ---------------------------------------------------------------------------
# Unit tests – get_active_hooks_for_event
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetActiveHooksForEvent:
    """Tests for querying active automation hooks from the database."""

    def test_returns_matching_hooks(self, mocker):
        """Only hooks subscribed to the event should be returned."""
        hook = MagicMock(
            id=1,
            target_url="https://hooks.zapier.com/1234",
            secret="abc",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
        )
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [hook]
        mocker.patch("app.utils.automation_hooks.SessionLocal", return_value=mock_session)

        result = get_active_hooks_for_event("document.uploaded")
        assert len(result) == 1
        assert result[0]["target_url"] == "https://hooks.zapier.com/1234"

    def test_excludes_non_matching_hooks(self, mocker):
        """Hooks for different events should not be returned."""
        hook = MagicMock(
            id=1,
            target_url="https://hooks.zapier.com/1234",
            secret=None,
            events=json.dumps(["document.processed"]),
            is_active=True,
        )
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = [hook]
        mocker.patch("app.utils.automation_hooks.SessionLocal", return_value=mock_session)

        result = get_active_hooks_for_event("document.uploaded")
        assert len(result) == 0

    def test_empty_when_no_hooks(self, mocker):
        """Empty list returned when no hooks exist."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mocker.patch("app.utils.automation_hooks.SessionLocal", return_value=mock_session)

        result = get_active_hooks_for_event("document.uploaded")
        assert result == []


# ---------------------------------------------------------------------------
# Unit tests – dispatch_automation_hooks
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDispatchAutomationHooks:
    """Tests for the automation hook dispatch function."""

    def test_ignores_unknown_events(self, mocker):
        """Unknown events should be silently ignored."""
        mocker.patch("app.utils.automation_hooks.settings", MagicMock(automation_hooks_enabled=True))
        mock_get = mocker.patch("app.utils.automation_hooks.get_active_hooks_for_event")
        dispatch_automation_hooks("bad.event", {})
        mock_get.assert_not_called()

    def test_skips_when_disabled(self, mocker):
        """No hooks should fire when automation_hooks_enabled is False."""
        mocker.patch("app.utils.automation_hooks.settings", MagicMock(automation_hooks_enabled=False))
        mock_get = mocker.patch("app.utils.automation_hooks.get_active_hooks_for_event")
        dispatch_automation_hooks("document.uploaded", {"file_id": 1})
        mock_get.assert_not_called()

    def test_queues_celery_task_for_each_hook(self, mocker):
        """A Celery task is queued for each matching hook."""
        mocker.patch("app.utils.automation_hooks.settings", MagicMock(automation_hooks_enabled=True))
        mocker.patch(
            "app.utils.automation_hooks.get_active_hooks_for_event",
            return_value=[
                {"id": 1, "target_url": "https://hooks.zapier.com/a", "secret": "s", "events": ["document.uploaded"]},
                {"id": 2, "target_url": "https://hooks.zapier.com/b", "secret": None, "events": ["document.uploaded"]},
            ],
        )
        mock_task = mocker.patch("app.tasks.automation_tasks.deliver_automation_hook_task.delay")

        dispatch_automation_hooks("document.uploaded", {"file_id": 42})

        assert mock_task.call_count == 2

    def test_no_tasks_when_no_hooks(self, mocker):
        """No tasks should be queued when there are no matching hooks."""
        mocker.patch("app.utils.automation_hooks.settings", MagicMock(automation_hooks_enabled=True))
        mocker.patch("app.utils.automation_hooks.get_active_hooks_for_event", return_value=[])
        mock_task = mocker.patch("app.tasks.automation_tasks.deliver_automation_hook_task.delay")

        dispatch_automation_hooks("document.uploaded", {})

        mock_task.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests – deliver_automation_hook_task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeliverAutomationHookTask:
    """Tests for the automation hook Celery task."""

    def test_returns_success_dict(self, mocker):
        """Successful delivery returns status dict."""
        mocker.patch("app.tasks.automation_tasks.deliver_webhook", return_value=True)

        from app.tasks.automation_tasks import deliver_automation_hook_task

        deliver_automation_hook_task.request.retries = 0

        result = deliver_automation_hook_task.__wrapped__("https://hooks.zapier.com/test", {"event": "test"}, None)
        assert result["status"] == "delivered"
        assert result["url"] == "https://hooks.zapier.com/test"

    def test_raises_on_failure(self, mocker):
        """Failed delivery raises RuntimeError for Celery retry."""
        mocker.patch("app.tasks.automation_tasks.deliver_webhook", return_value=False)

        from app.tasks.automation_tasks import deliver_automation_hook_task

        deliver_automation_hook_task.request.retries = 0

        with pytest.raises(RuntimeError, match="Automation hook delivery"):
            deliver_automation_hook_task.__wrapped__("https://hooks.zapier.com/test", {"event": "test"}, None)


# ---------------------------------------------------------------------------
# Integration tests – webhook dispatch integration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWebhookDispatchIntegration:
    """Test that dispatch_webhook_event also triggers automation hooks."""

    def test_dispatch_triggers_automation_hooks(self, mocker):
        """dispatch_webhook_event should also call dispatch_automation_hooks."""
        mocker.patch("app.utils.webhook.get_active_webhooks_for_event", return_value=[])
        mock_auto = mocker.patch("app.utils.automation_hooks.dispatch_automation_hooks")

        from app.utils.webhook import dispatch_webhook_event

        dispatch_webhook_event("document.uploaded", {"file_id": 1})

        mock_auto.assert_called_once_with("document.uploaded", {"file_id": 1})


# ---------------------------------------------------------------------------
# Integration tests – API endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAutomationAPI:
    """Tests for the /api/automation/ endpoints."""

    def _with_auth(self, client):
        """Override auth dependency to simulate an authenticated user."""
        from app.api.automation import _require_api_user

        client.app.dependency_overrides[_require_api_user] = lambda: {
            "id": "testuser",
            "email": "test@example.com",
            "preferred_username": "testuser",
            "is_admin": False,
        }
        return client

    # ── Subscribe / Unsubscribe ──────────────────────────────────────

    def test_subscribe_hook(self, client):
        """POST /api/automation/hooks/subscribe creates a new hook."""
        self._with_auth(client)
        resp = client.post(
            "/api/automation/hooks/subscribe",
            json={
                "target_url": "https://hooks.zapier.com/test",
                "events": ["document.uploaded"],
                "hook_type": "zapier",
                "description": "My Zap",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["target_url"] == "https://hooks.zapier.com/test"
        assert data["events"] == ["document.uploaded"]
        assert data["is_active"] is True
        assert data["hook_type"] == "zapier"

    def test_subscribe_with_secret(self, client):
        """POST /api/automation/hooks/subscribe with secret masks it."""
        self._with_auth(client)
        resp = client.post(
            "/api/automation/hooks/subscribe",
            json={
                "target_url": "https://hooks.zapier.com/secret",
                "events": ["document.processed"],
                "secret": "my-signing-secret",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["has_secret"] is True
        assert "secret" not in data

    def test_subscribe_invalid_event(self, client):
        """POST /api/automation/hooks/subscribe rejects invalid events."""
        self._with_auth(client)
        resp = client.post(
            "/api/automation/hooks/subscribe",
            json={
                "target_url": "https://hooks.zapier.com/bad",
                "events": ["bad.event"],
            },
        )
        assert resp.status_code == 422

    def test_unsubscribe_hook(self, client, db_session):
        """DELETE /api/automation/hooks/{id} removes the hook."""
        self._with_auth(client)
        hook = AutomationHook(
            target_url="https://hooks.zapier.com/del",
            events=json.dumps(["document.uploaded"]),
            is_active=True,
            hook_type="zapier",
        )
        db_session.add(hook)
        db_session.commit()
        hook_id = hook.id

        resp = client.delete(f"/api/automation/hooks/{hook_id}")
        assert resp.status_code == 204

    def test_unsubscribe_not_found(self, client):
        """DELETE /api/automation/hooks/9999 returns 404."""
        self._with_auth(client)
        resp = client.delete("/api/automation/hooks/9999")
        assert resp.status_code == 404

    # ── List hooks ───────────────────────────────────────────────────

    def test_list_hooks(self, client, db_session):
        """GET /api/automation/hooks returns all hooks."""
        self._with_auth(client)
        hook = AutomationHook(
            target_url="https://hooks.zapier.com/list",
            events=json.dumps(["document.processed"]),
            is_active=True,
            hook_type="make",
        )
        db_session.add(hook)
        db_session.commit()

        resp = client.get("/api/automation/hooks")
        assert resp.status_code == 200
        items = resp.json()
        assert any(h["target_url"] == "https://hooks.zapier.com/list" for h in items)

    # ── Sample trigger data ──────────────────────────────────────────

    def test_trigger_sample(self, client):
        """GET /api/automation/triggers/sample/{event} returns sample data."""
        self._with_auth(client)
        resp = client.get("/api/automation/triggers/sample/document.uploaded")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["event"] == "document.uploaded"
        assert "id" in data[0]

    def test_trigger_sample_unknown_event(self, client):
        """GET /api/automation/triggers/sample/bad returns 404."""
        self._with_auth(client)
        resp = client.get("/api/automation/triggers/sample/bad.event")
        assert resp.status_code == 404

    # ── Events listing ───────────────────────────────────────────────

    def test_list_events(self, client):
        """GET /api/automation/events returns valid event types."""
        self._with_auth(client)
        resp = client.get("/api/automation/events")
        assert resp.status_code == 200
        events = resp.json()
        assert "document.uploaded" in events
        assert "document.processed" in events
        assert "document.failed" in events

    # ── Incoming action: upload ──────────────────────────────────────

    def test_action_upload(self, client, mocker):
        """POST /api/automation/actions/upload accepts a file."""
        self._with_auth(client)
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mocker.patch("app.tasks.process_document.process_document.delay", return_value=mock_task)

        resp = client.post(
            "/api/automation/actions/upload",
            files={"file": ("test.pdf", b"fake-pdf-content", "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["filename"] == "test.pdf"
        assert data["task_id"] == "task-123"

    def test_action_upload_no_filename(self, client):
        """POST /api/automation/actions/upload rejects empty filename."""
        self._with_auth(client)
        resp = client.post(
            "/api/automation/actions/upload",
            files={"file": ("", b"content", "application/pdf")},
        )
        # FastAPI/Starlette returns 422 for invalid multipart form data
        assert resp.status_code in (400, 422)

    # ── Auth required ────────────────────────────────────────────────

    def test_requires_auth(self, client):
        """Endpoints return 401 without authentication."""
        from app.api.automation import _require_api_user

        client.app.dependency_overrides.pop(_require_api_user, None)

        resp = client.get("/api/automation/hooks")
        assert resp.status_code == 401
