"""
Common utilities for API routes
"""

import logging
import os
from pathlib import Path
from fastapi import HTTPException, status

from app.database import SessionLocal
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)


def get_db():
    """Database dependency injection for routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def resolve_file_path(file_path: str, subfolder: str = None) -> str:
    """
    Resolves a file path to an absolute path with path traversal protection.
    If the path is not absolute, it will be joined with the workdir path.
    Optionally, can include a subfolder like 'processed'.

    Security: Validates that the resolved path stays within the workdir
    to prevent path traversal attacks (e.g., ../../etc/passwd).

    Args:
        file_path: The file path to resolve
        subfolder: Optional subfolder within workdir

    Returns:
        The validated absolute file path

    Raises:
        HTTPException: If the path attempts to escape the workdir
    """
    # Build the base directory
    if subfolder:
        base_dir = Path(settings.workdir) / subfolder
    else:
        base_dir = Path(settings.workdir)

    # Resolve the file path
    if not os.path.isabs(file_path):
        resolved_path = (base_dir / file_path).resolve()
    else:
        resolved_path = Path(file_path).resolve()

    # Ensure the resolved path is within the base directory (path traversal protection)
    try:
        resolved_path.relative_to(base_dir.resolve())
    except ValueError:
        # Path is outside the base directory - potential path traversal attack
        logger.warning(f"Path traversal attempt detected: {file_path} -> {resolved_path}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path: path traversal not allowed"
        )

    return str(resolved_path)
