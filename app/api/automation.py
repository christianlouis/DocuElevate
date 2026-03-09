"""API endpoints for Zapier / Make.com automation integration.

Provides a REST hooks subscription interface for outgoing triggers and
incoming action endpoints that external automation platforms can call.

Outgoing triggers:
    External platforms subscribe to DocuElevate events via
    ``POST /api/automation/hooks/subscribe``.  When a subscribed event
    fires, DocuElevate POSTs a flat Zapier-compatible JSON payload to the
    registered ``target_url``.

Incoming actions:
    ``POST /api/automation/actions/upload`` allows automation platforms to
    push documents into DocuElevate for processing.

Authentication:
    All endpoints require a valid API token via ``Authorization: Bearer``
    header.
"""

import json
import logging
import os
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AutomationHook
from app.utils.automation_hooks import SAMPLE_PAYLOADS
from app.utils.webhook import VALID_EVENTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automation", tags=["automation"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper – require a valid API token (Bearer)
# ---------------------------------------------------------------------------


def _require_api_user(request: Request) -> dict:
    """Ensure the caller is authenticated via session or API token.

    Raises:
        HTTPException: 401 if not authenticated, 403 if automation hooks are disabled.
    """
    if not settings.automation_hooks_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Automation hooks are disabled",
        )

    # Check for API-token user first (set by auth middleware)
    user = getattr(request.state, "api_token_user", None)
    if user:
        return user

    # Fall back to session user
    user = request.session.get("user")
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required (Bearer token or session)",
    )


AuthUser = Annotated[dict, Depends(_require_api_user)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class HookSubscribe(BaseModel):
    """Schema for subscribing to automation hook events."""

    target_url: str = Field(..., min_length=1, max_length=2048, description="URL to POST event payloads to")
    events: list[str] = Field(..., min_length=1, description="Event types to subscribe to")
    secret: str | None = Field(default=None, max_length=512, description="Optional HMAC-SHA256 signing secret")
    hook_type: str = Field(
        default="generic",
        max_length=50,
        description="Platform identifier (zapier, make, generic)",
    )
    description: str | None = Field(default=None, max_length=500, description="Optional human-readable label")


class HookResponse(BaseModel):
    """Schema returned when listing or creating hooks."""

    id: int
    target_url: str
    events: list[str]
    is_active: bool
    hook_type: str
    description: str | None
    has_secret: bool

    model_config = {"from_attributes": True}


class ActionUploadResponse(BaseModel):
    """Response after an automation action uploads a document."""

    status: str
    filename: str
    task_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_events(events: list[str]) -> None:
    """Raise 422 if any event name is not recognised."""
    invalid = set(events) - VALID_EVENTS
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid event(s): {', '.join(sorted(invalid))}. Valid: {', '.join(sorted(VALID_EVENTS))}",
        )


def _hook_to_response(hook: AutomationHook) -> dict[str, Any]:
    """Convert a DB model instance to a response dict."""
    try:
        events = json.loads(hook.events)
    except (json.JSONDecodeError, TypeError):
        events = []
    return {
        "id": hook.id,
        "target_url": hook.target_url,
        "events": events,
        "is_active": hook.is_active,
        "hook_type": hook.hook_type,
        "description": hook.description,
        "has_secret": hook.secret is not None and len(hook.secret) > 0,
    }


# ---------------------------------------------------------------------------
# Outgoing triggers – REST hooks subscription endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/hooks/subscribe",
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to automation events (REST hooks)",
)
def subscribe_hook(body: HookSubscribe, db: DbSession, user: AuthUser) -> dict[str, Any]:
    """Register a new automation hook subscription.

    Zapier and Make.com call this endpoint to subscribe to DocuElevate
    events.  When an event fires, a flat JSON payload is POSTed to
    ``target_url``.
    """
    _validate_events(body.events)

    hook = AutomationHook(
        target_url=body.target_url,
        secret=body.secret,
        events=json.dumps(sorted(body.events)),
        is_active=True,
        hook_type=body.hook_type or "generic",
        description=body.description,
    )
    try:
        db.add(hook)
        db.commit()
        db.refresh(hook)
    except Exception:
        db.rollback()
        raise

    logger.info("Automation hook %d created (type=%s) for events %s", hook.id, hook.hook_type, body.events)
    return _hook_to_response(hook)


@router.delete(
    "/hooks/{hook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsubscribe an automation hook",
)
def unsubscribe_hook(hook_id: int, db: DbSession, user: AuthUser) -> None:
    """Remove an automation hook subscription.

    Zapier calls this endpoint when a Zap is turned off or deleted.
    """
    hook = db.query(AutomationHook).filter(AutomationHook.id == hook_id).first()
    if not hook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hook not found")

    try:
        db.delete(hook)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Automation hook %d deleted", hook_id)


@router.get("/hooks", summary="List automation hook subscriptions")
def list_hooks(db: DbSession, user: AuthUser) -> list[dict[str, Any]]:
    """Return all active automation hook subscriptions."""
    hooks = db.query(AutomationHook).order_by(AutomationHook.id).all()
    return [_hook_to_response(h) for h in hooks]


# ---------------------------------------------------------------------------
# Outgoing triggers – sample data for Zapier field mapping
# ---------------------------------------------------------------------------


@router.get("/triggers/sample/{event}", summary="Get sample trigger data")
def get_trigger_sample(event: str, user: AuthUser) -> list[dict[str, Any]]:
    """Return sample payload data for the given event type.

    Zapier uses this during Zap setup to discover available fields and
    provide a mapping interface.  The response is wrapped in an array
    as Zapier expects.
    """
    if event not in VALID_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown event: {event}. Valid: {', '.join(sorted(VALID_EVENTS))}",
        )

    sample = SAMPLE_PAYLOADS.get(event, {"id": "evt_sample", "event": event, "timestamp": 0})
    return [sample]


# ---------------------------------------------------------------------------
# Outgoing triggers – list valid events
# ---------------------------------------------------------------------------


@router.get("/events", summary="List valid automation event types")
def list_events(user: AuthUser) -> list[str]:
    """Return the list of valid event types that automation hooks can subscribe to."""
    return sorted(VALID_EVENTS)


# ---------------------------------------------------------------------------
# Incoming actions – endpoints that Zapier / Make.com can call
# ---------------------------------------------------------------------------


@router.post("/actions/upload", summary="Upload a document (incoming action)")
def action_upload(
    request: Request,
    db: DbSession,
    user: AuthUser,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Accept a document upload from an automation platform.

    This endpoint allows Zapier or Make.com to push a document into
    DocuElevate for processing.  The file is saved to the work directory
    and a background processing task is queued.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    owner_id = user.get("preferred_username") or user.get("email") or user.get("id", "automation")
    workdir = settings.workdir or tempfile.gettempdir()
    upload_dir = os.path.join(workdir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    dest_path = os.path.join(upload_dir, file.filename)
    try:
        contents = file.file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
    except Exception as exc:
        logger.error("Failed to save uploaded file: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")

    # Queue background processing
    task_id = None
    try:
        from app.tasks.process_document import process_document

        result = process_document.delay(dest_path, owner_id)
        task_id = result.id
        logger.info("Automation upload queued: file=%s, task=%s, owner=%s", file.filename, task_id, owner_id)
    except Exception as exc:
        logger.warning("Could not queue processing task (Celery may be unavailable): %s", exc)

    return {
        "status": "accepted",
        "filename": file.filename,
        "task_id": task_id,
    }
