"""Celery task for asynchronous automation hook delivery with retry and backoff.

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


@celery.task(base=BaseTaskWithRetry, bind=True, name="automation.deliver_hook")
def deliver_automation_hook_task(self, url: str, payload: dict[str, Any], secret: str | None = None) -> dict[str, Any]:
    """Deliver an automation hook payload to *url* with automatic retries.

    Args:
        url: Target webhook URL (provided by Zapier / Make.com).
        payload: The flat Zapier-compatible payload.
        secret: Optional shared secret for HMAC-SHA256 signing.

    Returns:
        A dict with ``status`` and ``url`` on success.

    Raises:
        RuntimeError: Re-raised to trigger Celery retry on delivery failure.
    """
    logger.info(
        "Delivering automation hook to %s (attempt %d/%d)",
        url,
        self.request.retries + 1,
        self.max_retries + 1,
    )

    success = deliver_webhook(url, payload, secret)
    if success:
        return {"status": "delivered", "url": url}

    raise RuntimeError(f"Automation hook delivery to {url} failed")
