"""
Audit log REST API endpoints.

Provides read-only access to the comprehensive audit log for admin users.
Events are append-only — there are no update or delete endpoints.
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.utils.audit_service import count_events, query_events

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependency singleton to satisfy Ruff B008 while maintaining default values for manual calls (e.g. in decorators).
_db_dep = Depends(get_db)
DbSession = Annotated[Session, _db_dep]


@router.get("/audit-logs")
@require_login
async def list_audit_logs(
    request: Request,
    db: DbSession = _db_dep,
    action: Annotated[str | None, Query(description="Filter by action (exact match)")] = None,
    user: Annotated[str | None, Query(description="Filter by username")] = None,
    resource_type: Annotated[str | None, Query(description="Filter by resource type")] = None,
    severity: Annotated[str | None, Query(description="Filter by severity level")] = None,
    since: Annotated[datetime | None, Query(description="Only events at or after this ISO-8601 timestamp")] = None,
    until: Annotated[datetime | None, Query(description="Only events at or before this ISO-8601 timestamp")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return")] = 50,
    offset: Annotated[int, Query(ge=0, description="Rows to skip for pagination")] = 0,
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
    db: DbSession = _db_dep,
) -> list[str]:
    """Return the distinct action values present in the audit log."""
    from app.models import AuditLog

    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in rows]


@router.get("/audit-logs/users")
@require_login
async def list_distinct_users(
    request: Request,
    db: DbSession = _db_dep,
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
