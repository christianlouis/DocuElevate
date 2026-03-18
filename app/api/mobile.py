"""Mobile app API endpoints.

Provides endpoints specifically designed for the DocuElevate native mobile
app (iOS / Android via React Native / Expo):

* ``POST /mobile/generate-token`` – exchange an active session for a
  long-lived API token that the mobile app stores securely.  The token is
  auto-named "Mobile App – <device_name>" and is identical to regular API
  tokens (Bearer auth works everywhere).

* ``POST /mobile/register-device`` – register a push-notification device
  token (Expo push token) so the user receives push notifications when
  documents finish processing.

* ``GET /mobile/devices`` – list registered devices for the current user.

* ``DELETE /mobile/devices/{device_id}`` – deactivate a device.

* ``GET /mobile/whoami`` – lightweight profile endpoint for the mobile app
  to verify authentication state.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.api_tokens import generate_api_token, hash_token
from app.auth import require_login
from app.database import get_db
from app.models import ApiToken, MobileDevice
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mobile", tags=["mobile"])

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
# Request / Response schemas
# ---------------------------------------------------------------------------


class GenerateTokenRequest(BaseModel):
    """Request body for auto-generating a mobile app token."""

    device_name: str = Field(
        default="Mobile App",
        min_length=1,
        max_length=120,
        description="Human-readable device name used to label the token.",
    )


class GenerateTokenResponse(BaseModel):
    """Response containing the one-time-visible API token."""

    token: str
    token_id: int
    name: str
    created_at: datetime


class RegisterDeviceRequest(BaseModel):
    """Request body for registering a push-notification device token."""

    push_token: str = Field(
        min_length=1,
        max_length=512,
        description="Expo push token (ExponentPushToken[…]) obtained from the mobile app.",
    )
    device_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional human-readable device name (e.g. 'John's iPhone').",
    )
    platform: str = Field(
        default="ios",
        description="Device platform: 'ios', 'android', or 'web'.",
    )


class DeviceResponse(BaseModel):
    """Serialised MobileDevice record."""

    id: int
    device_name: str | None
    platform: str
    push_token_preview: str
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None


class WhoAmIResponse(BaseModel):
    """Lightweight profile response for the mobile app."""

    owner_id: str
    display_name: str | None
    email: str | None
    avatar_url: str | None
    is_admin: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _device_to_response(device: MobileDevice) -> dict[str, Any]:
    """Convert a MobileDevice ORM object to a serialisable dict."""
    # Show only first 20 chars of the push token for security.
    token_preview = device.push_token[:20] + "…" if len(device.push_token) > 20 else device.push_token
    return {
        "id": device.id,
        "device_name": device.device_name,
        "platform": device.platform,
        "push_token_preview": token_preview,
        "is_active": device.is_active,
        "created_at": device.created_at,
        "last_seen_at": device.last_seen_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate-token", status_code=status.HTTP_201_CREATED, response_model=GenerateTokenResponse)
@require_login
async def generate_mobile_token(
    request: Request,
    body: GenerateTokenRequest,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Generate a long-lived API token for the mobile app.

    The mobile app calls this endpoint immediately after SSO login to obtain
    a Bearer token it can store in the secure keychain.  The returned token
    is functionally identical to manually-created API tokens and works with
    every authenticated endpoint.

    The token is shown **exactly once** in the response; subsequent requests
    show only the prefix for identification.
    """
    token_name = f"Mobile App – {body.device_name}"
    plaintext = generate_api_token()
    token_hash_value = hash_token(plaintext)
    prefix = plaintext[:12]

    db_token = ApiToken(
        owner_id=owner_id,
        name=token_name,
        token_hash=token_hash_value,
        token_prefix=prefix,
    )
    try:
        db.add(db_token)
        db.commit()
        db.refresh(db_token)
    except Exception:
        db.rollback()
        logger.exception("Failed to create mobile API token for owner_id=%s", owner_id)
        raise

    logger.info("Mobile API token created: id=%s owner=%s device=%r", db_token.id, owner_id, body.device_name)

    return {
        "token": plaintext,
        "token_id": db_token.id,
        "name": token_name,
        "created_at": db_token.created_at,
    }


