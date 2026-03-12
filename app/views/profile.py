"""View route for the user self-service profile settings page.

Route:
  GET /profile  — renders the profile settings HTML page (requires login)
"""

from __future__ import annotations

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models import UserProfile
from app.utils.i18n import SUPPORTED_LANGUAGES
from app.views.base import APIRouter, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/profile", include_in_schema=False)
@require_login
async def profile_page(request: Request, db: Session = Depends(get_db)):
    """Serve the user profile settings page."""
    user = request.session.get("user") or {}
    user_id = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")

    profile = None
    if user_id:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "profile": profile,
            "supported_languages": SUPPORTED_LANGUAGES,
        },
    )
