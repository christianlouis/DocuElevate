"""API endpoints for the user onboarding wizard.

Provides a REST interface for the multi-step onboarding flow, allowing
authenticated users to set their profile, choose a subscription plan,
select a storage destination, and mark onboarding as complete.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DEFAULT_TENANT_ID, Tribe, TribeMembership, UserIntegration, UserProfile
from app.utils.subscription import TIERS
from app.utils.tribe_scope import (
    canonical_tribe_name,
    ensure_personal_scope,
    ensure_tribe_membership,
    personal_tribe_id,
    shared_tribe_id,
)

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
    space_mode: Literal["personal", "shared"] = "personal"
    tribe_name: str | None = Field(default=None, max_length=255)


class PlanBody(BaseModel):
    """Body for the plan step of the onboarding wizard."""

    subscription_tier: str
    billing_cycle: str = Field(pattern="^(monthly|yearly)$")


class StorageBody(BaseModel):
    """Body for the storage step of the onboarding wizard."""

    preferred_destination: str | None = Field(default=None, max_length=50)


_JOURNEY_TOPICS = {"welcome", "profile", "plan", "processing", "sources", "destinations", "automation", "review"}


class ProgressBody(BaseModel):
    """Persist a safe resume point and optional completed/skipped topic."""

    current_step: int = Field(ge=1, le=8)
    completed_topic: str | None = None
    skipped_topic: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile_to_dict(profile: UserProfile) -> dict[str, Any]:
    """Serialize a UserProfile to a plain dict for API responses."""
    journey = _journey_state(profile)
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
        "onboarding_current_step": profile.onboarding_current_step or 1,
        "onboarding_journey": journey,
    }


def _journey_state(profile: UserProfile) -> dict[str, Any]:
    """Load the non-sensitive onboarding journey state safely."""
    try:
        journey = json.loads(profile.onboarding_journey_state or "{}")
    except (TypeError, json.JSONDecodeError):
        journey = {}
    if not isinstance(journey, dict):
        journey = {}
    # Keep the response shape stable for a brand-new profile and older rows.
    # The UI can then render an honest review without guessing whether a
    # missing list means "not visited" or "nothing skipped".
    journey["completed"] = sorted(topic for topic in set(journey.get("completed") or []) if topic in _JOURNEY_TOPICS)
    journey["skipped"] = sorted(topic for topic in set(journey.get("skipped") or []) if topic in _JOURNEY_TOPICS)
    return journey


def _get_or_create_profile(db: Session, user_id: str) -> UserProfile:
    """Return the UserProfile for *user_id*, creating one if it does not exist."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.flush()
    return profile


def _spaces_for_user(db: Session, user_id: str) -> list[dict[str, Any]]:
    """Return only the Tribes the authenticated user belongs to."""
    rows = (
        db.query(TribeMembership, Tribe)
        .join(Tribe, Tribe.id == TribeMembership.tribe_id)
        .filter(TribeMembership.user_id == user_id)
        .order_by(Tribe.created_at.asc(), Tribe.name.asc())
        .all()
    )
    return [
        {
            "tenant_id": tribe.tenant_id,
            "tribe_id": tribe.id,
            "name": tribe.name,
            "role": membership.role,
            "is_personal": tribe.id == personal_tribe_id(user_id, tribe.tenant_id),
        }
        for membership, tribe in rows
    ]


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
    spaces = _spaces_for_user(db, user_id)

    if profile is None:
        return {
            "completed": False,
            "step": 1,
            "profile": None,
            "spaces": spaces,
            "integrations": {"sources": 0, "destinations": 0},
        }

    # Derive a sensible current step from saved data so the wizard can resume.
    step = profile.onboarding_current_step or 1
    if profile.onboarding_completed:
        step = 8

    integrations = db.query(UserIntegration.direction).filter(UserIntegration.owner_id == user_id).all()

    return {
        "completed": bool(profile.onboarding_completed),
        "step": step,
        "profile": _profile_to_dict(profile),
        "spaces": spaces,
        "integrations": {
            "sources": sum(1 for (direction,) in integrations if direction == "SOURCE"),
            "destinations": sum(1 for (direction,) in integrations if direction == "DESTINATION"),
        },
    }


@router.post("/progress", summary="Persist onboarding journey progress")
def save_progress(request: Request, body: ProgressBody, db: DbSession) -> dict[str, Any]:
    """Save a per-user resume point without accepting credentials or arbitrary settings."""
    user_id = _get_current_user_id(request)
    profile = _get_or_create_profile(db, user_id)
    journey = _journey_state(profile)

    completed = set(journey.get("completed", []))
    skipped = set(journey.get("skipped", []))
    for topic in (body.completed_topic, body.skipped_topic):
        if topic is not None and topic not in _JOURNEY_TOPICS:
            raise HTTPException(status_code=422, detail="Unknown onboarding topic")

    # A later choice supersedes an earlier one. Without this, returning to a
    # skipped step and completing it leaves the journey in two contradictory
    # states and the final review cannot be trusted.
    if body.completed_topic is not None:
        completed.add(body.completed_topic)
        skipped.discard(body.completed_topic)
    if body.skipped_topic is not None:
        skipped.add(body.skipped_topic)
        completed.discard(body.skipped_topic)

    profile.onboarding_current_step = body.current_step
    journey["completed"] = sorted(completed)
    journey["skipped"] = sorted(skipped)
    profile.onboarding_journey_state = json.dumps(journey, separators=(",", ":"))
    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise
    return {
        "success": True,
        "step": profile.onboarding_current_step,
        "journey": _profile_to_dict(profile)["onboarding_journey"],
    }


