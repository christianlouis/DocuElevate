"""
Audit log REST API endpoints.

Provides read-only access to the comprehensive audit log for admin users.
Events are append-only — there are no update or delete endpoints.
"""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.utils.audit_service import count_events, query_events

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/audit-logs")
@require_login
async def list_audit_logs(
    request: Request,
    db: Session = Depends(get_db),
    action: str | None = Query(None, description="Filter by action (exact match)"),
    user: str | None = Query(None, description="Filter by username"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    severity: str | None = Query(None, description="Filter by severity level"),
    since: datetime | None = Query(None, description="Only events at or after this ISO-8601 timestamp"),
    until: datetime | None = Query(None, description="Only events at or before this ISO-8601 timestamp"),
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip for pagination"),
) -> dict[str, Any]:
    """Return audit log entries with optional filtering and pagination.

    Requires authentication. Returns events in reverse chronological order.
    """
    entries = query_events(
        db,
        action=action,
        user=user,
        resource_type=resource_type,
        severity=severity,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    total = count_events(
        db,
        action=action,
        user=user,
        resource_type=resource_type,
        severity=severity,
        since=since,
        until=until,
    )
    return {
        "items": [_serialize(e) for e in entries],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit-logs/actions")
@require_login
async def list_distinct_actions(
    request: Request,
    db: Session = Depends(get_db),
) -> list[str]:
    """Return the distinct action values present in the audit log."""
    from app.models import AuditLog

    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in rows]


@router.get("/audit-logs/users")
@require_login
async def list_distinct_users(
    request: Request,
    db: Session = Depends(get_db),
) -> list[str]:
    """Return the distinct user values present in the audit log."""
    from app.models import AuditLog

    rows = db.query(AuditLog.user).distinct().order_by(AuditLog.user).all()
    return [r[0] for r in rows]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _serialize(entry) -> dict[str, Any]:
    """Convert an AuditLog row to a JSON-safe dict."""
    import json as _json

    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
        "user": entry.user,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "ip_address": entry.ip_address,
        "details": _json.loads(entry.details) if entry.details else None,
        "severity": entry.severity,
    }
