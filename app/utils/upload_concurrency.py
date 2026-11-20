"""Distributed admission control for external upload destinations."""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class UploadDestinationCapacityError(RuntimeError):
    """A destination cannot accept another upload yet."""

    retry_after = 30.0


@dataclass(frozen=True)
class UploadDestinationLease:
    key: str
    token: str


_redis_client: redis.Redis | None = None
_ACQUIRE_SCRIPT = """
local now = redis.call('TIME')
local now_seconds = tonumber(now[1]) + tonumber(now[2]) / 1000000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_seconds)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now_seconds + tonumber(ARGV[2]), ARGV[3])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]) + 60)
return 1
"""
_RELEASE_SCRIPT = "redis.call('ZREM', KEYS[1], ARGV[1]); return 1"


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.effective_celery_broker_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    _redis_client.ping()
    return _redis_client


def _key(destination: str) -> str:
    fingerprint = hashlib.sha256(destination.encode(), usedforsecurity=False).hexdigest()[:24]
    return f"docuelevate:upload-destination:{fingerprint}:leases"


def acquire(destination: str) -> UploadDestinationLease | None:
    """Acquire one slot, or fail closed when Redis admission is unavailable."""
    limit = int(getattr(settings, "upload_destination_concurrency", 0))
    if limit <= 0:
        return None
    lease_seconds = max(1200, int(getattr(settings, "upload_destination_lease_seconds", 1200)))
    key = _key(destination)
    token = secrets.token_urlsafe(18)
    try:
        accepted = _client().eval(_ACQUIRE_SCRIPT, 1, key, limit, lease_seconds, token)
    except Exception as exc:
        raise UploadDestinationCapacityError("Upload destination admission unavailable; retrying later") from exc
    if not accepted:
        raise UploadDestinationCapacityError("Upload destination concurrency limit reached; retrying later")
    return UploadDestinationLease(key=key, token=token)


def release(lease: UploadDestinationLease | None) -> None:
    if lease is None:
        return
    try:
        _client().eval(_RELEASE_SCRIPT, 1, lease.key, lease.token)
    except Exception:
        logger.warning("Upload destination lease release failed; it will expire automatically", exc_info=True)