@router.post("/profile", summary="Save profile step during onboarding")
def save_profile(request: Request, body: ProfileBody, db: DbSession) -> dict[str, Any]:
    """Persist the profile and establish the user's first safe document spaces."""
    user_id = _get_current_user_id(request)
    shared_name = " ".join((body.tribe_name or "").split())
    shared_tribe: Tribe | None = None

    if body.space_mode == "shared":
        if not shared_name:
            raise HTTPException(status_code=422, detail="Enter a name for the shared space")
        canonical_name = canonical_tribe_name(shared_name)
        if canonical_name.startswith("personal space for "):
            raise HTTPException(status_code=422, detail="Choose a different shared space name")
        shared_tribe = next(
            (
                tribe
                for tribe in db.query(Tribe).filter(Tribe.tenant_id == DEFAULT_TENANT_ID).all()
                if canonical_tribe_name(tribe.name) == canonical_name
            ),
            None,
        )
        if shared_tribe is not None:
            membership = (
                db.query(TribeMembership)
                .filter(
                    TribeMembership.tribe_id == shared_tribe.id,
                    TribeMembership.user_id == user_id,
                )
                .first()
            )
            if membership is None:
                raise HTTPException(
                    status_code=409,
                    detail="This shared space cannot be created. Ask its administrator for an invitation.",
                )

    profile = _get_or_create_profile(db, user_id)

    if body.display_name is not None:
        profile.display_name = body.display_name
    if body.contact_email is not None:
        profile.contact_email = body.contact_email

    ensure_personal_scope(db, user_id)
    if body.space_mode == "shared" and shared_tribe is None:
        shared_tribe = Tribe(
            id=shared_tribe_id(shared_name),
            tenant_id=DEFAULT_TENANT_ID,
            name=shared_name,
        )
        try:
            with db.begin_nested():
                db.add(shared_tribe)
                db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="This shared space cannot be created. Ask its administrator for an invitation.",
            ) from exc
    if body.space_mode == "shared" and shared_tribe is not None:
        ensure_tribe_membership(
            db,
            tenant_id=DEFAULT_TENANT_ID,
            tribe_id=shared_tribe.id,
            user_id=user_id,
            role="admin",
        )

    journey = _journey_state(profile)
    journey["space_mode"] = body.space_mode
    journey["selected_tribe_id"] = (
        shared_tribe.id if body.space_mode == "shared" and shared_tribe is not None else personal_tribe_id(user_id)
    )
    profile.onboarding_journey_state = json.dumps(journey, separators=(",", ":"))

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Onboarding: saved profile for user %s", user_id)
    return {**_profile_to_dict(profile), "spaces": _spaces_for_user(db, user_id)}


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
    old_tier = profile.subscription_tier or "free"
    profile.subscription_tier = body.subscription_tier
    profile.subscription_billing_cycle = body.billing_cycle

    try:
        db.commit()
        db.refresh(profile)
    except Exception:
        db.rollback()
        raise

    logger.info("Onboarding: saved plan %s/%s", body.subscription_tier, body.billing_cycle)

    # Notify admins and fire webhook when the plan actually changes
    if old_tier != body.subscription_tier:
        try:
            from app.utils.notification import notify_plan_changed
            from app.utils.webhook import dispatch_webhook_event

            notify_plan_changed(user_id, old_tier=old_tier, new_tier=body.subscription_tier, changed_by="user")
            dispatch_webhook_event(
                "user.plan_changed",
                {
                    "user_id": user_id,
                    "old_tier": old_tier,
                    "new_tier": body.subscription_tier,
                    "billing_cycle": body.billing_cycle,
                    "changed_by": "user",
                },
            )
        except Exception:
            logger.exception("Failed to send plan-change notification/webhook for user %s", user_id)

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
    ``/upload?onboarding=first-document`` when the session key is absent. A
    plain ``/upload`` saved by the authentication flow is normalized to the
    same first-document destination, while explicit custom redirects are
    preserved.
    """
    user_id = _get_current_user_id(request)
    profile = _get_or_create_profile(db, user_id)
    profile.onboarding_completed = True
    profile.onboarding_completed_at = datetime.now(tz=timezone.utc)
    profile.onboarding_current_step = 8
    ensure_personal_scope(db, user_id)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    redirect_url = request.session.pop("post_onboarding_redirect", "/upload?onboarding=first-document")
    if redirect_url == "/upload":
        redirect_url = "/upload?onboarding=first-document"
    logger.info("Onboarding: completed for user %s, redirecting to %s", user_id, redirect_url)
    return {"success": True, "redirect_url": redirect_url}
