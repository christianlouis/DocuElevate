#!/usr/bin/env python3

import logging
import time
from urllib.parse import urlsplit

import requests
from celery import shared_task

from app.config import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10
_MAX_ATTEMPTS = 3
_RETRY_DELAYS_SECONDS = (1, 2)
_RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 429})


def _safe_endpoint(url: str) -> str:
    """Return an endpoint label without path, query, or push-token material."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme and parsed.hostname:
            host = parsed.hostname
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return f"{parsed.scheme}://{host}"
    except ValueError:
        pass
    return "configured endpoint"


def _result(status: str, *, endpoint: str, attempts: int, message: str, **details: object) -> dict[str, object]:
    return {
        "status": status,
        "configured": True,
        "endpoint": endpoint,
        "attempts": attempts,
        "message": message,
        **details,
    }


def check_uptime_kuma(url: str | None = None) -> dict[str, object]:
    """Check the optional monitor with bounded retries and safe diagnostics."""
    target = url if url is not None else getattr(settings, "uptime_kuma_url", None)
    if not target:
        return {
            "status": "disabled",
            "configured": False,
            "attempts": 0,
            "message": "Uptime Kuma monitoring is disabled; configure UPTIME_KUMA_URL to enable it.",
        }

    endpoint = _safe_endpoint(target)
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                target,
                timeout=_REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            http_status = int(response.status_code)
            payload = None
            try:
                candidate = response.json()
                if isinstance(candidate, dict):
                    payload = candidate
            except (AttributeError, TypeError, ValueError, requests.exceptions.RequestException):
                pass
            if 200 <= http_status < 300 and not (isinstance(payload, dict) and payload.get("ok") is False):
                return _result(
                    "success",
                    endpoint=endpoint,
                    attempts=attempt,
                    http_status=http_status,
                    message=f"Uptime Kuma accepted the ping (HTTP {http_status}).",
                )

            retryable = http_status >= 500 or http_status in _RETRYABLE_HTTP_STATUS_CODES
            error_message = f"Uptime Kuma returned HTTP {http_status}. Check the push URL and monitor configuration."
            if isinstance(payload, dict) and payload.get("ok") is False:
                error_message = "Uptime Kuma rejected the ping (ok=false). Check the monitor configuration."
            error_kind = f"HTTP {http_status}"
            if not retryable or attempt == _MAX_ATTEMPTS:
                return _result(
                    "error",
                    endpoint=endpoint,
                    attempts=attempt,
                    http_status=http_status,
                    message=error_message,
                )
        except requests.exceptions.Timeout:
            retryable = True
            error_kind = "timeout"
            error_message = "Uptime Kuma did not respond before the timeout. Check network reachability."
        except requests.exceptions.RequestException as exc:
            retryable = True
            error_kind = type(exc).__name__
            error_message = f"Uptime Kuma request failed ({error_kind}). Check network reachability."

        if attempt == _MAX_ATTEMPTS:
            return _result("error", endpoint=endpoint, attempts=attempt, message=error_message)
        logger.warning(
            "Uptime Kuma ping failed for %s (%s); retrying (attempt %s/%s)",
            endpoint,
            error_kind,
            attempt,
            _MAX_ATTEMPTS,
        )
        time.sleep(_RETRY_DELAYS_SECONDS[attempt - 1])

    raise AssertionError("bounded Uptime Kuma retry loop did not return")


@shared_task
def ping_uptime_kuma() -> dict[str, object]:
    """
    Periodic Celery task that pings the configured Uptime Kuma URL
    to report that the document processor service is running.
    If no URL is configured, the task does nothing.
    """
    result = check_uptime_kuma()
    if result["status"] == "disabled":
        logger.debug("Uptime Kuma monitoring is disabled; skipping ping")
    elif result["status"] == "success":
        logger.info("Uptime Kuma ping succeeded for %s (HTTP %s)", result["endpoint"], result["http_status"])
    else:
        logger.warning(
            "Uptime Kuma ping failed for %s after %s attempt(s): %s",
            result["endpoint"],
            result["attempts"],
            result["message"],
        )
    return result
