"""Celery task for asynchronous webhook delivery with retry and backoff.

Uses :class:`~app.tasks.retry_config.BaseTaskWithRetry` so failed deliveries
are automatically retried with exponential backoff (default: 60 s, 300 s,
900 s) and ±20 % jitter.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery
from app.database import SessionLocal
from app.models import WebhookDeliveryAttempt
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.webhook import deliver_webhook

logger = logging.getLogger(__name__)


def _payload_event(payload: dict[str, Any] | None) -> str | None:
    if isinstance(payload, dict):
        event = payload.get("event")
        return str(event) if event else None
    return None


def _record_delivery_attempt(
    *,
    url: str,
    payload: dict[str, Any],
    status: str,
    attempt_number: int,
    task_id: str | None,
    webhook_config_id: int | None = None,
    delivery_id: int | None = None,
    error: str | None = None,
) -> int | None:
    """Create or update a persisted webhook delivery attempt."""
    db = SessionLocal()
    try:
        attempt = None
        if delivery_id is not None:
            attempt = db.query(WebhookDeliveryAttempt).filter(WebhookDeliveryAttempt.id == delivery_id).first()
        if attempt is None:
            attempt = WebhookDeliveryAttempt(
                webhook_config_id=webhook_config_id,
                url=url,
                event=_payload_event(payload),
                payload=json.dumps(payload, default=str, sort_keys=True),
            )
            db.add(attempt)

        attempt.task_id = task_id
        attempt.status = status
        attempt.attempt_number = attempt_number
        attempt.error = error
        if status == "delivered":
            attempt.delivered_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(attempt)
        return attempt.id
    except Exception:
        db.rollback()
        logger.exception("Failed to persist webhook delivery attempt for url=%s", url)
        return delivery_id
    finally:
        db.close()


class WebhookDeliveryTask(BaseTaskWithRetry):
    """Retry policy plus dead-letter logging for outbound webhook delivery."""

    def on_failure(
        self, exc: BaseException, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any
    ) -> None:
        """Log final delivery failures after Celery has exhausted retries."""
        url = args[0] if len(args) > 0 else kwargs.get("url")
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        webhook_config_id = args[3] if len(args) > 3 else kwargs.get("webhook_config_id")
        delivery_id = args[4] if len(args) > 4 else kwargs.get("delivery_id")
        event = payload.get("event") if isinstance(payload, dict) else None
        if isinstance(url, str) and isinstance(payload, dict):
            _record_delivery_attempt(
                url=url,
                payload=payload,
                status="dead_lettered",
                attempt_number=self.max_retries + 1,
                task_id=task_id,
                webhook_config_id=webhook_config_id,
                delivery_id=delivery_id,
                error=str(exc),
            )
        logger.error(
            "Webhook delivery dead-lettered: task_id=%s url=%s event=%s attempts=%d error=%s",
            task_id,
            url,
            event,
            self.max_retries + 1,
            exc,
        )
        super().on_failure(exc, task_id, args, kwargs, einfo)


@celery.task(base=WebhookDeliveryTask, bind=True, name="webhook.deliver")
def deliver_webhook_task(
    self,
    url: str,
    payload: dict[str, Any],
    secret: str | None = None,
    webhook_config_id: int | None = None,
    delivery_id: int | None = None,
) -> dict[str, Any]:
    """Deliver a webhook payload to *url* with automatic retries.

    Args:
        url: Target webhook URL.
        payload: The full webhook payload envelope.
        secret: Optional shared secret for HMAC-SHA256 signing.

    Returns:
        A dict with ``status`` and ``url`` on success.

    Raises:
        RuntimeError: Re-raised to trigger Celery retry on delivery failure.
    """
    attempt_number = self.request.retries + 1
    task_id = getattr(self.request, "id", None)
    logger.info("Delivering webhook to %s (attempt %d/%d)", url, attempt_number, self.max_retries + 1)

    persisted_id = _record_delivery_attempt(
        url=url,
        payload=payload,
        status="running",
        attempt_number=attempt_number,
        task_id=task_id,
        webhook_config_id=webhook_config_id,
        delivery_id=delivery_id,
    )

    success = deliver_webhook(url, payload, secret)
    if success:
        _record_delivery_attempt(
            url=url,
            payload=payload,
            status="delivered",
            attempt_number=attempt_number,
            task_id=task_id,
            webhook_config_id=webhook_config_id,
            delivery_id=persisted_id,
        )
        return {"status": "delivered", "url": url, "delivery_id": persisted_id}

    _record_delivery_attempt(
        url=url,
        payload=payload,
        status="failed",
        attempt_number=attempt_number,
        task_id=task_id,
        webhook_config_id=webhook_config_id,
        delivery_id=persisted_id,
        error=f"Webhook delivery to {url} failed",
    )
    raise RuntimeError(f"Webhook delivery to {url} failed")
