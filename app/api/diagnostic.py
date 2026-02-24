"""
Diagnostic API endpoints
"""

import logging

from fastapi import APIRouter, Request

from app.auth import require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


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
