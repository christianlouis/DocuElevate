"""Webhook delivery utility for notifying external systems of document events.

Provides functions to dispatch webhook payloads with HMAC-SHA256 signatures
and to query active webhook configurations from the database.

Supported events:
- ``document.uploaded``  – a new document has been ingested
- ``document.processed`` – a document finished processing successfully
- ``document.failed``    – document processing failed
- ``document.routed``    – a document was assigned to a processing profile
- ``document.metadata_updated`` – document metadata was created or changed
- ``user.signup``        – a new user account was created
- ``user.plan_changed``  – a user's subscription plan changed
- ``user.payment_issue`` – a payment issue was reported for a user
"""

import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import socket
import ssl
import time
from typing import Any
from urllib.parse import ParseResult, urlparse

from app.database import SessionLocal
from app.models import WebhookConfig

logger = logging.getLogger(__name__)

#: Version for the outbound webhook payload envelope.
WEBHOOK_PAYLOAD_VERSION = "1.0"

#: Events recognised by the webhook subsystem.
VALID_EVENTS: frozenset[str] = frozenset(
    {
        "document.uploaded",
        "document.processed",
        "document.failed",
        "document.routed",
        "document.metadata_updated",
        "user.signup",
        "user.plan_changed",
        "user.payment_issue",
    }
)

#: Timeout (seconds) for outgoing webhook HTTP requests.
WEBHOOK_TIMEOUT = 10
METADATA_ENDPOINTS = {
    "169.254.169.254",
    "169.254.169.253",
    "metadata.google.internal",
}


def _normalise_hostname(hostname: str) -> str:
    return hostname.rstrip(".").lower()


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True

    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def _resolve_public_address(hostname: str, port: int) -> str | None:
    """Resolve *hostname* and return one validated public address.

    Every returned DNS address must be publicly routable. Blocking the whole
    hostname when any answer is private prevents DNS rebinding from picking a
    different address than the one validated here.
    """
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        logger.warning("Webhook host %s could not be resolved: %s", hostname, exc)
        return None

    candidates: list[str] = []
    for *_, sockaddr in addresses:
        address = sockaddr[0]
        if _is_blocked_ip(address):
            logger.warning("Webhook host %s resolved to blocked address %s", hostname, address)
            return None
        candidates.append(address)

    return candidates[0] if candidates else None


def _send_pinned_post(
    parsed_url: ParseResult,
    address: str,
    body_bytes: bytes,
    headers: dict[str, str],
) -> tuple[bool, int]:
    """Send the webhook over a socket pinned to a pre-validated address."""
    hostname = parsed_url.hostname
    if not hostname:
        return False, 0

    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    raw_socket = socket.create_connection((address, port), timeout=WEBHOOK_TIMEOUT)
    connection = None
    if parsed_url.scheme == "https":
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            raw_socket = context.wrap_socket(raw_socket, server_hostname=hostname)
        except Exception:
            raw_socket.close()
            raise

    try:
        path = parsed_url.path or "/"
        if parsed_url.query:
            path = f"{path}?{parsed_url.query}"

        host_header = hostname
        if ":" in hostname and not hostname.startswith("["):
            host_header = f"[{hostname}]"
        default_port = 443 if parsed_url.scheme == "https" else 80
        if port != default_port:
            host_header = f"{host_header}:{port}"
        request_headers = {key: value for key, value in headers.items() if key.lower() != "host"}
        request_headers["Host"] = host_header

        connection_cls = http.client.HTTPSConnection if parsed_url.scheme == "https" else http.client.HTTPConnection
        connection = connection_cls(hostname, port, timeout=WEBHOOK_TIMEOUT)
        connection.sock = raw_socket
        connection.request("POST", path, body=body_bytes, headers=request_headers)
        response = connection.getresponse()
        return 200 <= response.status < 300, response.status
    finally:
        if connection is not None:
            connection.close()
        else:
            raw_socket.close()


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


