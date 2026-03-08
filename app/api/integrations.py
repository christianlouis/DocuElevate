"""API endpoints for managing per-user integrations (sources and destinations).

Provides CRUD operations for :class:`~app.models.UserIntegration` records.
Each record represents one ingestion source (e.g. IMAP, Watch Folder) or
storage destination (e.g. S3, Dropbox, Google Drive) configured by a user.

Sensitive credentials are encrypted at rest using Fernet symmetric encryption
(keyed from ``SESSION_SECRET``) via :mod:`app.utils.encryption`.  Credential
values are **never** returned in API responses.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntegrationDirection, IntegrationType, UserIntegration
from app.utils.encryption import decrypt_value, encrypt_value
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

_VALID_DIRECTIONS = IntegrationDirection.ALL
_VALID_TYPES = IntegrationType.ALL


class IntegrationCreate(BaseModel):
    """Schema for creating a new integration."""

    direction: str = Field(..., description="'SOURCE' or 'DESTINATION'")
    integration_type: str = Field(..., description="Integration type (e.g. 'IMAP', 'S3', 'DROPBOX')")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    config: dict[str, Any] | None = Field(default=None, description="Non-sensitive configuration (JSON object)")
    credentials: dict[str, Any] | None = Field(
        default=None, description="Sensitive credentials (JSON object, encrypted at rest)"
    )
    is_active: bool = Field(default=True, description="Whether the integration is active")


class IntegrationUpdate(BaseModel):
    """Schema for updating an existing integration (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_direction(direction: str) -> None:
    """Raise 400 if *direction* is not a known value."""
    if direction not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid direction '{direction}'. Must be one of: {sorted(_VALID_DIRECTIONS)}",
        )


def _validate_integration_type(integration_type: str) -> None:
    """Raise 400 if *integration_type* is not a known value."""
    if integration_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid integration_type '{integration_type}'. Must be one of: {sorted(_VALID_TYPES)}",
        )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_response(integration: UserIntegration) -> dict[str, Any]:
    """Serialise a :class:`UserIntegration` row to a response dict.

    Credentials are **never** included; only a boolean flag indicating
    whether credentials have been configured is returned.
    """
    config_data: dict[str, Any] | None = None
    if integration.config:
        try:
            config_data = json.loads(integration.config)
        except (json.JSONDecodeError, TypeError):
            config_data = None

    return {
        "id": integration.id,
        "owner_id": integration.owner_id,
        "direction": integration.direction,
        "integration_type": integration.integration_type,
        "name": integration.name,
        "config": config_data,
        "has_credentials": bool(integration.credentials),
        "is_active": integration.is_active,
        "last_used_at": integration.last_used_at.isoformat() if integration.last_used_at else None,
        "last_error": integration.last_error,
        "created_at": integration.created_at.isoformat() if integration.created_at else None,
        "updated_at": integration.updated_at.isoformat() if integration.updated_at else None,
    }


def _encode_credentials(credentials: dict[str, Any] | None) -> str | None:
    """Serialise *credentials* dict to an encrypted JSON string for storage."""
    if not credentials:
        return None
    plaintext = json.dumps(credentials)
    return encrypt_value(plaintext)


def _decode_credentials(stored: str | None) -> dict[str, Any] | None:
    """Decrypt and deserialise stored credentials back to a dict.

    Returns ``None`` when *stored* is empty or cannot be decoded.
    """
    if not stored:
        return None
    plaintext = decrypt_value(stored)
    if not plaintext:
        return None
    try:
        return json.loads(plaintext)
    except (json.JSONDecodeError, TypeError):
        logger.error("Failed to decode credentials JSON after decryption")
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List integrations for the current user")
def list_integrations(
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
    direction: str | None = None,
    integration_type: str | None = None,
) -> list[dict[str, Any]]:
    """Return all integrations belonging to the authenticated user.

    Optional query-string filters:

    - ``direction`` — ``SOURCE`` or ``DESTINATION``
    - ``integration_type`` — e.g. ``IMAP``, ``S3``, ``DROPBOX``
    """
    query = db.query(UserIntegration).filter(UserIntegration.owner_id == owner_id)

    if direction is not None:
        _validate_direction(direction)
        query = query.filter(UserIntegration.direction == direction)

    if integration_type is not None:
        _validate_integration_type(integration_type)
        query = query.filter(UserIntegration.integration_type == integration_type)

    integrations = query.order_by(UserIntegration.id).all()
    return [_to_response(i) for i in integrations]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new integration")
def create_integration(
    request: Request,
    body: IntegrationCreate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Create a new source or destination integration for the current user.

    ``credentials`` are encrypted at rest using Fernet symmetric encryption
    before being persisted and are **never** returned in API responses.
    """
    _validate_direction(body.direction)
    _validate_integration_type(body.integration_type)

    integration = UserIntegration(
        owner_id=owner_id,
        direction=body.direction,
        integration_type=body.integration_type,
        name=body.name,
        config=json.dumps(body.config) if body.config is not None else None,
        credentials=_encode_credentials(body.credentials),
        is_active=body.is_active,
    )

    try:
        db.add(integration)
        db.commit()
        db.refresh(integration)
    except Exception:
        db.rollback()
        raise

    logger.info(
        "User %s created %s integration %d (%s)",
        owner_id,
        body.direction,
        integration.id,
        body.integration_type,
    )
    return _to_response(integration)


@router.get("/{integration_id}", summary="Get a single integration")
def get_integration(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Return a single integration by ID (must belong to the current user)."""
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return _to_response(integration)


@router.put("/{integration_id}", summary="Update an integration")
def update_integration(
    integration_id: int,
    request: Request,
    body: IntegrationUpdate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Update an existing integration.  Only provided fields are changed.

    When ``credentials`` is supplied the stored value is replaced in full
    with the freshly encrypted version of the new credentials dict.
    """
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    if body.name is not None:
        integration.name = body.name
    if body.config is not None:
        integration.config = json.dumps(body.config)
    if body.credentials is not None:
        integration.credentials = _encode_credentials(body.credentials)
    if body.is_active is not None:
        integration.is_active = body.is_active

    # Reset last_error so the next operation gives a fresh result
    integration.last_error = None

    try:
        db.commit()
        db.refresh(integration)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s updated integration %d", owner_id, integration_id)
    return _to_response(integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an integration")
def delete_integration(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> None:
    """Delete an integration permanently."""
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    try:
        db.delete(integration)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("User %s deleted integration %d", owner_id, integration_id)


@router.get("/{integration_id}/credentials", summary="Retrieve decrypted credentials for an integration")
def get_integration_credentials(
    integration_id: int,
    request: Request,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Return the decrypted credentials dict for a saved integration.

    This endpoint is intended for internal use by background tasks that need
    to authenticate with a third-party service.  Treat the response as
    sensitive — it contains plaintext secrets.
    """
    integration = (
        db.query(UserIntegration)
        .filter(UserIntegration.id == integration_id, UserIntegration.owner_id == owner_id)
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    credentials = _decode_credentials(integration.credentials)
    return {"credentials": credentials or {}}
