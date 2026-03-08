"""API endpoints for per-user notification targets, preferences, and in-app inbox.

Users can define notification targets (email via SMTP, webhook via HTTP POST)
and configure which document events trigger which targets.  In-app notifications
are always created and surfaced via the bell icon / inbox endpoints.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InAppNotification, UserNotificationPreference, UserNotificationTarget
from app.utils.user_notification import USER_EVENT_LABELS
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user-notifications", tags=["user-notifications"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth helper (mirrors api_tokens.py pattern)
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

VALID_CHANNEL_TYPES = {"email", "webhook"}
VALID_EVENT_TYPES = set(USER_EVENT_LABELS.keys())


class NotificationTargetCreate(BaseModel):
    """Schema for creating a new notification target."""

    channel_type: str = Field(..., pattern="^(email|webhook)$")
    name: str = Field(..., min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class NotificationTargetUpdate(BaseModel):
    """Schema for updating an existing notification target."""

    name: str | None = Field(None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class PreferenceItem(BaseModel):
    """A single preference toggle for one event+channel combination."""

    is_enabled: bool
    target_id: int | None = None


class PreferenceItemFull(BaseModel):
    """Full preference item including event and channel type (used in bulk update)."""

    event_type: str
    channel_type: str
    is_enabled: bool
    target_id: int | None = None


class PreferencesUpdate(BaseModel):
    """Bulk preferences update payload — a flat list of preference items."""

    preferences: list[PreferenceItemFull]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_email_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of an email config dict with the password masked."""
    masked = dict(config)
    if masked.get("smtp_password"):
        masked["smtp_password"] = "****"
    return masked


def _target_to_dict(target: UserNotificationTarget) -> dict[str, Any]:
    """Serialize a UserNotificationTarget to a response dict, masking secrets."""
    config: dict[str, Any] = {}
    if target.config:
        try:
            config = json.loads(target.config)
        except (json.JSONDecodeError, ValueError):
            config = {}

    if target.channel_type == "email":
        config = _mask_email_config(config)

    return {
        "id": target.id,
        "channel_type": target.channel_type,
        "name": target.name,
        "config": config,
        "is_active": target.is_active,
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }


# ---------------------------------------------------------------------------
# Inbox endpoints
# ---------------------------------------------------------------------------


@router.get("/inbox")
async def list_inbox(
    owner_id: CurrentOwner,
    db: DbSession,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List in-app notifications for the authenticated user, newest first."""
    notifications = (
        db.query(InAppNotification)
        .filter(InAppNotification.owner_id == owner_id)
        .order_by(InAppNotification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": n.id,
            "event_type": n.event_type,
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "file_id": n.file_id,
            "created_at": n.created_at,
        }
        for n in notifications
    ]


@router.get("/inbox/unread-count")
async def unread_count(
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, int]:
    """Return the number of unread in-app notifications."""
    count = (
        db.query(InAppNotification)
        .filter(InAppNotification.owner_id == owner_id, InAppNotification.is_read == False)  # noqa: E712
        .count()
    )
    return {"count": count}


@router.post("/inbox/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_read(
    notification_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Mark a single in-app notification as read."""
    notif = (
        db.query(InAppNotification)
        .filter(InAppNotification.id == notification_id, InAppNotification.owner_id == owner_id)
        .first()
    )
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    try:
        notif.is_read = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"detail": "Marked as read"}


@router.post("/inbox/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Mark all in-app notifications as read for the authenticated user."""
    try:
        db.query(InAppNotification).filter(
            InAppNotification.owner_id == owner_id,
            InAppNotification.is_read == False,  # noqa: E712
        ).update({"is_read": True})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"detail": "All notifications marked as read"}


# ---------------------------------------------------------------------------
# Notification target endpoints
# ---------------------------------------------------------------------------


@router.get("/targets")
async def list_targets(
    owner_id: CurrentOwner,
    db: DbSession,
) -> list[dict[str, Any]]:
    """List all notification targets for the authenticated user."""
    targets = (
        db.query(UserNotificationTarget)
        .filter(UserNotificationTarget.owner_id == owner_id)
        .order_by(UserNotificationTarget.created_at.desc())
        .all()
    )
    return [_target_to_dict(t) for t in targets]


