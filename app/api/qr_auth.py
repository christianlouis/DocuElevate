"""QR code login API endpoints for mobile app authentication.

Provides a secure challenge-response flow for logging into the mobile app
by scanning a QR code displayed in the web interface:

1. **Web user** calls ``POST /qr-auth/challenge`` → receives a time-limited
   challenge token (encoded in the QR code).
2. **Web UI** polls ``GET /qr-auth/challenge/{id}/status`` to detect when
   the mobile app has claimed the challenge.
3. **Mobile app** scans the QR code and calls ``POST /qr-auth/claim`` with
   the challenge token + device name → receives an API token.

Security properties:
* Challenges expire after a configurable TTL (default 2 minutes).
* Single-use: once claimed, a challenge cannot be reused (replay-safe).
* Cryptographically random 64-byte tokens.
* IP addresses are logged for audit.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.middleware.audit_log import get_client_ip
from app.utils.session_manager import (
    claim_qr_challenge,
    create_qr_challenge,
    get_challenge_status,
)
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/qr-auth", tags=["qr-auth"])

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


class CreateChallengeResponse(BaseModel):
    """Response after creating a QR login challenge."""

    challenge_id: int
    challenge_token: str
    expires_at: datetime
    qr_payload: str = Field(description="The string to encode in the QR code.")


class ChallengeStatusResponse(BaseModel):
    """Response for polling the status of a QR challenge."""

    id: int
    status: str  # "pending", "claimed", "expired", "cancelled"
    device_name: str | None = None
    claimed_at: datetime | None = None
    expires_at: datetime


class ClaimChallengeRequest(BaseModel):
    """Request body for claiming a QR login challenge."""

    challenge_token: str = Field(min_length=1, max_length=256)
    device_name: str = Field(
        default="Mobile App",
        min_length=1,
        max_length=120,
        description="Human-readable device name.",
    )


class ClaimChallengeResponse(BaseModel):
    """Response after successfully claiming a QR challenge."""

    token: str
    token_id: int
    name: str
    owner_id: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/challenge", status_code=status.HTTP_201_CREATED, response_model=CreateChallengeResponse)
@require_login
async def create_challenge(
    request: Request,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Create a new QR login challenge.

    The returned ``qr_payload`` should be encoded into a QR code and
    displayed to the user.  The mobile app scans this QR code and
    calls the ``/claim`` endpoint.
    """
    ip = get_client_ip(request)
    challenge = create_qr_challenge(db, owner_id, ip_address=ip)

    # The QR payload is a JSON-like string with enough info for the mobile
    # app to know the server URL and challenge token.
    base_url = str(request.base_url).rstrip("/")
    qr_payload = f"docuelevate://qr-login?token={challenge.challenge_token}&server={base_url}"

    return {
        "challenge_id": challenge.id,
        "challenge_token": challenge.challenge_token,
        "expires_at": challenge.expires_at,
        "qr_payload": qr_payload,
    }


@router.get("/challenge/{challenge_id}/status", response_model=ChallengeStatusResponse)
@require_login
async def poll_challenge_status(
    request: Request,
    challenge_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Poll the status of a QR login challenge.

    The web UI calls this endpoint every few seconds to check if the
    mobile app has scanned the QR code and claimed the challenge.
    """
    result = get_challenge_status(db, challenge_id, owner_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")
    return result


@router.post("/claim", response_model=ClaimChallengeResponse)
async def claim_challenge(
    request: Request,
    body: ClaimChallengeRequest,
    db: DbSession,
) -> dict[str, Any]:
    """Claim a QR login challenge and receive an API token.

    This endpoint is called by the mobile app after scanning a QR code.
    It does **not** require authentication — the challenge token itself
    serves as proof that the user authorized this login from their web
    session.
    """
    ip = get_client_ip(request)
    result = claim_qr_challenge(db, body.challenge_token, device_name=body.device_name, ip_address=ip)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already claimed challenge.",
        )

    try:
        from app.utils.audit_service import record_event

        record_event(
            db,
            action="qr_login_claimed",
            user=result["owner_id"],
            resource_type="session",
            ip_address=ip,
            details={"device_name": body.device_name, "token_id": result["token_id"]},
            severity="info",
        )
    except Exception:
        logger.debug("Failed to write QR login audit event", exc_info=True)

    return result
