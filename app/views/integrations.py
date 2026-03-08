"""User-facing view for the unified Sources & Destinations dashboard."""

import logging

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models import IntegrationDirection, IntegrationType, UserIntegration
from app.utils.subscription import get_tier, get_user_tier_id
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()

# Source types that consume the mailbox quota (mirrored from app.api.integrations)
_MAILBOX_SOURCE_TYPES = {IntegrationType.IMAP}
_FREE_TIER_ID = "free"


def _get_max_destinations(tier: dict) -> int | None:
    """Return the maximum number of storage destinations allowed by *tier*.

    Returns ``None`` for unlimited, or a positive int for the cap.
    """
    tier_id: str = tier.get("id", _FREE_TIER_ID)
    max_dest: int = tier.get("max_storage_destinations", 0)
    if tier_id == _FREE_TIER_ID:
        return max_dest if max_dest > 0 else 1
    if max_dest == 0:
        return None
    return max_dest


def _get_max_sources(tier: dict) -> int | None:
    """Return the maximum number of IMAP sources allowed by *tier*.

    Returns ``None`` for unlimited, ``0`` for no access, or a positive int.
    """
    tier_id: str = tier.get("id", _FREE_TIER_ID)
    max_mb: int = tier.get("max_mailboxes", 0)
    if tier_id == _FREE_TIER_ID:
        return 0
    if max_mb == 0:
        return None
    return max_mb


@router.get("/integrations")
@require_login
async def integrations_dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the unified Sources & Destinations dashboard."""
    try:
        owner_id = get_current_owner_id(request)

        dest_count = 0
        src_count = 0
        max_destinations: int | None = 1
        max_sources: int | None = 0
        can_add_destination = False
        can_add_source = False
        tier_name = "Free"
        tier_id = "free"

        if owner_id:
            integrations = (
                db.query(UserIntegration)
                .filter(UserIntegration.owner_id == owner_id)
                .order_by(UserIntegration.id)
                .all()
            )
            dest_count = sum(1 for i in integrations if i.direction == IntegrationDirection.DESTINATION)
            src_count = sum(
                1
                for i in integrations
                if i.direction == IntegrationDirection.SOURCE and i.integration_type in _MAILBOX_SOURCE_TYPES
            )
            tier_id = get_user_tier_id(db, owner_id)
            tier = get_tier(tier_id, db)
            tier_name = tier.get("name", tier_id)
            max_destinations = _get_max_destinations(tier)
            max_sources = _get_max_sources(tier)
            can_add_destination = max_destinations is None or dest_count < max_destinations
            can_add_source = max_sources is None or (max_sources > 0 and src_count < max_sources)

        return templates.TemplateResponse(
            "integrations_dashboard.html",
            {
                "request": request,
                "dest_count": dest_count,
                "src_count": src_count,
                "max_destinations": max_destinations,
                "max_sources": max_sources,
                "can_add_destination": can_add_destination,
                "can_add_source": can_add_source,
                "tier_id": tier_id,
                "tier_name": tier_name,
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error loading integrations dashboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load integrations dashboard",
        )
