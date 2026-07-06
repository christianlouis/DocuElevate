"""API endpoints for managing webhook configurations.

Provides CRUD operations for webhook configs that notify external systems
when document events occur (``document.uploaded``, ``document.processed``,
``document.failed``).
"""

import json
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_id, require_login
from app.database import get_db
from app.models import FileRecord, Pipeline, WebhookConfig, WebhookDeliveryAttempt
from app.tasks.process_document import process_document
from app.tasks.webhook_tasks import deliver_webhook_task
from app.utils.user_scope import get_current_owner_id
from app.utils.webhook import VALID_EVENTS, WEBHOOK_PAYLOAD_VERSION

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


class InboundPipelineTrigger(BaseModel):
    """Schema for authenticated inbound workflow triggers."""

    file_id: int = Field(..., ge=1, description="Existing document ID to process with the selected pipeline")
    force_cloud_ocr: bool = Field(default=False, description="Force OCR during the queued processing run")
    event_id: str | None = Field(default=None, max_length=255, description="Optional external event identifier")


class WebhookReplayResponse(BaseModel):
    """Response returned after queueing a webhook delivery replay."""

    status: str
    delivery_id: int
    replay_of: int
    task_id: str | None


_WEBHOOK_EVENT_SAMPLE_DATA: dict[str, dict[str, Any]] = {
    "document.uploaded": {"file_id": 42, "filename": "invoice.pdf", "owner_id": "user@example.com"},
    "document.processed": {"file_id": 42, "filename": "invoice.pdf", "status": "completed"},
    "document.failed": {"file_id": 42, "filename": "invoice.pdf", "error": "OCR provider unavailable"},
    "user.signup": {"user_id": "user@example.com", "email": "user@example.com"},
    "user.plan_changed": {"user_id": "user@example.com", "old_tier": "free", "new_tier": "starter"},
    "user.payment_issue": {"user_id": "user@example.com", "issue": "Card declined"},
}


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


