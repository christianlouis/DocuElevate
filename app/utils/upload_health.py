"""Small Redis-backed freshness markers for the bulk-upload control plane."""

from __future__ import annotations

from datetime import datetime, timezone

import redis

from app.config import settings

HEARTBEAT_TTL = 30
SCHEDULER_KEY = "docuelevate:upload-health:scheduler"
DISPATCHER_KEY = "docuelevate:upload-health:dispatcher"
RECONCILER_KEY = "docuelevate:upload-health:reconciler"


def _client() -> redis.Redis:
    # Health markers are operational state, not broker traffic.  Keep them on
    # the established REDIS_URL so a non-Redis broker (for example AMQP) does
    # not make upload health unknowable.
    return redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)


def mark_fresh(key: str, client: redis.Redis | None = None) -> None:
    try:
        (client or _client()).set(key, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL)
    except Exception:
        # Freshness is observability only; never prevent durable work from running.
        return


def freshness(key: str, client: redis.Redis | None = None) -> str:
    try:
        value = (client or _client()).get(key)
    except Exception:
        return "unknown"
    if not value:
        return "stalled"
    try:
        if isinstance(value, bytes):
            value = value.decode("ascii")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(value)).total_seconds()
    except (TypeError, ValueError, UnicodeDecodeError):
        return "unknown"
    return "healthy" if 0 <= age <= HEARTBEAT_TTL else "stalled"
