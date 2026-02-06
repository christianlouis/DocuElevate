"""
Common utilities for API routes
"""
import logging
import os
from sqlalchemy.orm import Session
from fastapi import Depends

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
    
    Returns the absolute file path.
    
    Raises:
        ValueError: If the resolved path is outside the allowed base directory.
    """
    # Determine the base directory
    if subfolder:
        base_dir = os.path.join(settings.workdir, subfolder)
    else:
        base_dir = settings.workdir
    
    # Normalize the base directory to absolute path
    base_dir = os.path.realpath(base_dir)
    
    # If the file_path is absolute, use it directly; otherwise join with base_dir
    if os.path.isabs(file_path):
        resolved_path = os.path.realpath(file_path)
    else:
        resolved_path = os.path.realpath(os.path.join(base_dir, file_path))
    
    # Verify the resolved path is within the base directory
    try:
        common_path = os.path.commonpath([base_dir, resolved_path])
    except ValueError:
        # os.path.commonpath raises ValueError if paths are on different drives (Windows)
        # This indicates path traversal attempt
        raise ValueError(f"Path traversal detected: {file_path} resolves outside base directory")
    
    if common_path != base_dir:
        raise ValueError(f"Path traversal detected: {file_path} resolves outside base directory")
    
    return resolved_path
