#!/usr/bin/env python3
"""
Authentication provider status module
"""

from app.config import settings
from app.utils.config_validator.masking import mask_sensitive_value

def get_auth_provider_status():
    """Returns authentication provider status"""
    auth_enabled = getattr(settings, 'auth_enabled', False)
    using_oidc = bool(getattr(settings, 'authentik_client_id', None) and 
                     getattr(settings, 'authentik_client_secret', None) and
                     getattr(settings, 'authentik_config_url', None))
    
    auth_method = "OIDC" if using_oidc else "Basic Auth" if auth_enabled else "None"
    
    return {
        "name": "Authentication", 
        "icon": "fa-solid fa-lock",
        "configured": bool(auth_enabled and 
                         (getattr(settings, 'admin_username', None) or 
                          using_oidc)),
        "enabled": auth_enabled,
        "description": "Access control and user authentication",
        "details": {
            "method": auth_method,
            "provider_name": getattr(settings, 'oauth_provider_name', 'Not set') if using_oidc else "N/A",
            "session_security": "Configured" if getattr(settings, 'session_secret', None) else "Not configured"
        }
    }
