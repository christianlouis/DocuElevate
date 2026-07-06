"""Celery task for asynchronous webhook delivery with retry and backoff.

Uses :class:`~app.tasks.retry_config.BaseTaskWithRetry` so failed deliveries
are automatically retried with exponential backoff (default: 60 s, 300 s,
900 s) and ±20 % jitter.
"""

import logging
from typing import Any

from app.celery_app import celery
from app.tasks.retry_config import BaseTaskWithRetry
from app.utils.webhook import deliver_webhook

logger = logging.getLogger(__name__)


class WebhookDeliveryTask(BaseTaskWithRetry):
    """Retry policy plus dead-letter logging for outbound webhook delivery."""

    def on_failure(
        self, exc: BaseException, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], einfo: Any
    ) -> None:
        """Log final delivery failures after Celery has exhausted retries."""
        url = args[0] if len(args) > 0 else kwargs.get("url")
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        event = payload.get("event") if isinstance(payload, dict) else None
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
def deliver_webhook_task(self, url: str, payload: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
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
    logger.info("Delivering webhook to %s (attempt %d/%d)", url, self.request.retries + 1, self.max_retries + 1)

    success = deliver_webhook(url, payload, secret)
    if success:
        return {"status": "delivered", "url": url}

    raise RuntimeError(f"Webhook delivery to {url} failed")
