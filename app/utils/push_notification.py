"""Push notification sender for the DocuElevate mobile app.

Uses the **Expo Push Notification** service to deliver notifications to both
iOS (via APNs) and Android (via FCM) without requiring server-side APNs keys
or FCM credentials.  The mobile app obtains an ``ExponentPushToken[…]`` at
startup and registers it with the backend via the mobile API.

Reference: https://docs.expo.dev/push-notifications/sending-notifications/
"""

import logging
from typing import Any

import httpx

from app.database import SessionLocal
from app.models import MobileDevice

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Maximum tokens per batch request (Expo limit).
_EXPO_BATCH_LIMIT = 100


def send_expo_push_notification(
    tokens: list[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    sound: str = "default",
    badge: int | None = None,
) -> list[dict[str, Any]]:
    """Send a push notification to one or more Expo push tokens.

    Args:
        tokens: List of Expo push tokens (``ExponentPushToken[…]``).
        title: Notification title shown in the system tray.
        body: Notification body text.
        data: Optional JSON-serialisable dict attached to the notification
              (available in the app via ``notification.request.content.data``).
        sound: Notification sound.  Use ``"default"`` or ``None`` for silent.
        badge: iOS badge count.  Pass ``0`` to clear.

    Returns:
        List of Expo push receipt dicts (one per token).
    """
    if not tokens:
        return []

    results: list[dict[str, Any]] = []

    # Send in batches to stay within Expo's per-request limit.
    for i in range(0, len(tokens), _EXPO_BATCH_LIMIT):
        batch = tokens[i : i + _EXPO_BATCH_LIMIT]
        messages = []
        for token in batch:
            msg: dict[str, Any] = {
                "to": token,
                "title": title,
                "body": body,
                "sound": sound,
            }
            if data:
                msg["data"] = data
            if badge is not None:
                msg["badge"] = badge
            messages.append(msg)

        try:
            resp = httpx.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()
            batch_results = payload.get("data", [])
            results.extend(batch_results)
            logger.debug("Expo push batch sent: %d tokens, %d results", len(batch), len(batch_results))
        except httpx.HTTPStatusError as exc:
            logger.error("Expo push HTTP error: %s – %s", exc.response.status_code, exc.response.text)
        except Exception:
            logger.exception("Expo push notification failed for batch starting at index %d", i)

    return results


def send_push_to_owner(
    owner_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> None:
    """Look up all active push tokens for *owner_id* and send them a notification.

    This function is safe to call from Celery task workers.  Database errors
    and push failures are logged but never raised so that the caller task is
    not retried due to a notification failure.
    """
    db = SessionLocal()
    try:
        devices = (
            db.query(MobileDevice)
            .filter(
                MobileDevice.owner_id == owner_id,
                MobileDevice.is_active.is_(True),
                MobileDevice.push_token.isnot(None),
            )
            .all()
        )
        tokens = [d.push_token for d in devices if d.push_token]
    except Exception:
        logger.exception("Failed to query mobile devices for owner_id=%s", owner_id)
        return
    finally:
        db.close()

    if not tokens:
        logger.debug("No active push tokens for owner_id=%s", owner_id)
        return

    logger.info("Sending push notification to %d device(s) for owner_id=%s", len(tokens), owner_id)
    send_expo_push_notification(tokens=tokens, title=title, body=body, data=data)
