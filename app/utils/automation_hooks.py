"""Automation hook utilities for Zapier / Make.com integration.

Provides helpers to build Zapier-compatible flat payloads, query active
automation hook subscriptions, and fan-out event delivery to all matching
hooks via Celery tasks.

The payload format is intentionally *flat* (no nested ``data`` key) so that
Zapier and Make.com can map fields without JSONPath expressions.  An ``id``
field is included for Zapier deduplication.
"""

import json
import logging
import time
import uuid
from typing import Any

from app.config import settings
from app.database import SessionLocal
from app.models import AutomationHook
from app.utils.webhook import VALID_EVENTS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def build_zapier_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Build a flat, Zapier-compatible webhook payload.

    Zapier works best with flat JSON objects that include an ``id`` field
    for deduplication.  This function merges event metadata into the
    top-level object alongside the event-specific *data*.

    Args:
        event: The event name (e.g. ``document.processed``).
        data: Event-specific key/value pairs.

    Returns:
        A flat dictionary suitable for Zapier / Make.com consumption.
    """
    return {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "event": event,
        "timestamp": time.time(),
        **data,
    }


# ---------------------------------------------------------------------------
# Sample payloads (used by the /triggers/sample endpoint)
# ---------------------------------------------------------------------------

#: Example payloads that Zapier uses for field-mapping during Zap creation.
SAMPLE_PAYLOADS: dict[str, dict[str, Any]] = {
    "document.uploaded": {
        "id": "evt_sample0001",
        "event": "document.uploaded",
        "timestamp": 1710000000.0,
        "document_id": 42,
        "filename": "invoice_2024.pdf",
        "content_type": "application/pdf",
        "size_bytes": 204800,
        "owner_id": "user@example.com",
    },
    "document.processed": {
        "id": "evt_sample0002",
        "event": "document.processed",
        "timestamp": 1710000060.0,
        "document_id": 42,
        "filename": "invoice_2024.pdf",
        "status": "processed",
        "title": "Invoice #1234",
        "owner_id": "user@example.com",
    },
    "document.failed": {
        "id": "evt_sample0003",
        "event": "document.failed",
        "timestamp": 1710000120.0,
        "document_id": 42,
        "filename": "corrupt.pdf",
        "status": "failed",
        "error": "Unable to extract text from document",
        "owner_id": "user@example.com",
    },
    "user.signup": {
        "id": "evt_sample0004",
        "event": "user.signup",
        "timestamp": 1710000180.0,
        "user_id": "newuser@example.com",
        "display_name": "Jane Doe",
    },
    "user.plan_changed": {
        "id": "evt_sample0005",
        "event": "user.plan_changed",
        "timestamp": 1710000240.0,
        "user_id": "user@example.com",
        "old_tier": "free",
        "new_tier": "pro",
    },
    "user.payment_issue": {
        "id": "evt_sample0006",
        "event": "user.payment_issue",
        "timestamp": 1710000300.0,
        "user_id": "user@example.com",
        "issue": "Credit card declined",
    },
}


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------


def get_active_hooks_for_event(event: str) -> list[dict[str, Any]]:
    """Return all active automation hooks subscribed to *event*.

    Args:
        event: The event name to filter on.

    Returns:
        A list of dicts with ``id``, ``target_url``, ``secret``, and
        ``events`` keys.
    """
    db = SessionLocal()
    try:
        hooks = db.query(AutomationHook).filter(AutomationHook.is_active.is_(True)).all()
        result: list[dict[str, Any]] = []
        for hook in hooks:
            try:
                subscribed = json.loads(hook.events)
            except (json.JSONDecodeError, TypeError):
                subscribed = []
            if event in subscribed:
                result.append(
                    {
                        "id": hook.id,
                        "target_url": hook.target_url,
                        "secret": hook.secret,
                        "events": subscribed,
                    }
                )
        return result
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_automation_hooks(event: str, data: dict[str, Any]) -> None:
    """Fan-out an event to all matching active automation hooks.

    Builds a Zapier-compatible flat payload and queues a Celery task for
    each matching hook so delivery is asynchronous with automatic retries.

    Args:
        event: Event name (must be in :data:`VALID_EVENTS`).
        data: Event-specific payload data.
    """
    if not settings.automation_hooks_enabled:
        return

    if event not in VALID_EVENTS:
        logger.warning("Ignoring unknown automation hook event: %s", event)
        return

    hooks = get_active_hooks_for_event(event)
    if not hooks:
        logger.debug("No active automation hooks for event %s", event)
        return

    payload = build_zapier_payload(event, data)

    from app.tasks.automation_tasks import deliver_automation_hook_task

    for hook in hooks:
        try:
            deliver_automation_hook_task.delay(hook["target_url"], payload, hook["secret"])
            logger.debug("Queued automation hook delivery to %s for event %s", hook["target_url"], event)
        except Exception as exc:
            logger.error("Failed to queue automation hook to %s: %s", hook["target_url"], exc)
