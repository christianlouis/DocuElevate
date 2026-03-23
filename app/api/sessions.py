"""API endpoints for managing user sessions.

Provides endpoints for listing active sessions, revoking individual sessions,
and the "log off everywhere" feature that invalidates all sessions and API
tokens across all devices.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.middleware.audit_log import get_client_ip
from app.utils.session_manager import (
    get_session_lifetime_days,
    list_user_sessions,
    revoke_all_sessions,
    revoke_session,
)
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """Serialised user session for the management UI."""

    id: int
    device_info: str | None
    ip_address: str | None
    created_at: datetime
    last_active_at: datetime
    expires_at: datetime
    is_current: bool = False


class SessionListResponse(BaseModel):
    """Response for listing active sessions."""

    sessions: list[SessionResponse]
    session_lifetime_days: int


class RevokeAllResponse(BaseModel):
    """Response after revoking all sessions."""

    revoked_count: int
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", response_model=SessionListResponse)
@require_login
async def list_sessions(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """List all active sessions for the current user."""
    sessions = list_user_sessions(db, owner_id)

    # Determine which session is the current one
    current_token = request.session.get("_session_token")

    session_list = []
    for s in sessions:
        session_list.append(
            {
                "id": s.id,
                "device_info": s.device_info,
                "ip_address": s.ip_address,
                "created_at": s.created_at,
                "last_active_at": s.last_active_at,
                "expires_at": s.expires_at,
                "is_current": s.session_token == current_token if current_token else False,
            }
        )

    return {
        "sessions": session_list,
        "session_lifetime_days": get_session_lifetime_days(),
    }


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
async def revoke_single_session(
    request: Request,
    session_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> None:
    """Revoke a specific session by ID."""
    success = revoke_session(db, session_id, owner_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        from app.utils.audit_service import record_event

        record_event(
            db,
            action="session_revoked",
            user=owner_id,
            resource_type="session",
            resource_id=str(session_id),
            ip_address=get_client_ip(request),
            severity="info",
        )
    except Exception:
        logger.debug("Failed to write session revocation audit event", exc_info=True)


@router.post("/revoke-all", response_model=RevokeAllResponse)
@require_login
async def revoke_all(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Revoke all sessions except the current one ("log off everywhere").

    Also revokes all active API tokens for the user, which invalidates
    mobile app sessions and any programmatic access.
    """
    # Find current session to preserve it
    current_token = request.session.get("_session_token")
    current_session_id = None
    if current_token:
        from app.models import UserSession

        current = db.query(UserSession).filter(UserSession.session_token == current_token).first()
        if current:
            current_session_id = current.id

    count = revoke_all_sessions(
        db,
        owner_id,
        except_session_id=current_session_id,
        revoke_api_tokens=True,
    )

    try:
        from app.utils.audit_service import record_event

        record_event(
            db,
            action="revoke_all_sessions",
            user=owner_id,
            resource_type="session",
            ip_address=get_client_ip(request),
            details={"revoked_count": count},
            severity="warning",
        )
    except Exception:
        logger.debug("Failed to write revoke-all audit event", exc_info=True)

    return {
        "revoked_count": count,
        "message": f"Successfully revoked {count} session(s) and all API tokens.",
    }