@router.post("/targets", status_code=status.HTTP_201_CREATED)
async def create_target(
    body: NotificationTargetCreate,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Create a new notification target (email or webhook)."""
    target = UserNotificationTarget(
        owner_id=owner_id,
        channel_type=body.channel_type,
        name=body.name,
        config=json.dumps(body.config),
        is_active=body.is_active,
    )
    try:
        db.add(target)
        db.commit()
        db.refresh(target)
    except Exception:
        db.rollback()
        raise

    logger.info("Notification target created: id=%s owner=%s type=%s", target.id, owner_id, body.channel_type)
    return _target_to_dict(target)


@router.put("/targets/{target_id}", status_code=status.HTTP_200_OK)
async def update_target(
    target_id: int,
    body: NotificationTargetUpdate,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Update an existing notification target."""
    target = (
        db.query(UserNotificationTarget)
        .filter(UserNotificationTarget.id == target_id, UserNotificationTarget.owner_id == owner_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    try:
        if body.name is not None:
            target.name = body.name
        if body.config is not None:
            # Merge new config over existing, preserving masked password field if unchanged
            existing_config: dict[str, Any] = {}
            if target.config:
                try:
                    existing_config = json.loads(target.config)
                except (json.JSONDecodeError, ValueError):
                    existing_config = {}
            merged = dict(existing_config)
            for k, v in body.config.items():
                # Skip writing back a masked password placeholder
                if k == "smtp_password" and v == "****":
                    continue
                merged[k] = v
            target.config = json.dumps(merged)
        if body.is_active is not None:
            target.is_active = body.is_active
        db.commit()
        db.refresh(target)
    except Exception:
        db.rollback()
        raise

    logger.info("Notification target updated: id=%s owner=%s", target_id, owner_id)
    return _target_to_dict(target)


@router.delete("/targets/{target_id}", status_code=status.HTTP_200_OK)
async def delete_target(
    target_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Delete a notification target and its associated preferences."""
    target = (
        db.query(UserNotificationTarget)
        .filter(UserNotificationTarget.id == target_id, UserNotificationTarget.owner_id == owner_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    try:
        # Remove any preferences that reference this target
        db.query(UserNotificationPreference).filter(
            UserNotificationPreference.owner_id == owner_id,
            UserNotificationPreference.target_id == target_id,
        ).delete()
        db.delete(target)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Notification target deleted: id=%s owner=%s", target_id, owner_id)
    return {"detail": "Target deleted"}


@router.post("/targets/{target_id}/test", status_code=status.HTTP_200_OK)
async def test_target(
    target_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Send a test notification to the specified target."""
    target = (
        db.query(UserNotificationTarget)
        .filter(UserNotificationTarget.id == target_id, UserNotificationTarget.owner_id == owner_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    config: dict[str, Any] = {}
    if target.config:
        try:
            config = json.loads(target.config)
        except (json.JSONDecodeError, ValueError):
            config = {}

    title = "DocuElevate Test Notification"
    message = f"This is a test notification from DocuElevate for target '{target.name}'."

    if target.channel_type == "email":
        from app.utils.user_notification import _send_email_notification

        ok = _send_email_notification(config, title, message)
    elif target.channel_type == "webhook":
        from app.utils.user_notification import _send_webhook_notification

        ok = _send_webhook_notification(config, "test", title, message)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown channel type")

    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send test notification")

    return {"detail": "Test notification sent"}


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------


@router.get("/preferences")
async def get_preferences(
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Return all notification preferences for the authenticated user.

    Response structure:
        {
          "event_types": ["document.processed", "document.failed"],
          "event_labels": {"document.processed": "Document Processed", ...},
          "preferences": {
            "document.processed": {
              "in_app": {"is_enabled": true, "target_id": null},
              "email": {"is_enabled": false, "target_id": 1},
              ...
            }
          }
        }
    """
    prefs = db.query(UserNotificationPreference).filter(UserNotificationPreference.owner_id == owner_id).all()

    # Build nested dict: event_type -> channel_type -> {is_enabled, target_id}
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for pref in prefs:
        result.setdefault(pref.event_type, {})[pref.channel_type] = {
            "is_enabled": pref.is_enabled,
            "target_id": pref.target_id,
        }

    return {
        "event_types": list(USER_EVENT_LABELS.keys()),
        "event_labels": USER_EVENT_LABELS,
        "preferences": result,
    }


@router.put("/preferences", status_code=status.HTTP_200_OK)
async def update_preferences(
    body: PreferencesUpdate,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Bulk upsert notification preferences for the authenticated user.

    Validates that any referenced target_id belongs to the requesting user.
    """
    # Collect all target IDs referenced in the payload for ownership validation
    referenced_target_ids: set[int] = set()
    for item in body.preferences:
        if item.target_id is not None:
            referenced_target_ids.add(item.target_id)

    if referenced_target_ids:
        owned_ids = {
            row.id
            for row in db.query(UserNotificationTarget.id)
            .filter(
                UserNotificationTarget.owner_id == owner_id,
                UserNotificationTarget.id.in_(referenced_target_ids),
            )
            .all()
        }
        invalid = referenced_target_ids - owned_ids
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid or inaccessible target_id(s): {sorted(invalid)}",
            )

    try:
        for item in body.preferences:
            existing = (
                db.query(UserNotificationPreference)
                .filter(
                    UserNotificationPreference.owner_id == owner_id,
                    UserNotificationPreference.event_type == item.event_type,
                    UserNotificationPreference.channel_type == item.channel_type,
                    UserNotificationPreference.target_id == item.target_id,
                )
                .first()
            )
            if existing:
                existing.is_enabled = item.is_enabled
            else:
                db.add(
                    UserNotificationPreference(
                        owner_id=owner_id,
                        event_type=item.event_type,
                        channel_type=item.channel_type,
                        target_id=item.target_id,
                        is_enabled=item.is_enabled,
                    )
                )
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Notification preferences updated for owner=%s", owner_id)
    return {"detail": "Preferences updated"}
