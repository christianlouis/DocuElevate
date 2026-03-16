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


def _owner_id_from_user(user: dict) -> str | None:
    """Extract the owner identifier from a user dict.

    Priority: ``sub`` (OAuth subject) → ``preferred_username`` → ``email`` → ``id``.
    """
    return user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")


def get_current_owner_id(request: Request) -> str | None:
    """Extract the owner identifier for the current authenticated user.

    The owner ID is derived from the user's session data or, when no session
    is present, from a valid Bearer API token in the ``Authorization`` header.
    This ensures that both browser-based (session cookie) and mobile/API
    (Bearer token) requests are correctly identified.

    Priority for user resolution:

    1. Session ``user`` dict (set by OAuth or local login).
    2. ``request.state.api_token_user`` (set by ``require_login`` or an
       earlier call to this function during the same request).
    3. Direct Bearer token look-up against the database.

    Within the resolved user dict the owner ID is chosen as:
    ``sub`` → ``preferred_username`` → ``email`` → ``id``.

    Args:
        request: The current FastAPI request with session data.

    Returns:
        A stable string identifier for the user, or ``None``.
    """
    # 1. Session-based auth (most common for web UI)
    user = request.session.get("user")
    if user and isinstance(user, dict):
        return _owner_id_from_user(user)

    # 2. Already-resolved API token user (cached by require_login or a
    #    prior dependency call during this request)
    api_user = getattr(request.state, "api_token_user", None)
    if isinstance(api_user, dict):
        return _owner_id_from_user(api_user)

    # 3. Direct Bearer token resolution – necessary when this function is
    #    invoked as a FastAPI dependency (via Depends) which runs *before*
    #    the @require_login decorator wrapper has had a chance to resolve
    #    the token and populate request.state.api_token_user.
    auth_header = request.headers.get("authorization", "")
    if isinstance(auth_header, str) and auth_header.startswith("Bearer "):
        try:
            from app.auth import _resolve_bearer_user
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                resolved = _resolve_bearer_user(request, db)
            finally:
                db.close()

            if resolved:
                # Cache so subsequent calls (and require_login) skip the DB
                request.state.api_token_user = resolved
                return _owner_id_from_user(resolved)
        except Exception:
            logger.debug("Bearer token resolution failed in get_current_owner_id")

    return None


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
