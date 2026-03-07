"""API endpoints for the user onboarding wizard.

Provides a REST interface for the multi-step onboarding flow, allowing
authenticated users to set their profile, choose a subscription plan,
select a storage destination, and mark onboarding as complete.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserProfile
from app.utils.subscription import TIERS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_current_user_id(request: Request) -> str:
    """Extract the stable user_id from the session using the same priority as _ensure_user_profile.

    Priority: sub → preferred_username → email → id.

    Raises:
        HTTPException: 401 if the user is not authenticated.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_id


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ProfileBody(BaseModel):
    """Body for the profile step of the onboarding wizard."""

    display_name: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)


class PlanBody(BaseModel):
    """Body for the plan step of the onboarding wizard."""

    subscription_tier: str
    billing_cycle: str = Field(pattern="^(monthly|yearly)$")


class StorageBody(BaseModel):
    """Body for the storage step of the onboarding wizard."""

    preferred_destination: str | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    """Serialize a UserProfile to a plain dict for API responses."""
    return {
        "user_id": profile.user_id,
        "display_name": profile.display_name,
        "contact_email": profile.contact_email,
        "subscription_tier": profile.subscription_tier or "free",
        "subscription_billing_cycle": profile.subscription_billing_cycle or "monthly",
        "preferred_destination": profile.preferred_destination,
        "onboarding_completed": bool(profile.onboarding_completed),
        "onboarding_completed_at": profile.onboarding_completed_at.isoformat()
        if profile.onboarding_completed_at
        else None,
    }


def _get_or_create_profile(db: Session, user_id: str) -> UserProfile:
    """Return the UserProfile for *user_id*, creating one if it does not exist."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", summary="Get onboarding status for the current user")
def get_onboarding_status(request: Request, db: DbSession) -> dict[str, Any]:
    """Return whether onboarding has been completed and the current step.

    The ``step`` field is a best-effort estimate: 1 for brand-new profiles,
    further along when partial data has already been saved.
    """
    user_id = _get_current_user_id(request)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    if profile is None:
        return {"completed": False, "step": 1, "profile": None}

    # Derive a sensible current step from saved data so the wizard can resume.
    step = 1
    if profile.display_name or profile.contact_email:
        step = 2
    if profile.subscription_tier and profile.subscription_tier != "free":
        step = 3
    if profile.preferred_destination:
        step = 4
    if profile.onboarding_completed:
        step = 5

    return {
        "completed": bool(profile.onboarding_completed),
        "step": step,
        "profile": _profile_to_dict(profile),
    }


@router.post("/profile", summary="Save profile step during onboarding")
def save_profile(request: Request, body: ProfileBody, db: DbSession) -> dict[str, Any]:
    """Persist the user's display name and contact email from the profile step."""
    user_id = _get_current_user_id(request)
    profile = _get_or_create_profile(db, user_id)

    if body.display_name is not None:
        profile.display_name = body.display_name
    if body.contact_email is not None:
        profile.contact_email = body.contact_email

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Onboarding: saved profile for user %s", user_id)
    return _profile_to_dict(profile)


@router.post("/plan", summary="Save plan selection during onboarding")
def save_plan(request: Request, body: PlanBody, db: DbSession) -> dict[str, Any]:
    """Persist the chosen subscription tier and billing cycle from the plan step.

    Raises:
        HTTPException: 422 if the tier is not a recognised value.
    """
    user_id = _get_current_user_id(request)

    if body.subscription_tier not in TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid subscription_tier '{body.subscription_tier}'. Valid values: {list(TIERS.keys())}",
        )

    profile = _get_or_create_profile(db, user_id)
    profile.subscription_tier = body.subscription_tier
    profile.subscription_billing_cycle = body.billing_cycle

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Onboarding: saved plan %s/%s", body.subscription_tier, body.billing_cycle)
    return _profile_to_dict(profile)


@router.post("/storage", summary="Save storage preference during onboarding")
def save_storage(request: Request, body: StorageBody, db: DbSession) -> dict[str, Any]:
    """Persist the user's preferred storage destination from the storage step."""
    user_id = _get_current_user_id(request)
    profile = _get_or_create_profile(db, user_id)
    profile.preferred_destination = body.preferred_destination

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Onboarding: saved storage preference '%s' for user %s", body.preferred_destination, user_id)
    return _profile_to_dict(profile)


@router.post("/complete", summary="Mark onboarding as completed")
def complete_onboarding(request: Request, db: DbSession) -> dict[str, Any]:
    """Set onboarding_completed=True, record the completion timestamp, and return the post-onboarding redirect URL.

    The redirect URL is read from ``request.session["post_onboarding_redirect"]`` (stored by
    ``oauth_callback`` when it reroutes a first-time user to the wizard) and defaults to
    ``/upload`` when the session key is absent.
    """
    user_id = _get_current_user_id(request)
    profile = _get_or_create_profile(db, user_id)
    profile.onboarding_completed = True
    profile.onboarding_completed_at = datetime.now(tz=timezone.utc)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    redirect_url = request.session.pop("post_onboarding_redirect", "/upload")
    logger.info("Onboarding: completed for user %s, redirecting to %s", user_id, redirect_url)
    return {"success": True, "redirect_url": redirect_url}