def _to_delivery_response(attempt: WebhookDeliveryAttempt) -> dict[str, Any]:
    """Convert a persisted delivery attempt to an admin response."""
    return {
        "id": attempt.id,
        "webhook_config_id": attempt.webhook_config_id,
        "task_id": attempt.task_id,
        "url": attempt.url,
        "event": attempt.event,
        "status": attempt.status,
        "attempt_number": attempt.attempt_number,
        "response_status": attempt.response_status,
        "error": attempt.error,
        "created_at": attempt.created_at,
        "delivered_at": attempt.delivered_at,
        "updated_at": attempt.updated_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/inbound/pipelines/{pipeline_id}/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a processing pipeline from an inbound webhook",
)
@require_login
def trigger_pipeline_from_webhook(
    pipeline_id: int,
    request: Request,
    body: InboundPipelineTrigger,
    db: DbSession,
) -> dict[str, Any]:
    """Assign a pipeline to an existing file and enqueue processing.

    This endpoint is intended for external systems authenticated with a
    DocuElevate API token.  It validates both the target file and pipeline
    against the caller before modifying the file or queueing work.
    """
    user = get_current_user(request)
    user_id = get_current_user_id(request)
    owner_id = get_current_owner_id(request)
    is_admin = bool(user and user.get("is_admin"))

    file_record = db.query(FileRecord).filter(FileRecord.id == body.file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if not is_admin and file_record.owner_id is not None and file_record.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline or (not is_admin and pipeline.owner_id is not None and pipeline.owner_id != user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    if not file_record.local_filename or not os.path.exists(file_record.local_filename):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local file not found on disk. Cannot trigger pipeline.",
        )

    file_record.pipeline_id = pipeline.id
    file_record.pipeline_routing_rule_id = None
    file_record.pipeline_assignment_source = "inbound_webhook"
    reason = "Inbound webhook trigger assigned processing profile and queued workflow"
    if body.event_id:
        reason = f"{reason} for external event {body.event_id}"
    file_record.pipeline_assignment_reason = reason

    try:
        db.commit()
        db.refresh(file_record)
        task = process_document.delay(
            file_record.local_filename,
            original_filename=file_record.original_filename,
            file_id=file_record.id,
            force_cloud_ocr=body.force_cloud_ocr,
            owner_id=file_record.owner_id,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to trigger inbound pipeline id=%s for file id=%s", pipeline_id, body.file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to trigger pipeline"
        ) from exc

    logger.info(
        "Inbound webhook queued pipeline_id=%s for file_id=%s task_id=%s",
        pipeline_id,
        file_record.id,
        task.id,
    )
    return {
        "status": "queued",
        "file_id": file_record.id,
        "pipeline_id": file_record.pipeline_id,
        "task_id": task.id,
    }


@router.get("/", summary="List all webhook configurations")
def list_webhooks(db: DbSession, _admin: AdminUser) -> list[dict[str, Any]]:
    """Return all webhook configurations. Secrets are never included."""
    configs = db.query(WebhookConfig).order_by(WebhookConfig.id).all()
    return [_to_response(c) for c in configs]


@router.get("/delivery-attempts/", summary="List webhook delivery attempts")
def list_delivery_attempts(
    db: DbSession,
    _admin: AdminUser,
    status_filter: str | None = Query(default=None, alias="status"),
    event: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Return recent outbound webhook delivery attempts."""
    query = db.query(WebhookDeliveryAttempt)
    if status_filter:
        query = query.filter(WebhookDeliveryAttempt.status == status_filter)
    if event:
        query = query.filter(WebhookDeliveryAttempt.event == event)
    attempts = (
        query.order_by(WebhookDeliveryAttempt.created_at.desc(), WebhookDeliveryAttempt.id.desc()).limit(limit).all()
    )
    return [_to_delivery_response(attempt) for attempt in attempts]


@router.get("/event-catalog/", summary="List webhook event catalog")
def event_catalog(_admin: AdminUser) -> dict[str, Any]:
    """Return supported webhook events with example payload envelopes."""
    events = []
    for event in sorted(VALID_EVENTS):
        sample_data = _WEBHOOK_EVENT_SAMPLE_DATA.get(event, {})
        events.append(
            {
                "event": event,
                "payload_version": WEBHOOK_PAYLOAD_VERSION,
                "sample_payload": {
                    "version": WEBHOOK_PAYLOAD_VERSION,
                    "event": event,
                    "timestamp": 1772841600.0,
                    "data": sample_data,
                },
            }
        )
    return {"payload_version": WEBHOOK_PAYLOAD_VERSION, "events": events}


@router.post("/delivery-attempts/{attempt_id}/replay", summary="Replay a webhook delivery attempt")
def replay_delivery_attempt(attempt_id: int, db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Queue a replay for a persisted webhook delivery attempt."""
    attempt = db.query(WebhookDeliveryAttempt).filter(WebhookDeliveryAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook delivery attempt not found")

    try:
        payload = json.loads(attempt.payload)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stored webhook payload cannot be replayed")

    webhook_config = None
    if attempt.webhook_config_id is not None:
        webhook_config = db.query(WebhookConfig).filter(WebhookConfig.id == attempt.webhook_config_id).first()

    replay_url = webhook_config.url if webhook_config else attempt.url
    replay_secret = webhook_config.secret if webhook_config else None
    replay = WebhookDeliveryAttempt(
        webhook_config_id=attempt.webhook_config_id,
        url=replay_url,
        event=attempt.event,
        payload=json.dumps(payload, default=str, sort_keys=True),
        status="queued",
        attempt_number=1,
    )
    db.add(replay)
    db.commit()
    db.refresh(replay)

    task = deliver_webhook_task.delay(replay_url, payload, replay_secret, attempt.webhook_config_id, replay.id)
    replay.task_id = getattr(task, "id", None)
    db.commit()
    db.refresh(replay)

    logger.info("Webhook delivery attempt %d replay queued as delivery %d", attempt.id, replay.id)
    return WebhookReplayResponse(
        status="queued",
        delivery_id=replay.id,
        replay_of=attempt.id,
        task_id=replay.task_id,
    ).model_dump()


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
