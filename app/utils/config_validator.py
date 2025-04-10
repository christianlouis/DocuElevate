#!/usr/bin/env python3
"""
Configuration validation for the application.
This file serves as a backward-compatible interface to the config_validator package.
"""

# Import and re-export all functions from the new package
from app.utils.config_validator.validators import validate_email_config, validate_storage_configs, check_all_configs
from app.utils.config_validator.masking import mask_sensitive_value
from app.utils.config_validator.providers import get_provider_status
from app.utils.config_validator.settings_display import get_settings_for_display, dump_all_settings

__all__ = [
    'validate_email_config',
    'validate_storage_configs',
    'mask_sensitive_value',
    'get_provider_status',
    'get_settings_for_display',
    'dump_all_settings',
    'check_all_configs'
]

