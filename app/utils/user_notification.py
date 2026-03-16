"""Per-user notification dispatch service.

Handles user-centric events (document.processed, document.failed) by:
1. Always creating an InAppNotification record
2. Sending via configured email/webhook targets (UserNotificationTarget)
   if the user has enabled that channel/event combination.
"""

import json
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.database import SessionLocal
from app.models import InAppNotification, UserNotificationPreference, UserNotificationTarget

logger = logging.getLogger(__name__)

# Supported user-centric event types
EVENT_DOCUMENT_PROCESSED = "document.processed"
EVENT_DOCUMENT_FAILED = "document.failed"

USER_EVENT_LABELS: dict[str, str] = {
    EVENT_DOCUMENT_PROCESSED: "Document Processed",
    EVENT_DOCUMENT_FAILED: "Document Processing Failed",
}


def create_in_app_notification(
    owner_id: str,
    event_type: str,
    title: str,
    message: str,
    file_id: int | None = None,
) -> InAppNotification | None:
    """Persist an InAppNotification record for the given user.

    Returns:
        The created InAppNotification, or None on error.
    """
    db = SessionLocal()
    try:
        notif = InAppNotification(
            owner_id=owner_id,
            event_type=event_type,
            title=title,
            message=message,
            file_id=file_id,
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif
    except Exception:
        db.rollback()
        logger.exception("Failed to create in-app notification for owner_id=%s", owner_id)
        return None
    finally:
        db.close()


def _send_email_notification(target_config: dict[str, Any], title: str, message: str) -> bool:
    """Send an email notification via the configured SMTP target.

    Args:
        target_config: dict with keys: smtp_host, smtp_port, smtp_username,
                       smtp_password, smtp_use_tls, recipient_email
        title: Email subject
        message: Email body text

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    try:
        smtp_host = target_config.get("smtp_host", "")
        smtp_port = int(target_config.get("smtp_port", 587))
        smtp_username = target_config.get("smtp_username", "")
        smtp_password = target_config.get("smtp_password", "")
        smtp_use_tls = bool(target_config.get("smtp_use_tls", True))
        recipient_email = target_config.get("recipient_email", "")
        sender_email = target_config.get("sender_email") or smtp_username or "noreply@docuelevate.local"

        if not smtp_host or not recipient_email:
            logger.warning("Email notification target missing smtp_host or recipient_email")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = sender_email
        msg["To"] = recipient_email
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            if smtp_use_tls:
                server.starttls()
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(msg)

        logger.info("Email notification sent to %s", recipient_email)
        return True
    except Exception:
        logger.exception("Failed to send email notification")
        return False


def _send_webhook_notification(target_config: dict[str, Any], event_type: str, title: str, message: str) -> bool:
    """Send a webhook POST notification to the configured URL.

    Args:
        target_config: dict with keys: url, secret (optional HMAC header value)
        event_type: The event type string
        title: Notification title
        message: Notification body

    Returns:
        True if the webhook was delivered successfully, False otherwise.
    """
    try:
        url = target_config.get("url", "")
        secret = target_config.get("secret", "")

        if not url:
            logger.warning("Webhook notification target missing url")
            return False

        payload = {
            "event": event_type,
            "title": title,
            "message": message,
        }
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-DocuElevate-Secret"] = secret

        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        logger.info("Webhook notification sent to %s (status %s)", url, response.status_code)
        return True
    except Exception:
        logger.exception("Failed to send webhook notification to %s", target_config.get("url", ""))
        return False


def dispatch_user_notification(
    owner_id: str,
    event_type: str,
    title: str,
    message: str,
    file_id: int | None = None,
) -> None:
    """Dispatch a user notification for the given event.

    Always creates an in-app notification. Also sends via email/webhook
    targets if the user has configured and enabled them for this event.

    Args:
        owner_id: The user's stable identifier.
        event_type: e.g. "document.processed" or "document.failed"
        title: Short notification title.
        message: Longer notification body.
        file_id: Optional FileRecord.id to link.
    """
    # 1. Always create an in-app notification
    create_in_app_notification(
        owner_id=owner_id,
        event_type=event_type,
        title=title,
        message=message,
        file_id=file_id,
    )

    # 2. Check for configured email/webhook preferences
    db = SessionLocal()
    try:
        prefs = (
            db.query(UserNotificationPreference)
            .filter(
                UserNotificationPreference.owner_id == owner_id,
                UserNotificationPreference.event_type == event_type,
                UserNotificationPreference.is_enabled == True,  # noqa: E712
                UserNotificationPreference.channel_type.in_(["email", "webhook"]),
            )
            .all()
        )

        for pref in prefs:
            if not pref.target_id:
                continue
            target = db.get(UserNotificationTarget, pref.target_id)
            if not target or not target.is_active:
                continue
            config: dict[str, Any] = {}
            if target.config:
                try:
                    config = json.loads(target.config)
                except (json.JSONDecodeError, ValueError):
                    config = {}

            if pref.channel_type == "email":
                _send_email_notification(config, title, message)
            elif pref.channel_type == "webhook":
                _send_webhook_notification(config, event_type, title, message)
    except Exception:
        logger.exception("Error dispatching user notification for owner_id=%s event=%s", owner_id, event_type)
    finally:
        db.close()

    # 3. Send push notifications to registered mobile devices
    try:
        from app.utils.push_notification import send_push_to_owner

        send_push_to_owner(
            owner_id=owner_id,
            title=title,
            body=message,
            data={"event_type": event_type, "file_id": file_id},
        )
    except Exception:
        logger.exception("Error sending push notification for owner_id=%s event=%s", owner_id, event_type)


def notify_user_document_processed(owner_id: str, filename: str, file_id: int | None = None) -> None:
    """Notify a user that their document was successfully processed."""
    dispatch_user_notification(
        owner_id=owner_id,
        event_type=EVENT_DOCUMENT_PROCESSED,
        title=f"Document processed: {filename}",
        message=f"Your document '{filename}' has been successfully processed and uploaded.",
        file_id=file_id,
    )


def notify_user_document_failed(owner_id: str, filename: str, error: str, file_id: int | None = None) -> None:
    """Notify a user that their document processing failed."""
    dispatch_user_notification(
        owner_id=owner_id,
        event_type=EVENT_DOCUMENT_FAILED,
        title=f"Document processing failed: {filename}",
        message=f"Processing of '{filename}' failed: {error}",
        file_id=file_id,
    )
