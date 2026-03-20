"""
System reset API endpoints for DocuElevate.

Provides admin-only REST endpoints for:
- Full system reset (wipe all user data)
- Reset with re-import (move originals → reimport folder, wipe, re-ingest)

Both operations require the ``ENABLE_FACTORY_RESET=True`` feature flag and
admin privileges.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/system-reset", tags=["system-reset"])


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin.  Raises 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


def _require_feature_enabled() -> None:
    """Raise 404 when the factory-reset feature flag is off."""
    if not settings.enable_factory_reset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System reset is not enabled. Set ENABLE_FACTORY_RESET=True to activate.",
        )


class ResetRequest(BaseModel):
    """Body for system reset endpoints.  Requires explicit confirmation."""

    confirmation: str


@router.post("/full")
async def full_reset(
    body: ResetRequest,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> dict:
    """Wipe all user data (database + work-files).

    The caller must send ``{"confirmation": "DELETE"}`` to proceed.
    """
    _require_feature_enabled()

    if body.confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation required: send {"confirmation": "DELETE"} to proceed.',
        )

    from app.utils.system_reset import perform_full_reset

    try:
        result = perform_full_reset(db)
    except Exception as exc:
        logger.exception("Full system reset failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"System reset failed: {exc}",
        ) from exc

    return {"status": "ok", "result": result}


@router.post("/reimport")
async def reset_and_reimport(
    body: ResetRequest,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> dict:
    """Move original files to a reimport folder, wipe everything, and
    configure the reimport folder as a watch folder for automatic
    re-ingestion.

    The caller must send ``{"confirmation": "REIMPORT"}`` to proceed.
    """
    _require_feature_enabled()

    if body.confirmation != "REIMPORT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation required: send {"confirmation": "REIMPORT"} to proceed.',
        )

    from app.utils.system_reset import perform_reset_and_reimport

    try:
        result = perform_reset_and_reimport(db)
    except Exception as exc:
        logger.exception("Reset-and-reimport failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reset and reimport failed: {exc}",
        ) from exc

    return {"status": "ok", "result": result}


@router.get("/status")
async def reset_status(_admin: AdminUser) -> dict:
    """Return whether the system reset feature is enabled."""
    return {
        "enabled": settings.enable_factory_reset,
        "factory_reset_on_startup": settings.factory_reset_on_startup,
    }
