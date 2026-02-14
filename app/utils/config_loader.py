"""
Configuration loader that supports database-persisted settings with precedence.

This module provides functionality to:
- Load settings from database after app initialization
- Apply database settings over environment variables
- Dynamically reload settings when changed
"""

import logging
from typing import Any, Optional, Union

from sqlalchemy.orm import Session

from app.models import ApplicationSettings

logger = logging.getLogger(__name__)


def load_settings_from_db(settings_obj: object, db_session: Session) -> None:
    """
    Load settings from database and apply them to the settings object.

    Database settings take precedence over environment variables and defaults.
    This function should be called after database initialization.

    Args:
        settings_obj: The Settings instance to update
        db_session: Database session to use for loading settings
    """
    try:
        db_settings = db_session.query(ApplicationSettings).all()

        if not db_settings:
            logger.info("No database settings found, using environment/defaults")
            return

        # Apply database settings to the settings object
        updated_count = 0
        for db_setting in db_settings:
            key = db_setting.key
            value = db_setting.value

            # Check if the setting exists in the Settings class
            if hasattr(settings_obj, key):
                # Get the field info to determine the type
                field_info = settings_obj.__fields__.get(key)
                if field_info:
                    # Convert value to the appropriate type
                    converted_value = convert_setting_value(value, field_info.annotation)

                    # Set the attribute
                    setattr(settings_obj, key, converted_value)
                    updated_count += 1
                    logger.debug(f"Applied database setting: {key}")

        if updated_count > 0:
            logger.info(f"Loaded {updated_count} settings from database")
        else:
            logger.info("No applicable database settings found")

    except Exception as e:
        logger.error(f"Error loading settings from database: {e}")
        # Don't fail application startup if database settings can't be loaded
        logger.warning("Continuing with environment/default settings")


def convert_setting_value(value: Optional[str], field_type: Any) -> Any:
    """
    Convert a string value from database to the appropriate type.

    Args:
        value: String value from database
        field_type: Target type from Pydantic field annotation

    Returns:
        Converted value in the appropriate type
    """
    if value is None:
        return None

    # Handle Optional types
    origin = getattr(field_type, "__origin__", None)
    if origin is Union:
        # Get the non-None type from Union (for Optional)
        args = getattr(field_type, "__args__", ())
        field_type = next((arg for arg in args if arg is not type(None)), str)

    # Convert based on type
    if field_type is bool:
        return value.lower() in ("true", "1", "yes", "y", "t")
    elif field_type is int:
        try:
            return int(value)
        except ValueError:
            logger.warning(f"Failed to convert '{value}' to int, returning 0")
            return 0
    elif field_type is float:
        try:
            return float(value)
        except ValueError:
            logger.warning(f"Failed to convert '{value}' to float, returning 0.0")
            return 0.0
    elif field_type is list or getattr(field_type, "__origin__", None) is list:
        # Handle list types - assume comma-separated values
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
    else:
        # Default to string
        return str(value)


def reload_settings_from_db(settings_obj: object) -> bool:
    """
    Reload settings from database.

    This is useful after settings have been updated through the UI.
    Note: Some settings require application restart to take effect.

    Args:
        settings_obj: The Settings instance to update

    Returns:
        True if reload was successful, False otherwise
    """
    try:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            load_settings_from_db(settings_obj, db)
            logger.info("Settings reloaded from database")
            return True
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error reloading settings from database: {e}")
        return False
