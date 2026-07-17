#!/usr/bin/env python3

import logging

import requests
from celery import shared_task

from app.config import settings

logger = logging.getLogger(__name__)


@shared_task
def ping_uptime_kuma():
    """
    Periodic Celery task that pings the configured Uptime Kuma URL
    to report that the document processor service is running.
    If no URL is configured, the task does nothing.
    """
    if not settings.uptime_kuma_url:
        logger.debug("Uptime Kuma URL not configured, skipping ping")
        return

    try:
        logger.info("Pinging configured Uptime Kuma endpoint")
        response = requests.get(settings.uptime_kuma_url, timeout=10)
        response.raise_for_status()
        logger.info(f"Successfully pinged Uptime Kuma: {response.status_code}")
        return True
    except requests.exceptions.RequestException as exc:
        # Requests may include the full push URL (including its secret token)
        # in exception messages. Log only the failure class.
        logger.error("Failed to ping Uptime Kuma (%s)", type(exc).__name__)
        return False
