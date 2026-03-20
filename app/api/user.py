"""
User-related API endpoints
"""

import logging
from hashlib import md5
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import FileRecord, UserProfile

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


async def whoami_handler(request: Request, db: Session):
    """
    Returns user info if logged in, else 401.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User has no email in session")

    # Generate Gravatar URL from email
    # MD5 is used here for Gravatar's URL generation (not for security), so usedforsecurity=False
    email_hash = md5(email.strip().lower().encode(), usedforsecurity=False).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    # Add the gravatar URL to the user object instead of creating a new response
    user_response = user.copy()  # Create a copy to avoid modifying the session

    # Check if the user has a custom avatar stored in their profile
    user_id = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")
    if user_id:
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
            if profile and profile.avatar_data:
                user_response["picture"] = profile.avatar_data
            else:
                user_response["picture"] = gravatar_url
        except Exception:
            user_response["picture"] = gravatar_url
    else:
        user_response["picture"] = gravatar_url

    return user_response


# Register the same handler under two different paths
@router.get("/whoami")
async def whoami(request: Request, db: DbSession):
    return await whoami_handler(request, db)


@router.get("/auth/whoami")
async def auth_whoami(request: Request, db: DbSession):
    return await whoami_handler(request, db)


@router.get("/users/search")
@require_login
def search_known_users(
    db: DbSession,
    q: str = Query("", description="Substring to match against known owner IDs"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of results"),
):
    """
    Search known user identifiers (owner_ids) from existing documents.

    Returns distinct ``owner_id`` values from the files table that contain
    the query string as a case-insensitive substring.  Results are limited
    to at most ``limit`` entries (default 5).

    This powers the autocomplete widget on the settings page for the
    ``default_owner_id`` field.
    """
    base_query = db.query(FileRecord.owner_id).filter(FileRecord.owner_id.isnot(None)).distinct()

    if q.strip():
        base_query = base_query.filter(func.lower(FileRecord.owner_id).contains(q.strip().lower()))

    results = base_query.order_by(FileRecord.owner_id).limit(limit).all()

    return {"users": [row[0] for row in results]}
