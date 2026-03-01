"""
Saved searches API endpoints.

Provides CRUD operations for user-defined saved search filters.
Each user can save, list, update, and delete named filter combinations
for quick access on the files page.
"""

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_login
from app.database import get_db
from app.models import SavedSearch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/saved-searches", tags=["saved-searches"])

DbSession = Annotated[Session, Depends(get_db)]

# Allowed filter keys that can be saved.
# Files-view keys: search, mime_type, status, storage_provider, sort_by, sort_order
# Search-view keys: q, document_type, language, sender, text_quality
# Shared keys: tags, date_from, date_to
ALLOWED_FILTER_KEYS = frozenset(
    {
        "search",
        "q",
        "mime_type",
        "status",
        "date_from",
        "date_to",
        "storage_provider",
        "tags",
        "sort_by",
        "sort_order",
        "document_type",
        "language",
        "sender",
        "text_quality",
    }
)

# Maximum number of saved searches per user
MAX_SAVED_SEARCHES_PER_USER = 50

# Maximum length for saved search name
MAX_NAME_LENGTH = 100


def _get_user_id(request: Request) -> str:
    """Extract user identifier from the session.

    Returns the preferred_username, email, or 'anonymous' if auth is disabled.

    Args:
        request: The incoming HTTP request.

    Returns:
        A string identifying the current user.
    """
    user = get_current_user(request)
    if user:
        return user.get("preferred_username") or user.get("email") or user.get("name", "anonymous")
    return "anonymous"


def _validate_filters(filters: Any) -> dict:
    """Validate and sanitize filter parameters.

    Ensures only allowed filter keys are present and values are strings.

    Args:
        filters: The raw filter value from the client.

    Returns:
        A sanitized filter dictionary with only allowed keys.

    Raises:
        HTTPException: If filters is not a dict or contains invalid values.
    """
    if not isinstance(filters, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="filters must be a JSON object",
        )
    sanitized = {}
    for key, value in filters.items():
        if key in ALLOWED_FILTER_KEYS and isinstance(value, str) and value.strip():
            sanitized[key] = value.strip()
    return sanitized


def _serialize_saved_search(s: SavedSearch) -> dict:
    """Serialize a SavedSearch model instance to a JSON-compatible dict.

    Args:
        s: The SavedSearch model instance.

    Returns:
        A dictionary with id, name, filters, created_at, and updated_at.
    """
    return {
        "id": s.id,
        "name": s.name,
        "filters": json.loads(s.filters),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.get("")
@require_login
def list_saved_searches(request: Request, db: DbSession):
    """List all saved searches for the current user.

    Returns:
        A list of saved search objects with id, name, filters, and timestamps.
    """
    user_id = _get_user_id(request)
    searches = db.query(SavedSearch).filter(SavedSearch.user_id == user_id).order_by(SavedSearch.name).all()
    return [_serialize_saved_search(s) for s in searches]


@router.post("", status_code=status.HTTP_201_CREATED)
@require_login
def create_saved_search(
    request: Request,
    db: DbSession,
    name: str = Body(..., embed=True),
    filters: dict = Body(..., embed=True),
):
    """Create a new saved search for the current user.

    Request body (JSON):
        name: Display name for the saved search (required, max 100 chars)
        filters: Dictionary of filter parameters (required)

    Returns:
        The created saved search object.

    Raises:
        HTTPException 422: If name or filters are invalid.
        HTTPException 409: If a saved search with the same name already exists.
    """
    user_id = _get_user_id(request)

    name = name.strip() if isinstance(name, str) else ""
    if not name or len(name) > MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"name is required and must be at most {MAX_NAME_LENGTH} characters",
        )

    sanitized_filters = _validate_filters(filters)
    if not sanitized_filters:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one filter parameter is required",
        )

    # Check user limit
    count = db.query(SavedSearch).filter(SavedSearch.user_id == user_id).count()
    if count >= MAX_SAVED_SEARCHES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum of {MAX_SAVED_SEARCHES_PER_USER} saved searches reached",
        )

    # Check for duplicate name
    existing = db.query(SavedSearch).filter(SavedSearch.user_id == user_id, SavedSearch.name == name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A saved search named '{name}' already exists",
        )

    saved_search = SavedSearch(
        user_id=user_id,
        name=name,
        filters=json.dumps(sanitized_filters),
    )

    try:
        db.add(saved_search)
        db.commit()
        db.refresh(saved_search)
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to create saved search for user={user_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save search",
        )

    logger.info(f"Saved search created: user={user_id}, name={name!r}")
    return _serialize_saved_search(saved_search)


@router.put("/{search_id}")
@require_login
def update_saved_search(
    search_id: int,
    request: Request,
    db: DbSession,
    name: str | None = Body(None, embed=True),
    filters: dict | None = Body(None, embed=True),
):
    """Update an existing saved search.

    Path Parameters:
        search_id: The ID of the saved search to update.

    Request body (JSON):
        name: New display name (optional)
        filters: New filter parameters (optional)

    Returns:
        The updated saved search object.

    Raises:
        HTTPException 404: If the saved search is not found.
        HTTPException 409: If the new name conflicts with an existing saved search.
    """
    user_id = _get_user_id(request)
    saved_search = db.query(SavedSearch).filter(SavedSearch.id == search_id, SavedSearch.user_id == user_id).first()
    if not saved_search:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")

    if name is not None:
        new_name = name.strip() if isinstance(name, str) else ""
        if not new_name or len(new_name) > MAX_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"name must be non-empty and at most {MAX_NAME_LENGTH} characters",
            )
        # Check for name conflict
        if new_name != saved_search.name:
            existing = (
                db.query(SavedSearch).filter(SavedSearch.user_id == user_id, SavedSearch.name == new_name).first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A saved search named '{new_name}' already exists",
                )
        saved_search.name = new_name

    if filters is not None:
        sanitized_filters = _validate_filters(filters)
        if not sanitized_filters:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one filter parameter is required",
            )
        saved_search.filters = json.dumps(sanitized_filters)

    try:
        db.commit()
        db.refresh(saved_search)
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to update saved search id={search_id}, user={user_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update saved search",
        )

    logger.info(f"Saved search updated: id={search_id}, user={user_id}")
    return _serialize_saved_search(saved_search)


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_saved_search(search_id: int, request: Request, db: DbSession):
    """Delete a saved search.

    Path Parameters:
        search_id: The ID of the saved search to delete.

    Raises:
        HTTPException 404: If the saved search is not found.
    """
    user_id = _get_user_id(request)
    saved_search = db.query(SavedSearch).filter(SavedSearch.id == search_id, SavedSearch.user_id == user_id).first()
    if not saved_search:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")

    try:
        db.delete(saved_search)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(f"Failed to delete saved search id={search_id}, user={user_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete saved search",
        )

    logger.info(f"Saved search deleted: id={search_id}, user={user_id}")
