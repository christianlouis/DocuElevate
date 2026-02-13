"""
Diagnostic API endpoints
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user, require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/diagnostic/settings")
@require_login
async def diagnostic_settings(request: Request, current_user: CurrentUser):
    """
    API endpoint to dump settings to the log and view basic config information
    This endpoint doesn't expose sensitive information like passwords or tokens
    """
    from app.utils.config_validator import dump_all_settings

    # Dump full settings to log for admin to see
    dump_all_settings()

    # Return safe subset of settings for API response
    safe_settings = {
        "workdir": settings.workdir,
        "external_hostname": settings.external_hostname,
        "configured_services": {
            "email": bool(getattr(settings, "email_host", None)),
            "s3": bool(getattr(settings, "s3_bucket_name", None)),
            "dropbox": bool(getattr(settings, "dropbox_refresh_token", None)),
            "onedrive": bool(getattr(settings, "onedrive_refresh_token", None)),
            "nextcloud": bool(getattr(settings, "nextcloud_upload_url", None)),
            "sftp": bool(getattr(settings, "sftp_host", None)),
            "paperless": bool(getattr(settings, "paperless_host", None)),
            "google_drive": bool(getattr(settings, "google_drive_credentials_json", None)),
            "uptime_kuma": bool(getattr(settings, "uptime_kuma_url", None)),
            "auth": bool(getattr(settings, "authentik_config_url", None)),
            "openai": bool(getattr(settings, "openai_api_key", None)),
            "azure": bool(getattr(settings, "azure_api_key", None) and getattr(settings, "azure_endpoint", None)),
        },
        "imap_enabled": bool(getattr(settings, "imap1_host", None) or getattr(settings, "imap2_host", None)),
    }

    return {
        "status": "success",
        "settings": safe_settings,
        "message": "Full settings have been dumped to application logs",
    }


@router.post("/diagnostic/test-notification")
@require_login
async def test_notification(request: Request):
    # Add request_time to request.state
    import datetime

    request.state.request_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
    """
    Send a test notification through all configured notification channels
    """
    from app.utils.notification import send_notification

    try:
        notification_urls = getattr(settings, "notification_urls", [])
        if not notification_urls:
            return {
                "status": "warning",
                "message": "No notification services configured. Add notification URLs to your configuration.",
            }

        # Send a test notification
        hostname = settings.external_hostname or "Document Processor"
        result = send_notification(
            title=f"Test Notification from {hostname}",
            message=(
                f"This is a test notification sent at {request.state.request_time}. "
                "If you're receiving this, notifications are working!"
            ),
            notification_type="success",
            tags=["test", "notification", "diagnostic"],
        )

        if result:
            logger.info("Test notification sent successfully")
            return {
                "status": "success",
                "message": f"Test notification sent successfully to {len(notification_urls)} service(s)",
                "services_count": len(notification_urls),
            }
        else:
            logger.warning("Test notification send attempt returned False")
            return {
                "status": "error",
                "message": "Failed to send test notification. Check application logs for details.",
            }

    except Exception as e:
        logger.exception(f"Error sending test notification: {e}")
        return {"status": "error", "message": f"Error sending notification: {str(e)}"}
