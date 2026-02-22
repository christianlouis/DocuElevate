"""
Centralized input validation and sanitization utilities.

Provides reusable validators used across API endpoints to prevent injection attacks,
path traversal, and malformed payloads. See SECURITY_AUDIT.md (Code Security section)
for context.
"""

import logging
import re
from typing import Optional

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Allowed sort fields for the files list endpoint
ALLOWED_SORT_FIELDS = frozenset({"id", "original_filename", "file_size", "mime_type", "created_at"})

# Allowed sort orders
ALLOWED_SORT_ORDERS = frozenset({"asc", "desc"})

# Maximum length for free-text search queries
MAX_SEARCH_QUERY_LENGTH = 255

# Pattern for valid Celery task IDs (UUID v4 format: version=4, variant=[89ab])
_TASK_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)

# Pattern for valid setting keys (alphanumeric + underscore, non-empty, max 128 chars)
_SETTING_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,127}$")


def validate_sort_field(sort_by: str) -> str:
    """
    Validate that *sort_by* is one of the allowed sort fields.

    Args:
        sort_by: The sort field name supplied by the client.

    Returns:
        The validated sort field name (unchanged).

    Raises:
        HTTPException 422: If *sort_by* is not in the allow-list.
    """
    if sort_by not in ALLOWED_SORT_FIELDS:
        allowed = ", ".join(sorted(ALLOWED_SORT_FIELDS))
        logger.warning(f"Invalid sort_by value rejected: {sort_by!r}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_by value '{sort_by}'. Allowed values: {allowed}",
        )
    return sort_by


def validate_sort_order(sort_order: str) -> str:
    """
    Validate that *sort_order* is either 'asc' or 'desc'.

    Args:
        sort_order: The sort order supplied by the client.

    Returns:
        The validated sort order (unchanged).

    Raises:
        HTTPException 422: If *sort_order* is not 'asc' or 'desc'.
    """
    if sort_order not in ALLOWED_SORT_ORDERS:
        logger.warning(f"Invalid sort_order value rejected: {sort_order!r}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sort_order value '{sort_order}'. Allowed values: asc, desc",
        )
    return sort_order


def validate_search_query(search: Optional[str]) -> Optional[str]:
    """
    Sanitize and validate a free-text search query.

    Strips leading/trailing whitespace and enforces a maximum length to prevent
    overly long inputs from reaching the database layer.

    Args:
        search: The search string supplied by the client, or None.

    Returns:
        The sanitized search string, or None if the input was None or empty.

    Raises:
        HTTPException 422: If the search query exceeds MAX_SEARCH_QUERY_LENGTH.
    """
    if search is None:
        return None
    search = search.strip()
    if not search:
        return None
    if len(search) > MAX_SEARCH_QUERY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Search query too long (max {MAX_SEARCH_QUERY_LENGTH} characters)",
        )
    return search


def validate_task_id(task_id: str) -> str:
    """
    Validate that *task_id* matches the expected Celery UUID format.

    Args:
        task_id: The task ID supplied by the client.

    Returns:
        The validated task ID (unchanged).

    Raises:
        HTTPException 422: If *task_id* does not match the expected UUID format.
    """
    if not _TASK_ID_RE.match(task_id):
        logger.warning(f"Invalid task_id format rejected: {task_id!r}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid task_id format. Expected a UUID (e.g. 550e8400-e29b-41d4-a716-446655440000)",
        )
    return task_id


def validate_setting_key_format(key: str) -> str:
    """
    Validate that *key* has a valid setting key format (alphanumeric + underscore,
    starting with a letter).  Does **not** check whether the key exists in the
    ``SETTING_METADATA`` registry — use this for read-only lookups where an
    unknown key should return ``None`` rather than a 404 error.

    Args:
        key: The setting key supplied by the client.

    Returns:
        The validated setting key (unchanged).

    Raises:
        HTTPException 400: If the key contains invalid characters.
    """
    if not _SETTING_KEY_RE.match(key):
        logger.warning(f"Invalid setting key format rejected: {key!r}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid setting key format",
        )
    return key


def validate_setting_key(key: str) -> str:
    """
    Validate that *key* is a syntactically valid setting key.

    Performs two checks:
    1. The key matches the allowed character pattern (alphanumeric + underscore,
       starting with a letter) to prevent attribute injection or enumeration of
       internal Python object attributes.
    2. The key exists in the ``SETTING_METADATA`` registry, so callers cannot
       read or write arbitrary attributes of the ``Settings`` object.

    Args:
        key: The setting key supplied by the client.

    Returns:
        The validated setting key (unchanged).

    Raises:
        HTTPException 400: If the key contains invalid characters.
        HTTPException 404: If the key is not a known setting.
    """
    # Structural check first to avoid importing settings_service unnecessarily
    if not _SETTING_KEY_RE.match(key):
        logger.warning(f"Invalid setting key format rejected: {key!r}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid setting key format",
        )

    # Allow-list check: only expose keys that are declared in SETTING_METADATA
    from app.utils.settings_service import SETTING_METADATA  # local import to avoid circular deps

    if key not in SETTING_METADATA:
        logger.warning(f"Unknown setting key rejected: {key!r}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )

    return key