def verify_signature(payload_bytes: bytes, secret: str, signature: str | None) -> bool:
    """Return whether *signature* matches *payload_bytes* for *secret*.

    The comparison is constant-time and accepts the same ``sha256=<digest>``
    value that DocuElevate sends in ``X-Webhook-Signature``.
    """
    if not signature or not signature.startswith("sha256="):
        return False
    expected = compute_signature(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)


def deliver_webhook_with_status(
    url: str, payload: dict[str, Any], secret: str | None = None
) -> tuple[bool, int | None]:
    """Send a single webhook POST request.

    Args:
        url: Target URL.
        payload: JSON-serialisable dictionary.
        secret: If provided, an ``X-Webhook-Signature`` header is included.

    Returns:
        A tuple containing success and the remote HTTP status, when available.
    """
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"}:
        logger.warning("Webhook to %s blocked: invalid scheme %s", url, parsed_url.scheme)
        return False, None

    hostname = parsed_url.hostname
    if not hostname:
        logger.warning("Webhook to %s blocked: missing hostname", url)
        return False, None

    normalised_hostname = _normalise_hostname(hostname)
    if normalised_hostname in METADATA_ENDPOINTS:
        logger.warning("Webhook to %s blocked: private or metadata endpoint", url)
        return False, None

    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    address = _resolve_public_address(normalised_hostname, port)
    if address is None:
        logger.warning("Webhook to %s blocked: private, metadata, or unresolved endpoint", url)
        return False, None

    body = json.dumps(payload, default=str, sort_keys=True)
    body_bytes = body.encode("utf-8")

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if payload.get("event"):
        headers["X-DocuElevate-Event"] = str(payload["event"])
    if payload.get("version"):
        headers["X-DocuElevate-Webhook-Version"] = str(payload["version"])
    if secret:
        headers["X-Webhook-Signature"] = compute_signature(body_bytes, secret)

    try:
        ok, status_code = _send_pinned_post(parsed_url, address, body_bytes, headers)
        if ok:
            logger.info("Webhook delivered to %s (status %d)", url, status_code)
            return True, status_code
        logger.warning("Webhook to %s returned status %d", url, status_code)
        return False, status_code
    except (OSError, http.client.HTTPException) as exc:
        logger.error("Webhook delivery to %s failed: %s", url, exc)
        return False, None


def deliver_webhook(url: str, payload: dict[str, Any], secret: str | None = None) -> bool:
    """Send a webhook and retain the legacy boolean result contract."""
    success, _status_code = deliver_webhook_with_status(url, payload, secret)
    return success


def build_payload(event: str, data: dict[str, Any]) -> dict[str, Any]:
    """Build a standardised webhook payload envelope.

    Args:
        event: The event name (e.g. ``document.uploaded``).
        data: Event-specific data.

    Returns:
        Dictionary with ``event``, ``timestamp``, and ``data`` keys.
    """
    return {
        "version": WEBHOOK_PAYLOAD_VERSION,
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

    Also dispatches to automation hooks (Zapier / Make.com) if enabled.

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
    else:
        payload = build_payload(event, data)

        # Import here to avoid circular dependency with celery_app
        from app.tasks.webhook_tasks import deliver_webhook_task

        for wh in webhooks:
            try:
                deliver_webhook_task.delay(wh["url"], payload, wh["secret"], webhook_config_id=wh.get("id"))
                logger.debug("Queued webhook delivery to %s for event %s", wh["url"], event)
            except Exception as exc:
                logger.error("Failed to queue webhook to %s: %s", wh["url"], exc)

    # Also fan-out to Zapier / Make.com automation hooks
    try:
        from app.utils.automation_hooks import dispatch_automation_hooks

        dispatch_automation_hooks(event, data)
    except Exception as exc:
        logger.error("Failed to dispatch automation hooks for event %s: %s", event, exc)
