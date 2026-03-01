"""Webhook delivery utility for notifying external systems of document events.

Provides functions to dispatch webhook payloads with HMAC-SHA256 signatures
and to query active webhook configurations from the database.

Supported events:
- ``document.uploaded``  – a new document has been ingested
- ``document.processed`` – a document finished processing successfully
- ``document.failed``    – document processing failed
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import requests

from app.database import SessionLocal
from app.models import WebhookConfig

logger = logging.getLogger(__name__)

#: Events recognised by the webhook subsystem.
VALID_EVENTS: frozenset[str] = frozenset(
    {
        "document.uploaded",
        "document.processed",
        "document.failed",
    }
)

#: Timeout (seconds) for outgoing webhook HTTP requests.
WEBHOOK_TIMEOUT = 10


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute an HMAC-SHA256 hex-digest for *payload_bytes* using *secret*.

    Args:
        payload_bytes: The raw JSON body to sign.
        secret: The shared secret string.

    Returns:
        ``sha256=<hex-digest>`` signature string.
    """
    mac = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def deliver_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> bool:
    """Send a single webhook POST request.

    Args:
        url: Target URL.
        payload: JSON-serialisable dictionary.
        secret: If provided, an ``X-Webhook-Signature`` header is included.

    Returns:
        ``True`` when the remote server responds with a 2xx status.
    """
    body = json.dumps(payload, default=str, sort_keys=True)
    body_bytes = body.encode("utf-8")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Signature"] = compute_signature(body_bytes, secret)

    try:
        resp = requests.post(url, data=body_bytes, headers=headers, timeout=WEBHOOK_TIMEOUT)
        if resp.ok:
            logger.info("Webhook delivered to %s (status %d)", url, resp.status_code)
            return True
        logger.warning("Webhook to %s returned status %d", url, resp.status_code)
        return False
    except requests.RequestException as exc:
        logger.error("Webhook delivery to %s failed: %s", url, exc)
        return False


def build_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Build a standardised webhook payload envelope.

    Args:
        event: The event name (e.g. ``document.uploaded``).
        data: Event-specific data.

    Returns:
        Dictionary with ``event``, ``timestamp``, and ``data`` keys.
    """
    return {
        "event": event,
        "timestamp": time.time(),
        "data": data,
    }


def get_active_webhooks_for_event(event: str) -> list[dict[str, Any]]:
    """Return all active webhook configs subscribed to *event*.

    Queries the database directly so this helper can be called from both the
    API layer and Celery tasks.

    Args:
        event: The event name to filter on.

    Returns:
        A list of dicts with ``id``, ``url``, ``secret``, and ``events`` keys.
    """
    db = SessionLocal()
    try:
        configs = db.query(WebhookConfig).filter(WebhookConfig.is_active.is_(True)).all()
        result: list[dict[str, Any]] = []
        for cfg in configs:
            try:
                subscribed = json.loads(cfg.events)
            except (json.JSONDecodeError, TypeError):
                subscribed = []
            if event in subscribed:
                result.append(
                    {
                        "id": cfg.id,
                        "url": cfg.url,
                        "secret": cfg.secret,
                        "events": subscribed,
                    }
                )
        return result
    finally:
        db.close()


def dispatch_webhook_event(event: str, data: dict[str, Any]) -> None:
    """Fan-out a webhook event to all matching active configurations.

    This is the main entry-point used by application code to trigger webhooks.
    It delegates to :func:`deliver_webhook_task` (Celery) for each matching
    webhook so delivery happens asynchronously with automatic retries.

    Args:
        event: Event name (must be in :data:`VALID_EVENTS`).
        data: Event-specific payload data.
    """
    if event not in VALID_EVENTS:
        logger.warning("Ignoring unknown webhook event: %s", event)
        return

    webhooks = get_active_webhooks_for_event(event)
    if not webhooks:
        logger.debug("No active webhooks for event %s", event)
        return

    payload = build_payload(event, data)

    # Import here to avoid circular dependency with celery_app
    from app.tasks.webhook_tasks import deliver_webhook_task

    for wh in webhooks:
        try:
            deliver_webhook_task.delay(wh["url"], payload, wh["secret"])
            logger.debug("Queued webhook delivery to %s for event %s", wh["url"], event)
        except Exception as exc:
            logger.error("Failed to queue webhook to %s: %s", wh["url"], exc)
