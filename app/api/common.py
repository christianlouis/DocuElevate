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
    Resolves a file path to an absolute path.
    If the path is not absolute, it will be joined with the workdir path.
    Optionally, can include a subfolder like 'processed'.
    
    Returns the absolute file path.
    """
    if not os.path.isabs(file_path):
        if subfolder:
            file_path = os.path.join(settings.workdir, subfolder, file_path)
        else:
            file_path = os.path.join(settings.workdir, file_path)
    return file_path
