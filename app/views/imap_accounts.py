"""User-facing view for the per-user IMAP ingestion dashboard."""

import json
import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import ImapIngestionProfile, UserImapAccount
from app.utils.allowed_types import FILE_TYPE_CATEGORIES
from app.utils.subscription import get_tier, get_user_tier_id
from app.utils.user_scope import get_current_owner_id
from app.views.base import APIRouter, Depends, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_max_mailboxes(tier: dict) -> int | None:
    """Mirror of the quota helper from the API module — avoids a circular import."""
    tier_id: str = tier.get("id", "free")
    max_mb: int = tier.get("max_mailboxes", 0)
    if tier_id == "free":
        return 0
    if max_mb == 0:
        return None
    return max_mb


def _serialize_profile(profile: ImapIngestionProfile) -> dict:
    """Serialize a profile for JSON embedding in the template."""
    try:
        categories = json.loads(profile.allowed_categories)
    except (ValueError, TypeError):
        categories = []
    return {
        "id": profile.id,
        "name": profile.name,
        "description": profile.description,
        "owner_id": profile.owner_id,
        "allowed_categories": categories,
        "is_builtin": profile.is_builtin,
    }


@router.get("/imap-accounts")
@require_login
async def imap_accounts_page(request: Request, db: Session = Depends(get_db)):
    """IMAP ingestion account management page for the current user."""
    owner_id = get_current_owner_id(request)

    accounts: list[UserImapAccount] = []
    current_count = 0
    max_mailboxes: int | None = 0
    can_add = False
    tier_name = "Free"
    tier_id = "free"

    if owner_id:
        accounts = (
            db.query(UserImapAccount).filter(UserImapAccount.owner_id == owner_id).order_by(UserImapAccount.id).all()
        )
        current_count = len(accounts)
        tier_id = get_user_tier_id(db, owner_id)
        tier = get_tier(tier_id, db)
        tier_name = tier.get("name", tier_id)
        max_mailboxes = _get_max_mailboxes(tier)
        can_add = max_mailboxes is None or (max_mailboxes > 0 and current_count < max_mailboxes)

    # Load ingestion profiles: system-global + user's own
    profiles: list[ImapIngestionProfile] = (
        db.query(ImapIngestionProfile)
        .filter(
            (ImapIngestionProfile.owner_id == None)  # noqa: E711
            | (ImapIngestionProfile.owner_id == owner_id)
        )
        .order_by(ImapIngestionProfile.is_builtin.desc(), ImapIngestionProfile.id)
        .all()
        if owner_id
        else db.query(ImapIngestionProfile)
        .filter(ImapIngestionProfile.owner_id == None)  # noqa: E711
        .order_by(ImapIngestionProfile.id)
        .all()
    )

    # Category definitions for the UI checkbox builder
    categories = [
        {
            "key": key,
            "label": info["label"],
            "description": info["description"],
        }
        for key, info in FILE_TYPE_CATEGORIES.items()
    ]

    return templates.TemplateResponse(
        "imap_accounts.html",
        {
            "request": request,
            "accounts": accounts,
            "profiles": [_serialize_profile(p) for p in profiles],
            "categories": categories,
            "current_count": current_count,
            "max_mailboxes": max_mailboxes,
            "can_add": can_add,
            "tier_id": tier_id,
            "tier_name": tier_name,
        },
    )