@router.post("/register-device", status_code=status.HTTP_201_CREATED, response_model=DeviceResponse)
@require_login
async def register_device(
    request: Request,
    body: RegisterDeviceRequest,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Register or refresh a push-notification device token.

    If the same ``push_token`` is already registered for this user the
    record is reactivated and ``last_seen_at`` is updated rather than
    creating a duplicate.
    """
    platform = body.platform.lower()
    if platform not in {"ios", "android", "web"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="platform must be one of: ios, android, web",
        )

    now = datetime.now(timezone.utc)

    # Upsert: reuse existing record if the token is already known.
    existing = (
        db.query(MobileDevice)
        .filter(MobileDevice.owner_id == owner_id, MobileDevice.push_token == body.push_token)
        .first()
    )
    if existing:
        existing.is_active = True
        existing.last_seen_at = now
        if body.device_name:
            existing.device_name = body.device_name
        try:
            db.commit()
            db.refresh(existing)
        except Exception:
            db.rollback()
            raise
        logger.info("Mobile device refreshed: id=%s owner=%s", existing.id, owner_id)
        return _device_to_response(existing)

    device = MobileDevice(
        owner_id=owner_id,
        device_name=body.device_name,
        platform=platform,
        push_token=body.push_token,
        is_active=True,
        last_seen_at=now,
    )
    try:
        db.add(device)
        db.commit()
        db.refresh(device)
    except Exception:
        db.rollback()
        logger.exception("Failed to register mobile device for owner_id=%s", owner_id)
        raise

    logger.info("Mobile device registered: id=%s owner=%s platform=%s", device.id, owner_id, platform)
    return _device_to_response(device)


@router.get("/devices", response_model=list[DeviceResponse])
@require_login
async def list_devices(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> list[dict[str, Any]]:
    """List all registered push-notification devices for the current user."""
    devices = (
        db.query(MobileDevice).filter(MobileDevice.owner_id == owner_id).order_by(MobileDevice.created_at.desc()).all()
    )
    return [_device_to_response(d) for d in devices]


@router.delete("/devices/{device_id}", status_code=status.HTTP_200_OK)
@require_login
async def deactivate_device(
    request: Request,
    device_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Deactivate or permanently delete a push-notification device registration.

    * **Active device** – soft-deactivated: the record is kept for audit
      purposes but will no longer receive push notifications.
    * **Already-inactive device** – hard-deleted: the record is permanently
      removed from the database.
    """
    device = db.get(MobileDevice, device_id)
    if not device or device.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if device.is_active:
        device.is_active = False
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        logger.info("Mobile device deactivated: id=%s owner=%s", device_id, owner_id)
        return {"detail": "Device deactivated"}

    # Hard-delete an already-inactive device.
    try:
        db.delete(device)
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info("Mobile device permanently deleted: id=%s owner=%s", device_id, owner_id)
    return {"detail": "Device deleted"}


@router.get("/whoami", response_model=WhoAmIResponse)
@require_login
async def whoami(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Return basic profile information for the authenticated user.

    The mobile app calls this after token exchange to populate the user
    profile screen and verify that the stored token is still valid.
    """
    from app.auth import get_gravatar_url
    from app.models import LocalUser, UserProfile

    profile = db.query(UserProfile).filter(UserProfile.user_id == owner_id).first()
    local_user = db.query(LocalUser).filter(LocalUser.email == owner_id).first()

    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    is_admin = False

    if profile:
        display_name = profile.display_name

    if local_user:
        email = local_user.email
        is_admin = bool(local_user.is_admin)
        if not display_name and local_user.display_name:
            display_name = local_user.display_name
    elif "@" in owner_id:
        # SSO users commonly have their email as owner_id
        email = owner_id

    if email:
        avatar_url = get_gravatar_url(email)

    return {
        "owner_id": owner_id,
        "display_name": display_name,
        "email": email,
        "avatar_url": avatar_url,
        "is_admin": is_admin,
    }
