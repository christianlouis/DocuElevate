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
            "label_key": "setup.database_url_label",
            "description": "Database connection string (e.g., sqlite:///./app/database.db)",
            "description_key": "setup.database_url_description",
            "type": "string",
            "sensitive": False,
            "default": "sqlite:///./app/database.db",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
            "wizard_category_key": "setup.category_infrastructure",
            "bootstrap": True,
            "required": True,
            "bootstrap_reason": "Required before DocuElevate can open the settings database; configure DATABASE_URL in the deployment secret.",
            "bootstrap_reason_key": "setup.database_url_bootstrap_reason",
        },
        {
            "key": "redis_url",
            "label": "Redis URL",
            "label_key": "setup.redis_url_label",
            "description": "Redis connection for task queue (e.g., redis://localhost:6379/0)",
            "description_key": "setup.redis_url_description",
            "type": "string",
            "sensitive": False,
            "default": "redis://localhost:6379/0",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
            "wizard_category_key": "setup.category_infrastructure",
        },
        {
            "key": "workdir",
            "label": "Working Directory",
            "label_key": "setup.workdir_label",
            "description": "Directory for temporary file storage and processing",
            "description_key": "setup.workdir_description",
            "type": "string",
            "sensitive": False,
            "default": "/workdir",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
            "wizard_category_key": "setup.category_infrastructure",
        },
        {
            "key": "gotenberg_url",
            "label": "Gotenberg URL",
            "label_key": "setup.gotenberg_url_label",
            "description": "Gotenberg service URL for document conversion",
            "description_key": "setup.gotenberg_url_description",
            "type": "string",
            "sensitive": False,
            "default": "http://gotenberg:3000",
            "wizard_step": 1,
            "wizard_category": "Core Infrastructure",
            "wizard_category_key": "setup.category_infrastructure",
        },
        {
            "key": "session_secret",
            "label": "Session Secret",
            "label_key": "setup.session_secret_label",
            "description": "Secret key for session encryption (min 32 characters, auto-generate recommended)",
            "description_key": "setup.session_secret_description",
            "type": "string",
            "sensitive": True,
            "default": None,  # Should be generated
            "wizard_step": 2,
            "wizard_category": "Security",
            "wizard_category_key": "setup.category_security",
            "bootstrap": True,
            "required": True,
            "bootstrap_reason": "Must remain stable across restarts to decrypt database-stored credentials; configure SESSION_SECRET in the deployment secret.",
            "bootstrap_reason_key": "setup.session_secret_bootstrap_reason",
        },
        {
            "key": "admin_username",
            "label": "Admin Username",
            "label_key": "setup.admin_username_label",
            "description": "Username for the admin account",
            "description_key": "setup.admin_username_description",
            "type": "string",
            "sensitive": False,
            "default": "admin",
            "wizard_step": 2,
            "wizard_category": "Security",
            "wizard_category_key": "setup.category_security",
        },
        {
            "key": "admin_password",
            "label": "Admin Password",
            "label_key": "setup.admin_password_label",
            "description": "Password for the admin account",
            "description_key": "setup.admin_password_description",
            "type": "string",
            "sensitive": True,
            "default": None,  # Must be set
            "required": True,
            "wizard_step": 2,
            "wizard_category": "Security",
            "wizard_category_key": "setup.category_security",
        },
        {
            "key": "ai_provider",
            "label": "AI Provider",
            "label_key": "setup.ai_provider_label",
            "description": "AI provider for metadata extraction and OCR refinement (openai, azure, anthropic, gemini, ollama, openrouter, portkey, litellm)",
            "description_key": "setup.ai_provider_description",
            "type": "string",
            "sensitive": False,
            "default": "openai",
            "options": ["openai", "azure", "anthropic", "gemini", "ollama", "openrouter", "portkey", "litellm"],
            "wizard_step": 3,
            "wizard_category": "AI Services",
            "wizard_category_key": "setup.category_ai",
        },
        {
            "key": "openai_api_key",
            "label": "API Key (OpenAI / Azure / LiteLLM)",
            "label_key": "setup.ai_api_key_label",
            "description": "Optional API key for OpenAI, Azure OpenAI, or LiteLLM; leave blank to configure AI later",
            "description_key": "setup.ai_api_key_description",
            "type": "string",
            "sensitive": True,
            "default": None,
            "required": False,
            "wizard_step": 3,
            "wizard_category": "AI Services",
            "wizard_category_key": "setup.category_ai",
        },
        {
            "key": "openai_model",
            "label": "Default Model",
            "label_key": "setup.ai_model_label",
            "description": "Model name used when AI_MODEL is not set (e.g. gpt-4o-mini, claude-3-5-sonnet-20241022, llama3.2)",
            "description_key": "setup.ai_model_description",
            "type": "string",
            "sensitive": False,
            "default": "gpt-4o-mini",
            "wizard_step": 3,
            "wizard_category": "AI Services",
            "wizard_category_key": "setup.category_ai",
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
        # Never expose an installation whose security state could not be
        # determined. The setup boundary must fail closed.
        return True


def get_missing_required_settings() -> List[str]:
    """
    Get list of required settings that are missing or have placeholder values.

    Returns:
        List of setting keys that need to be configured
    """
    missing = []

    for required_setting in get_required_settings():
        if required_setting.get("required") is False:
            continue

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
