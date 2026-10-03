"""Short-lived server-side transactions for the OneDrive OAuth wizard."""

import json
import logging
from typing import Any

import redis

from app.config import settings
from app.utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

_KEY_PREFIX = "docuelevate:onedrive-oauth:"
_TTL_SECONDS = 600
_CONSUME_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then redis.call('DEL', KEYS[1]) end
return value
"""


class OneDriveOAuthTransactionUnavailable(RuntimeError):
    """Raised when a transaction cannot be safely stored or consumed."""


def _client() -> redis.Redis:
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        raise OneDriveOAuthTransactionUnavailable("OneDrive OAuth transaction storage is unavailable") from exc


def store_pending_onedrive_oauth(state: str, transaction: dict[str, Any]) -> None:
    """Encrypt and store a single OAuth transaction outside the browser/session."""
    encrypted = encrypt_value(json.dumps(transaction))
    if not encrypted or not encrypted.startswith("enc:"):
        raise OneDriveOAuthTransactionUnavailable("OneDrive OAuth transaction encryption is unavailable")
    try:
        stored = _client().set(f"{_KEY_PREFIX}{state}", encrypted, ex=_TTL_SECONDS, nx=True)
    except OneDriveOAuthTransactionUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OneDriveOAuthTransactionUnavailable("OneDrive OAuth transaction storage is unavailable") from exc
    if not stored:
        raise OneDriveOAuthTransactionUnavailable("Could not create OneDrive OAuth transaction")


def consume_pending_onedrive_oauth(state: str) -> dict[str, Any] | None:
    """Atomically return and remove a transaction so OAuth state is single-use."""
    try:
        encrypted = _client().eval(_CONSUME_SCRIPT, 1, f"{_KEY_PREFIX}{state}")
    except OneDriveOAuthTransactionUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OneDriveOAuthTransactionUnavailable("OneDrive OAuth transaction storage is unavailable") from exc
    if not encrypted:
        return None
    try:
        decoded = decrypt_value(encrypted)
        transaction = json.loads(decoded or "")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Discarding invalid OneDrive OAuth transaction")
        raise OneDriveOAuthTransactionUnavailable("OneDrive OAuth transaction is invalid") from exc
    return transaction if isinstance(transaction, dict) else None
