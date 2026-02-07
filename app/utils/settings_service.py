"""
Service for managing application settings with database persistence.

This module provides functionality to:
- Load settings from database with precedence over environment variables
- Save settings to database
- Get setting metadata (descriptions, types, categories)
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import ApplicationSettings

logger = logging.getLogger(__name__)

# Define setting metadata for UI display
SETTING_METADATA = {
    # Core Settings
    "database_url": {
        "category": "Core",
        "description": "Database connection URL (e.g., sqlite:///path/to/db.sqlite)",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "redis_url": {
        "category": "Core",
        "description": "Redis connection URL for Celery task queue",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "workdir": {
        "category": "Core",
        "description": "Working directory for file storage and processing",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "external_hostname": {
        "category": "Core",
        "description": "External hostname for the application (e.g., docuelevate.example.com)",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    "debug": {
        "category": "Core",
        "description": "Enable debug mode for verbose logging",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "allow_file_delete": {
        "category": "Core",
        "description": "Allow deleting files from the database",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "gotenberg_url": {
        "category": "Core",
        "description": "Gotenberg service URL for document conversion",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": True,
    },
    
    # Authentication Settings
    "auth_enabled": {
        "category": "Authentication",
        "description": "Enable authentication for the application",
        "type": "boolean",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "session_secret": {
        "category": "Authentication",
        "description": "Secret key for session encryption (min 32 characters)",
        "type": "string",
        "sensitive": True,
        "required": True,
        "restart_required": True,
    },
    "admin_username": {
        "category": "Authentication",
        "description": "Admin username for local authentication",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": True,
    },
    "admin_password": {
        "category": "Authentication",
        "description": "Admin password for local authentication",
        "type": "string",
        "sensitive": True,
        "required": False,
        "restart_required": True,
    },
    
    # AI Services
    "openai_api_key": {
        "category": "AI Services",
        "description": "OpenAI API key for metadata extraction",
        "type": "string",
        "sensitive": True,
        "required": True,
        "restart_required": False,
    },
    "openai_base_url": {
        "category": "AI Services",
        "description": "OpenAI API base URL (default: https://api.openai.com/v1)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "openai_model": {
        "category": "AI Services",
        "description": "OpenAI model to use (e.g., gpt-4o-mini)",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    },
    "azure_ai_key": {
        "category": "AI Services",
        "description": "Azure AI key for document intelligence",
        "type": "string",
        "sensitive": True,
        "required": True,
        "restart_required": False,
    },
    "azure_region": {
        "category": "AI Services",
        "description": "Azure region for AI services",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": False,
    },
    "azure_endpoint": {
        "category": "AI Services",
        "description": "Azure AI endpoint URL",
        "type": "string",
        "sensitive": False,
        "required": True,
        "restart_required": False,
    },
    
    # Add more settings metadata as needed...
}


def get_setting_from_db(db: Session, key: str) -> Optional[str]:
    """
    Retrieve a setting value from the database.
    
    Args:
        db: Database session
        key: Setting key to retrieve
        
    Returns:
        Setting value as string, or None if not found
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        return setting.value if setting else None
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving setting {key} from database: {e}")
        return None


def save_setting_to_db(db: Session, key: str, value: Optional[str]) -> bool:
    """
    Save or update a setting in the database.
    
    Args:
        db: Database session
        key: Setting key
        value: Setting value (as string)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = ApplicationSettings(key=key, value=value)
            db.add(setting)
        db.commit()
        logger.info(f"Saved setting {key} to database")
        return True
    except SQLAlchemyError as e:
        logger.error(f"Error saving setting {key} to database: {e}")
        db.rollback()
        return False


def get_all_settings_from_db(db: Session) -> Dict[str, str]:
    """
    Retrieve all settings from the database.
    
    Args:
        db: Database session
        
    Returns:
        Dictionary of setting key-value pairs
    """
    try:
        settings = db.query(ApplicationSettings).all()
        return {setting.key: setting.value for setting in settings}
    except SQLAlchemyError as e:
        logger.error(f"Error retrieving all settings from database: {e}")
        return {}


def delete_setting_from_db(db: Session, key: str) -> bool:
    """
    Delete a setting from the database.
    
    Args:
        db: Database session
        key: Setting key to delete
        
    Returns:
        True if successful, False otherwise
    """
    try:
        setting = db.query(ApplicationSettings).filter(ApplicationSettings.key == key).first()
        if setting:
            db.delete(setting)
            db.commit()
            logger.info(f"Deleted setting {key} from database")
            return True
        return False
    except SQLAlchemyError as e:
        logger.error(f"Error deleting setting {key} from database: {e}")
        db.rollback()
        return False


def get_setting_metadata(key: str) -> Dict[str, Any]:
    """
    Get metadata for a specific setting.
    
    Args:
        key: Setting key
        
    Returns:
        Dictionary containing setting metadata
    """
    return SETTING_METADATA.get(key, {
        "category": "Other",
        "description": f"Setting: {key}",
        "type": "string",
        "sensitive": False,
        "required": False,
        "restart_required": False,
    })


def get_settings_by_category() -> Dict[str, List[str]]:
    """
    Get settings organized by category.
    
    Returns:
        Dictionary mapping category names to lists of setting keys
    """
    categories = {}
    for key, metadata in SETTING_METADATA.items():
        category = metadata.get("category", "Other")
        if category not in categories:
            categories[category] = []
        categories[category].append(key)
    return categories


def validate_setting_value(key: str, value: str) -> tuple[bool, Optional[str]]:
    """
    Validate a setting value based on its metadata.
    
    Args:
        key: Setting key
        value: Setting value to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    metadata = get_setting_metadata(key)
    setting_type = metadata.get("type", "string")
    
    # Check required fields
    if metadata.get("required", False) and not value:
        return False, f"{key} is required"
    
    # Type-specific validation
    if setting_type == "boolean":
        if value.lower() not in ["true", "false", "1", "0", "yes", "no"]:
            return False, f"{key} must be a boolean value (true/false)"
    
    elif setting_type == "integer":
        try:
            int(value)
        except ValueError:
            return False, f"{key} must be an integer"
    
    # Special validation for specific keys
    if key == "session_secret" and value and len(value) < 32:
        return False, "session_secret must be at least 32 characters"
    
    return True, None
