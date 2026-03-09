"""
Comprehensive audit-event service for DocuElevate.

Provides helpers to **record** audit events (append-only database writes)
and to optionally **forward** them to external SIEM systems.

Supported SIEM transports:
* **Syslog** – RFC 5424 structured-data messages over UDP or TCP.
* **HTTP** – JSON POST payloads compatible with Splunk HEC, Logstash
  HTTP input, Grafana Loki push API, and any generic webhook endpoint.
"""

import json
import logging
import socket
import threading
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import Request
from sqlalchemy.orm import Session

from app.config import settings
from app.middleware.audit_log import get_client_ip, get_username
from app.models import AuditLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def record_event(
    db: Session,
    *,
    action: str,
    user: str = "system",
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
    severity: str = "info",
) -> AuditLog:
    """Persist an audit event and optionally forward it to SIEM.

    Args:
        db: Active SQLAlchemy session.
        action: Short action identifier (e.g. ``"login"``, ``"document.create"``).
        user: Username performing the action.
        resource_type: Category of the affected resource (``"document"``, ``"user"`` …).
        resource_id: Identifier of the affected resource.
        ip_address: Client IP address (``None`` when not applicable).
        details: Arbitrary key/value context serialised as JSON.
        severity: One of ``info``, ``warning``, ``error``, ``critical``.

    Returns:
        The newly created :class:`AuditLog` row.
    """
    details_json = json.dumps(details, default=str) if details else None

    entry = AuditLog(
        user=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        ip_address=ip_address,
        details=details_json,
        severity=severity,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Fire-and-forget SIEM forwarding in a background thread so we never
    # block the request path.
    if settings.audit_siem_enabled:
        payload = _build_siem_payload(entry)
        thread = threading.Thread(target=_forward_to_siem, args=(payload,), daemon=True)
        thread.start()

    return entry


def record_event_from_request(
    db: Session,
    request: Request,
    *,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    severity: str = "info",
) -> AuditLog:
    """Convenience wrapper that extracts user and IP from a :class:`Request`.

    Args:
        db: Active SQLAlchemy session.
        request: The current HTTP request.
        action: Short action identifier.
        resource_type: Category of the affected resource.
        resource_id: Identifier of the affected resource.
        details: Arbitrary key/value context serialised as JSON.
        severity: One of ``info``, ``warning``, ``error``, ``critical``.

    Returns:
        The newly created :class:`AuditLog` row.
    """
    return record_event(
        db,
        action=action,
        user=get_username(request),
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=get_client_ip(request),
        details=details,
        severity=severity,
    )


def query_events(
    db: Session,
    *,
    action: str | None = None,
    user: str | None = None,
    resource_type: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[AuditLog]:
    """Query audit log entries with optional filtering.

    Args:
        db: Active SQLAlchemy session.
        action: Filter by action string (exact match).
        user: Filter by username (exact match).
        resource_type: Filter by resource type (exact match).
        severity: Filter by severity level (exact match).
        since: Only events at or after this timestamp.
        until: Only events at or before this timestamp.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip (for pagination).

    Returns:
        List of :class:`AuditLog` rows ordered by *timestamp descending*.
    """
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if user:
        q = q.filter(AuditLog.user == user)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if severity:
        q = q.filter(AuditLog.severity == severity)
    if since:
        q = q.filter(AuditLog.timestamp >= since)
    if until:
        q = q.filter(AuditLog.timestamp <= until)
    return q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()


def count_events(
    db: Session,
    *,
    action: str | None = None,
    user: str | None = None,
    resource_type: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> int:
    """Return the total count of events matching the given filters.

    Args:
        db: Active SQLAlchemy session.
        action: Filter by action string.
        user: Filter by username.
        resource_type: Filter by resource type.
        severity: Filter by severity level.
        since: Only events at or after this timestamp.
        until: Only events at or before this timestamp.

    Returns:
        Integer count.
    """
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if user:
        q = q.filter(AuditLog.user == user)
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if severity:
        q = q.filter(AuditLog.severity == severity)
    if since:
        q = q.filter(AuditLog.timestamp >= since)
    if until:
        q = q.filter(AuditLog.timestamp <= until)
    return q.count()


# ---------------------------------------------------------------------------
# SIEM forwarding internals
# ---------------------------------------------------------------------------

_SYSLOG_FACILITY_LOCAL0 = 16
_SYSLOG_SEVERITY_MAP = {
    "info": 6,
    "warning": 4,
    "error": 3,
    "critical": 2,
}


def _build_siem_payload(entry: AuditLog) -> dict[str, Any]:
    """Convert an :class:`AuditLog` row into a plain dict for SIEM delivery."""
    ts = entry.timestamp if entry.timestamp else datetime.now(timezone.utc)
    return {
        "id": entry.id,
        "timestamp": ts.isoformat(),
        "user": entry.user,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "ip_address": entry.ip_address,
        "details": entry.details,
        "severity": entry.severity,
        "source": "docuelevate",
    }


def _forward_to_siem(payload: dict[str, Any]) -> None:
    """Route a SIEM payload to the configured transport."""
    transport = settings.audit_siem_transport.lower()
    try:
        if transport == "syslog":
            _send_syslog(payload)
        elif transport == "http":
            _send_http(payload)
        else:
            logger.warning("Unknown SIEM transport %r; skipping forwarding", transport)
    except Exception:
        logger.exception("Failed to forward audit event to SIEM (%s)", transport)


def _send_syslog(payload: dict[str, Any]) -> None:
    """Send a RFC 5424 syslog message to the configured receiver."""
    severity_num = _SYSLOG_SEVERITY_MAP.get(payload.get("severity", "info"), 6)
    priority = _SYSLOG_FACILITY_LOCAL0 * 8 + severity_num
    ts = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    hostname = socket.gethostname()
    app_name = "docuelevate"
    msg_id = payload.get("action", "-")

    # Structured data (SD) element with key event fields.
    sd = (
        f'[docuelevate@0 user="{payload.get("user", "-")}" '
        f'action="{payload.get("action", "-")}" '
        f'resource_type="{payload.get("resource_type", "-")}" '
        f'resource_id="{payload.get("resource_id", "-")}" '
        f'ip="{payload.get("ip_address", "-")}"]'
    )
    message = json.dumps(payload, default=str)
    syslog_msg = f"<{priority}>1 {ts} {hostname} {app_name} - {msg_id} {sd} {message}"

    proto = settings.audit_siem_syslog_protocol.lower()
    host = settings.audit_siem_syslog_host
    port = settings.audit_siem_syslog_port

    if proto == "tcp":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect((host, port))
            sock.sendall(syslog_msg.encode("utf-8"))
    else:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.sendto(syslog_msg.encode("utf-8"), (host, port))

    logger.debug("Syslog audit event sent to %s:%s (%s)", host, port, proto)


def _send_http(payload: dict[str, Any]) -> None:
    """POST a JSON audit event to the configured HTTP endpoint."""
    url = settings.audit_siem_http_url
    if not url:
        logger.warning("SIEM HTTP URL not configured; skipping HTTP forwarding")
        return

    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = settings.audit_siem_http_token
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Parse custom headers (comma-separated "Key:Value" pairs).
    raw_custom = settings.audit_siem_http_custom_headers
    if raw_custom:
        for raw_pair in raw_custom.split(","):
            pair = raw_pair.strip()
            if ":" in pair:
                k, _, v = pair.partition(":")
                headers[k.strip()] = v.strip()

    # Wrap in Splunk HEC-style envelope when URL contains ``/services/collector``.
    body: dict[str, Any]
    if "/services/collector" in url:
        body = {"event": payload, "sourcetype": "docuelevate:audit", "source": "docuelevate"}
    else:
        body = payload

    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()

    logger.debug("HTTP audit event forwarded to %s (status %s)", url, resp.status_code)
