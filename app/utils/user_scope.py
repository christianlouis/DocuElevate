"""
User-scoping utilities for multi-user document isolation.

When ``multi_user_enabled`` is ``True`` in settings, every document query
is filtered by the authenticated user's identifier so that each user sees
only their own documents.  When the flag is ``False`` (default), all
documents are visible to all users (single-user / shared mode).
"""

import logging

from fastapi import Request
from sqlalchemy import or_
from sqlalchemy.orm import Query
from sqlalchemy.sql import false

from app.config import settings
from app.models import FileRecord

logger = logging.getLogger(__name__)


def get_current_owner_id(request: Request) -> str | None:
    """Extract the owner identifier for the current authenticated user.

    The owner ID is derived from the user's session data.  It uses the
    ``sub`` claim (OAuth subject) when available, falling back to
    ``preferred_username`` or ``email``.  Returns ``None`` when no user
    is authenticated.

    Args:
        request: The current FastAPI request with session data.

    Returns:
        A stable string identifier for the user, or ``None``.
    """
    user = request.session.get("user")
    if not user or not isinstance(user, dict):
        return None
    # Prefer 'sub' (OAuth subject), then 'preferred_username', then 'email', then 'id'
    return user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")


def apply_owner_filter(query: Query, request: Request) -> Query:
    """Conditionally filter a ``FileRecord`` query by the current user.

    When multi-user mode is enabled, only files whose ``owner_id``
    matches the authenticated user are returned.  Admin users bypass
    the filter and see all documents.

    When ``unowned_docs_visible_to_all`` is ``True`` (default), documents
    with ``owner_id IS NULL`` (unclaimed) are also included for every
    authenticated user so they can be discovered and claimed.

    When multi-user mode is disabled the query is returned unchanged.

    Args:
        query: A SQLAlchemy query selecting ``FileRecord`` rows.
        request: The current FastAPI request (for session inspection).

    Returns:
        The (possibly filtered) query.
    """
    if not settings.multi_user_enabled:
        return query

    user = request.session.get("user")
    if isinstance(user, dict) and user.get("is_admin"):
        # Admins see all documents in multi-user mode
        return query

    owner_id = get_current_owner_id(request)
    if owner_id is None:
        # No authenticated user — return empty result set
        return query.filter(false())

    # Build filter: user's own documents
    conditions = [FileRecord.owner_id == owner_id]

    # Optionally include unclaimed (owner_id IS NULL) documents
    if settings.unowned_docs_visible_to_all:
        conditions.append(FileRecord.owner_id.is_(None))

    return query.filter(or_(*conditions))
