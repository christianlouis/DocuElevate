#!/usr/bin/env python3
"""
Provider status package
"""

from app.utils.config_validator.providers.auth_providers import get_auth_provider_status
from app.utils.config_validator.providers.ai_providers import get_ai_providers_status
from app.utils.config_validator.providers.notification_providers import get_notification_provider_status
from app.utils.config_validator.providers.storage_providers import get_storage_providers_status

__all__ = ['get_provider_status']

def get_provider_status():
    """
    Returns status information for all configured providers
    """
    providers = {}
    
    # Add Authentication configuration
    providers["Authentication"] = get_auth_provider_status()
    
    # Add Notification configuration - Make sure this provider is near the top of the list
    providers["Notifications"] = get_notification_provider_status()
    
    # Add AI services
    ai_providers = get_ai_providers_status()
    providers.update(ai_providers)
    
    # Add storage providers (alphabetically ordered)
    storage_providers = get_storage_providers_status()
    providers.update(storage_providers)
    
    return providers
