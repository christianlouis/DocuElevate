import logging
from typing import Any, Dict, List, Optional

import apprise

from app.config import settings

logger = logging.getLogger(__name__)

# Global Apprise instance
_apprise = None


def init_apprise() -> apprise.Apprise:
    """Initialize the Apprise instance with configured notification services"""
    global _apprise

    if _apprise is None:
        _apprise = apprise.Apprise()

        # Add all configured notification services
        if settings.notification_urls:
            for url in settings.notification_urls:
                try:
                    _apprise.add(url)
                    logger.info(f"Added notification service: {_mask_sensitive_url(url)}")
                except Exception as e:
                    logger.error(f"Failed to add notification service: {str(e)}")
        else:
            logger.warning("No notification services configured")

    return _apprise


def _mask_sensitive_url(url: str) -> str:
    """Mask sensitive parts of notification URLs for logging"""
    # Simple masking for common URL formats with credentials
    import re

    # Match patterns like user:pass@host or token in URL parameters
    masked = re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)
    masked = re.sub(r"(discord://)[^/]+/[^/]+", r"\1webhook_id/****", masked)
    masked = re.sub(r"(tgram://)[^/]+/[^/]+", r"\1bot_token/****", masked)
    masked = re.sub(r"([?&](token|key|api_key|password|secret)=)([^&]+)", r"\1****", masked)
    return masked


_NOTIFY_TYPE_MAP = {
    "success": "SUCCESS",
    "warning": "WARNING",
    "warn": "WARNING",
    "failure": "FAILURE",
    "error": "FAILURE",
    "failed": "FAILURE",
}


def _resolve_notify_type(notification_type: str):
    """Map a human-friendly notification type string to an apprise NotifyType."""
    mapped = _NOTIFY_TYPE_MAP.get(notification_type)
    if mapped:
        return getattr(apprise.NotifyType, mapped)
    return apprise.NotifyType.INFO


def send_notification(
    title: str,
    message: str,
    notification_type: str = "info",
    tags: Optional[List[str]] = None,
    attachments: Optional[List[str]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Send a notification through all configured channels

    Args:
        title: The notification title
        message: The notification body message
        notification_type: Type of notification (info, success, warning, failure)
        tags: Optional list of tags for filtering notifications
        attachments: Optional list of file paths to attach
        data: Optional additional data for the notification

    Returns:
        bool: True if notification was sent successfully to at least one service
    """
    if not settings.notification_urls:
        logger.debug(f"Notification not sent (no services configured): {title}")
        return False

    try:
        apprise_obj = init_apprise()

        notify_type = _resolve_notify_type(notification_type)

        # Send the notification to each service individually for better error reporting
        if not apprise_obj.servers:  # Access servers as an attribute, not a method
            logger.warning("No notification servers available despite having URLs configured")
            return False

        total_services = len(apprise_obj.servers)
        successful_services = 0

        for server in apprise_obj.servers:  # Iterate through the list directly
            try:
                service_name = str(server).split("://")[0] if "://" in str(server) else str(server)
                service_result = server.notify(title=title, body=message, notify_type=notify_type, attach=attachments)

                if service_result:
                    successful_services += 1
                    logger.debug(f"Notification sent via {service_name}")
                else:
                    logger.warning(f"Failed to send notification via {service_name}")
            except Exception as e:
                logger.error(f"Error sending notification via {str(server)}: {str(e)}")

        overall_result = successful_services > 0

        if overall_result:
            logger.debug(f"Notification sent: '{title}' (successful: {successful_services}/{total_services})")
        else:
            logger.warning(f"Failed to send notification to ALL services: '{title}' (0/{total_services})")

        return overall_result

    except Exception as e:
        logger.exception(f"Error sending notification: {e}")
        return False


def notify_celery_failure(task_name: str, task_id: str, exc: Exception, args: list, kwargs: dict) -> bool:
    """Send a notification about a failed Celery task"""
    if not settings.notify_on_task_failure:
        return False

    title = f"Task Failed: {task_name}"
    message = f"""
Task {task_name} ({task_id}) failed with error:
{type(exc).__name__}: {str(exc)}

Arguments: {args}
Keyword arguments: {kwargs}
"""
    return send_notification(
        title=title, message=message, notification_type="failure", tags=["celery", "failure", task_name]
    )


def notify_credential_failure(service_name: str, error: str) -> bool:
    """Send a notification about a credential failure"""
    if not settings.notify_on_credential_failure:
        return False

    title = f"Credential Failure: {service_name}"
    message = f"""
The credentials for {service_name} have failed:
{error}

Please check and update the credentials in the system settings.
"""
    return send_notification(
        title=title, message=message, notification_type="warning", tags=["credentials", "warning", service_name]
    )


def notify_startup() -> bool:
    """Send a notification that the application has started"""
    if not settings.notify_on_startup:
        return False

    title = "DocuElevate Started"
    message = f"DocuElevate has been started successfully on {settings.external_hostname}"
    return send_notification(title=title, message=message, notification_type="success", tags=["system", "startup"])


def notify_shutdown() -> bool:
    """Send a notification that the application is shutting down"""
    if not settings.notify_on_shutdown:
        return False

    title = "DocuElevate Shutting Down"
    message = f"DocuElevate on {settings.external_hostname} is shutting down"
    return send_notification(title=title, message=message, notification_type="info", tags=["system", "shutdown"])


def notify_file_processed(filename: str, file_size: int, metadata: dict, destinations: list) -> bool:
    """Send a notification that a file has been successfully processed"""
    if not settings.notify_on_file_processed:
        return False

    # Format file size for display
    size_mb = file_size / (1024 * 1024)
    size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

    # Extract key metadata fields
    doc_type = metadata.get("document_type", "Unknown")
    tags = metadata.get("tags", [])
    tags_str = ", ".join(tags) if tags else "None"

    # Format destinations
    destinations_str = ", ".join(destinations) if destinations else "None configured"

    title = f"File Processed: {filename}"
    message = f"""
File: {filename}
Size: {size_str}
Document Type: {doc_type}
Tags: {tags_str}
Destinations: {destinations_str}

The file has been successfully processed and is being uploaded to all configured destinations.
"""

    return send_notification(
        title=title, message=message.strip(), notification_type="success", tags=["document", "processed", "success"]
    )
