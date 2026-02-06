#!/usr/bin/env python3
"""
Notification configuration validators
"""

import logging
from app.config import settings

logger = logging.getLogger(__name__)

def validate_notification_config():
    """Check notification configuration"""
    issues = []
    
    # Check if any notification URLs are configured
    if not getattr(settings, 'notification_urls', None):
        issues.append("No notification URLs configured")
    else:
        try:
            # Try initializing Apprise to validate URLs
            import apprise
            a = apprise.Apprise()
            
            for url in settings.notification_urls:
                try:
                    if not a.add(url):
                        issues.append(f"Invalid notification URL format: {url}")
                except Exception as e:
                    issues.append(f"Error with notification URL: {str(e)}")
                    
        except ImportError:
            issues.append("Apprise module not installed")
    
    if not issues:
        logger.info("Notification configuration valid")
    else:
        logger.warning(f"Notification configuration issues: {', '.join(issues)}")
        
    return issues
