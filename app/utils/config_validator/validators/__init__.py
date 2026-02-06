#!/usr/bin/env python3
"""
Configuration validators package
"""

import logging
from app.config import settings
from app.utils.config_validator.validators.email_validators import validate_email_config
from app.utils.config_validator.validators.auth_validators import validate_auth_config
from app.utils.config_validator.validators.storage_validators import validate_storage_configs
from app.utils.config_validator.validators.notification_validators import validate_notification_config

logger = logging.getLogger(__name__)

__all__ = [
    'validate_email_config',
    'validate_auth_config',
    'validate_storage_configs',
    'validate_notification_config',
    'check_all_configs'
]

def check_all_configs():
    """Run all configuration validations and log results"""
    from app.utils.config_validator.settings_display import dump_all_settings
    
    logger.info("Validating application configuration...")
    
    # Check if debug is enabled and dump all settings if it is
    if hasattr(settings, 'debug') and settings.debug:
        dump_all_settings()
    
    # Check auth config
    auth_issues = validate_auth_config()
    if auth_issues:
        logger.warning(f"Authentication configuration issues: {', '.join(auth_issues)}")
    else:
        logger.info("Authentication configuration OK")
    
    # Check email config
    email_issues = validate_email_config()
    if email_issues:
        logger.warning(f"Email configuration issues: {', '.join(email_issues)}")
    else:
        logger.info("Email configuration OK")
    
    # Check storage configs
    storage_issues = validate_storage_configs()
    for provider, issues in storage_issues.items():
        if issues:
            logger.warning(f"{provider.capitalize()} configuration issues: {', '.join(issues)}")
        else:
            logger.info(f"{provider.capitalize()} configuration OK")
    
    # Check notification configuration
    notification_issues = validate_notification_config()
    if notification_issues:
        logger.warning(f"Notification configuration issues: {', '.join(notification_issues)}")
    else:
        logger.info("Notification configuration OK")
    
    # Return all identified issues
    return {
        'auth': auth_issues,
        'email': email_issues,
        'storage': storage_issues,
        'notification': notification_issues
    }
