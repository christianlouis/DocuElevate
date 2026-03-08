"""API endpoints for managing personal API tokens.

Provides CRUD operations so users can create, list, and revoke tokens
that grant programmatic access to the DocuElevate API (e.g. webhook
uploads, scripted integrations).

Tokens use ``secrets.token_urlsafe`` from the Python standard library
(no extra dependencies) and are prefixed with ``de_`` for easy
identification.  Only a SHA-256 hash is persisted; the plaintext is
returned exactly once at creation time.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiToken
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-tokens", tags=["api-tokens"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Prefix prepended to every generated token for easy identification.
TOKEN_PREFIX = "de_"
#: Number of random bytes for the token body (32 → 43 URL-safe chars).
TOKEN_BYTES = 32
#: PBKDF2 iteration count for hashing API tokens.
TOKEN_HASH_ITERATIONS = 100_000
#: PBKDF2 salt for API token hashing (not secret, but fixed for determinism).
TOKEN_HASH_SALT = b"api-token-v1"


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
# Helpers
# ---------------------------------------------------------------------------


def generate_api_token() -> str:
    """Generate a new API token with the ``de_`` prefix.

    Returns:
        A URL-safe random token string, e.g. ``de_Ab3xY…``.
    """
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Return a PBKDF2-HMAC-SHA256 hex digest of *token*.

    Args:
        token: The plaintext API token.

    Returns:
        64-character lowercase hex string.
    """
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        token.encode("utf-8"),
        TOKEN_HASH_SALT,
        TOKEN_HASH_ITERATIONS,
    )
    return dk.hex()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TokenCreate(BaseModel):
    """Schema for creating a new API token."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label for the token")


class TokenResponse(BaseModel):
    """Schema returned when listing tokens (plaintext is never included)."""

    id: int
    name: str
    token_prefix: str
    is_active: bool
    last_used_at: datetime | None
    last_used_ip: str | None
    created_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class TokenCreatedResponse(TokenResponse):
    """Schema returned once at creation time — includes the full plaintext token."""

    token: str = Field(..., description="The full API token. Store it securely — it will not be shown again.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=TokenCreatedResponse)
async def create_token(
    body: TokenCreate,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, Any]:
    """Create a new personal API token.

    The full token is returned **only once** in the response.  Subsequent
    ``GET`` requests will only show the prefix for identification.
    """
    plaintext = generate_api_token()
    token_hash_value = hash_token(plaintext)
    prefix = plaintext[:12]  # "de_" prefix + 9 random chars = 12 chars total

    db_token = ApiToken(
        owner_id=owner_id,
        name=body.name,
        token_hash=token_hash_value,
        token_prefix=prefix,
    )
    try:
        db.add(db_token)
        db.commit()
        db.refresh(db_token)
    except Exception:
        db.rollback()
        raise

    logger.info("API token created: id=%s owner=%s name=%r", db_token.id, owner_id, body.name)

    return {
        "id": db_token.id,
        "name": db_token.name,
        "token_prefix": db_token.token_prefix,
        "is_active": db_token.is_active,
        "last_used_at": db_token.last_used_at,
        "last_used_ip": db_token.last_used_ip,
        "created_at": db_token.created_at,
        "revoked_at": db_token.revoked_at,
        "token": plaintext,
    }


@router.get("/", response_model=list[TokenResponse])
async def list_tokens(
    owner_id: CurrentOwner,
    db: DbSession,
) -> list[dict[str, Any]]:
    """List all API tokens for the authenticated user."""
    tokens = db.query(ApiToken).filter(ApiToken.owner_id == owner_id).order_by(ApiToken.created_at.desc()).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "token_prefix": t.token_prefix,
            "is_active": t.is_active,
            "last_used_at": t.last_used_at,
            "last_used_ip": t.last_used_ip,
            "created_at": t.created_at,
            "revoked_at": t.revoked_at,
        }
        for t in tokens
    ]


@router.delete("/{token_id}", status_code=status.HTTP_200_OK)
async def revoke_token(
    token_id: int,
    owner_id: CurrentOwner,
    db: DbSession,
) -> dict[str, str]:
    """Revoke (soft-delete) an API token.

    The token row is kept for audit purposes but marked inactive with a
    ``revoked_at`` timestamp.
    """
    db_token = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.owner_id == owner_id).first()
    if not db_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if not db_token.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token is already revoked")

    try:
        db_token.is_active = False
        db_token.revoked_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("API token revoked: id=%s owner=%s", token_id, owner_id)
    return {"detail": "Token revoked"}
