"""API endpoints for managing webhook configurations.

Provides CRUD operations for webhook configs that notify external systems
when document events occur (``document.uploaded``, ``document.processed``,
``document.failed``).
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WebhookConfig
from app.utils.webhook import VALID_EVENTS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper (reuse the pattern from settings API)
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin. Raises 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class WebhookCreate(BaseModel):
    """Schema for creating a new webhook configuration."""

    url: str = Field(..., min_length=1, max_length=2048, description="Target URL for webhook delivery")
    secret: str | None = Field(default=None, max_length=512, description="Shared secret for HMAC-SHA256 signatures")
    events: list[str] = Field(..., min_length=1, description="List of events to subscribe to")
    is_active: bool = Field(default=True, description="Whether the webhook is active")
    description: str | None = Field(default=None, max_length=500, description="Optional human-readable description")


class WebhookUpdate(BaseModel):
    """Schema for updating an existing webhook configuration."""

    url: str | None = Field(default=None, min_length=1, max_length=2048)
    secret: str | None = Field(default=None, max_length=512)
    events: list[str] | None = Field(default=None, min_length=1)
    is_active: bool | None = None
    description: str | None = Field(default=None, max_length=500)


class WebhookResponse(BaseModel):
    """Schema returned to clients (secret is never exposed)."""

    id: int
    url: str
    events: list[str]
    is_active: bool
    description: str | None
    has_secret: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_events(events: list[str]) -> None:
    """Raise 422 if any event name is not recognised."""
    invalid = set(events) - VALID_EVENTS
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid event(s): {', '.join(sorted(invalid))}. Valid events: {', '.join(sorted(VALID_EVENTS))}",
        )


def _to_response(cfg: WebhookConfig) -> dict[str, Any]:
    """Convert a DB model instance to a response dict."""
    try:
        events = json.loads(cfg.events)
    except (json.JSONDecodeError, TypeError):
        events = []
    return {
        "id": cfg.id,
        "url": cfg.url,
        "events": events,
        "is_active": cfg.is_active,
        "description": cfg.description,
        "has_secret": cfg.secret is not None and len(cfg.secret) > 0,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List all webhook configurations")
def list_webhooks(db: DbSession, _admin: AdminUser) -> list[dict[str, Any]]:
    """Return all webhook configurations. Secrets are never included."""
    configs = db.query(WebhookConfig).order_by(WebhookConfig.id).all()
    return [_to_response(c) for c in configs]


@router.get("/{webhook_id}", summary="Get a single webhook configuration")
def get_webhook(webhook_id: int, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Return a single webhook configuration by ID."""
    cfg = db.query(WebhookConfig).filter(WebhookConfig.id == webhook_id).first()
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return _to_response(cfg)


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a webhook configuration")
def create_webhook(body: WebhookCreate, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Create a new webhook configuration."""
    _validate_events(body.events)

    cfg = WebhookConfig(
        url=body.url,
        secret=body.secret,
        events=json.dumps(sorted(body.events)),
        is_active=body.is_active,
        description=body.description,
    )
    try:
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    except Exception:
        db.rollback()
        raise

    logger.info("Webhook %d created for events %s", cfg.id, body.events)
    return _to_response(cfg)


@router.put("/{webhook_id}", summary="Update a webhook configuration")
def update_webhook(webhook_id: int, body: WebhookUpdate, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Update an existing webhook configuration. Only supplied fields are changed."""
    cfg = db.query(WebhookConfig).filter(WebhookConfig.id == webhook_id).first()
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    if body.url is not None:
        cfg.url = body.url
    if body.secret is not None:
        cfg.secret = body.secret
    if body.events is not None:
        _validate_events(body.events)
        cfg.events = json.dumps(sorted(body.events))
    if body.is_active is not None:
        cfg.is_active = body.is_active
    if body.description is not None:
        cfg.description = body.description

    try:
        db.commit()
        db.refresh(cfg)
    except Exception:
        db.rollback()
        raise

    logger.info("Webhook %d updated", cfg.id)
    return _to_response(cfg)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a webhook configuration")
def delete_webhook(webhook_id: int, db: DbSession, _admin: AdminUser) -> None:
    """Delete a webhook configuration."""
    cfg = db.query(WebhookConfig).filter(WebhookConfig.id == webhook_id).first()
    if not cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")

    try:
        db.delete(cfg)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Webhook %d deleted", cfg.id)


@router.get("/events/", summary="List valid webhook event types")
def list_events(_admin: AdminUser) -> list[str]:
    """Return the list of valid event types that can be subscribed to."""
    return sorted(VALID_EVENTS)
