#!/usr/bin/env python3
"""
Notification provider status module
"""

from app.config import settings


def get_notification_provider_status():
    """Returns notification provider status"""
    return {
        "name": "Notifications",
        "icon": "fa-solid fa-bell",
        "configured": bool(getattr(settings, "notification_urls", None)),
        "enabled": True,
        "description": "Send system notifications via various services",
        "details": {
            "services": (
                str(len(getattr(settings, "notification_urls", []))) + " service(s) configured"
                if getattr(settings, "notification_urls", None)
                else "Not configured"
            ),
            "task_failure": getattr(settings, "notify_on_task_failure", True),
            "credential_failure": getattr(settings, "notify_on_credential_failure", True),
            "startup": getattr(settings, "notify_on_startup", True),
            "shutdown": getattr(settings, "notify_on_shutdown", False),
        },
        "testable": True,
        "test_endpoint": "/api/diagnostic/test-notification",
    }
