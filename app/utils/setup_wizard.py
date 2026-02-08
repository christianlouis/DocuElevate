"""
Setup wizard utilities for first-time system configuration.

Detects if the system needs initial setup and provides required settings list.
"""

import logging
from typing import Any, Dict, List

from app.config import settings

logger = logging.getLogger(__name__)


def get_required_settings() -> List[Dict[str, Any]]:
    """
    Get list of settings that are absolutely required for the system to operate.

    Returns:
        List of required setting definitions with metadata
    """
    return [
        {
            "key": "database_url",
            "label": "Database URL",
            "description": "Database connection string (e.g., sqlite:///./app/database.db)",
            "type": "string",
            "sensitive": False,
            "default": "sqlite:///./app/database.db",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
        },
        {
            "key": "redis_url",
            "label": "Redis URL",
            "description": "Redis connection for task queue (e.g., redis://localhost:6379/0)",
            "type": "string",
            "sensitive": False,
            "default": "redis://localhost:6379/0",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
        },
        {
            "key": "workdir",
            "label": "Working Directory",
            "description": "Directory for temporary file storage and processing",
            "type": "string",
            "sensitive": False,
            "default": "/workdir",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
        },
        {
            "key": "gotenberg_url",
            "label": "Gotenberg URL",
            "description": "Gotenberg service URL for document conversion",
            "type": "string",
            "sensitive": False,
            "default": "http://gotenberg:3000",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
        },
        {
            "key": "session_secret",
            "label": "Session Secret",
            "description": "Secret key for session encryption (min 32 characters, auto-generate recommended)",
            "type": "string",
            "sensitive": True,
            "default": None,  # Should be generated
            "wizard_step": 2,
            "wizard_category": "Security",
        },
        {
            "key": "admin_username",
            "label": "Admin Username",
            "description": "Username for the admin account",
            "type": "string",
            "sensitive": False,
            "default": "admin",
            "wizard_step": 2,
            "wizard_category": "Security",
        },
        {
            "key": "admin_password",
            "label": "Admin Password",
            "description": "Password for the admin account",
            "type": "string",
            "sensitive": True,
            "default": None,  # Must be set
            "wizard_step": 2,
            "wizard_category": "Security",
        },
        {
            "key": "openai_api_key",
            "label": "OpenAI API Key",
            "description": "API key for OpenAI services (metadata extraction)",
            "type": "string",
            "sensitive": True,
            "default": None,
            "wizard_step": 3,
            "wizard_category": "AI Services",
        },
        {
            "key": "azure_ai_key",
            "label": "Azure AI Key",
            "description": "Azure AI key for document intelligence (OCR)",
            "type": "string",
            "sensitive": True,
            "default": None,
            "wizard_step": 3,
            "wizard_category": "AI Services",
        },
        {
            "key": "azure_region",
            "label": "Azure Region",
            "description": "Azure region for AI services (e.g., eastus)",
            "type": "string",
            "sensitive": False,
            "default": "eastus",
            "wizard_step": 3,
            "wizard_category": "AI Services",
        },
        {
            "key": "azure_endpoint",
            "label": "Azure Endpoint",
            "description": "Azure AI endpoint URL",
            "type": "string",
            "sensitive": False,
            "default": None,
            "wizard_step": 3,
            "wizard_category": "AI Services",
        },
    ]


def is_setup_required() -> bool:
    """
    Check if the system requires initial setup.

    Returns True if any critical required settings are missing or have placeholder values.

    Returns:
        True if setup wizard should be shown, False otherwise
    """
    try:
        # Critical settings that must be configured
        critical_settings = [
            ("session_secret", ["INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"]),
            ("admin_password", [None, "", "your_secure_password", "changeme", "admin"]),
            ("openai_api_key", [None, "", "<OPENAI_API_KEY>", "test-key"]),
            ("azure_ai_key", [None, "", "<AZURE_AI_KEY>", "test-key"]),
        ]

        for setting_key, invalid_values in critical_settings:
            value = getattr(settings, setting_key, None)
            if value in invalid_values:
                logger.warning(f"Setup required: {setting_key} has placeholder or missing value")
                return True

        # All critical settings are configured
        return False

    except Exception as e:
        logger.error(f"Error checking if setup required: {e}")
        # If we can't check, assume setup is not required (fail open)
        return False


def get_missing_required_settings() -> List[str]:
    """
    Get list of required settings that are missing or have placeholder values.

    Returns:
        List of setting keys that need to be configured
    """
    missing = []

    for required_setting in get_required_settings():
        key = required_setting["key"]
        value = getattr(settings, key, None)

        # Check if value is missing or is a placeholder
        placeholder_values = [
            None,
            "",
            f"<{key.upper()}>",
            "test-key",
            "your_secure_password",
            "changeme",
            "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS",
        ]

        if value in placeholder_values:
            missing.append(key)

    return missing


def get_wizard_steps() -> Dict[int, List[Dict[str, Any]]]:
    """
    Get setup wizard steps organized by step number.

    Returns:
        Dictionary mapping step number to list of settings in that step
    """
    steps = {}

    for setting in get_required_settings():
        step_num = setting.get("wizard_step", 1)
        if step_num not in steps:
            steps[step_num] = []
        steps[step_num].append(setting)

    return steps
