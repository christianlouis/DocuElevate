"""Per-user, health-aware upload rate limiter for DocuElevate.

This module provides a FastAPI dependency that enforces per-user upload rate
limits using a Redis-backed sliding window counter.  The effective limit is
dynamically reduced when the system is under heavy load (high Celery queue
depth or elevated CPU load average), ensuring the server remains responsive
to all users even during bulk-upload scenarios.

Usage in an endpoint::

    from app.middleware.upload_rate_limit import require_upload_rate_limit

    @router.post("/ui-upload")
    @require_login
    async def ui_upload(
        request: Request,
        _rate_ok: None = Depends(require_upload_rate_limit),
        ...
    ):
        ...

See ``docs/ConfigurationGuide.md`` for the configuration options
(``UPLOAD_RATE_LIMIT_PER_USER``, ``UPLOAD_RATE_LIMIT_WINDOW``).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import redis
from fastapi import HTTPException, Request, status

from app.config import settings
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis key prefix
# ---------------------------------------------------------------------------
_KEY_PREFIX = "docuelevate:upload_rate"

# ---------------------------------------------------------------------------
# Health-check queue names (Celery defaults used by DocuElevate)
# ---------------------------------------------------------------------------
_CELERY_QUEUES = ("document_processor", "default", "celery")

# ---------------------------------------------------------------------------
# Singleton Redis client (lazy-initialised; fail-open when unavailable)
# ---------------------------------------------------------------------------
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    """Return a shared Redis client, or *None* when Redis is unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Quick connectivity check – raises on failure.
        _redis_client.ping()
        return _redis_client
    except Exception:  # noqa: BLE001
        logger.debug("Redis unavailable for upload rate limiter – falling back to allow-all")
        _redis_client = None
        return None


# ---------------------------------------------------------------------------
# Health metrics helpers
# ---------------------------------------------------------------------------


def _get_queue_depth(r: redis.Redis) -> int:
    """Return the total number of pending tasks across all Celery queues."""
    total = 0
    for queue_name in _CELERY_QUEUES:
        try:
            total += r.llen(queue_name)
        except Exception:  # noqa: BLE001, S110
            logger.debug("Could not read queue length for '%s'", queue_name)
    return total


def _get_cpu_load_ratio() -> float:
    """Return the 1-minute load average divided by the number of CPU cores.

    Returns ``0.0`` on platforms that do not support :func:`os.getloadavg`
    (e.g. Windows) so that the limiter never penalises on those systems.
    """
    try:
        load_1m = os.getloadavg()[0]
        cpu_count = os.cpu_count() or 1
        return load_1m / cpu_count
    except (OSError, AttributeError):
        return 0.0


def compute_effective_limit(
    base_limit: int,
    queue_depth: int = 0,
    cpu_load_ratio: float = 0.0,
) -> tuple[int, float, str]:
    """Compute the effective upload rate limit based on system health.

    The function applies a *reduction factor* (``0.0 < factor ≤ 1.0``) to the
    configured base limit.  Both queue depth and CPU load contribute
    independently; the lowest factor wins.

    Args:
        base_limit: The configured maximum uploads per window.
        queue_depth: Total pending tasks in Celery queues.
        cpu_load_ratio: 1-minute load average divided by CPU count.

    Returns:
        A 3-tuple of ``(effective_limit, factor, reason)`` where *reason*
        is a human-readable tag for logging.
    """
    factor = 1.0
    reason = "normal"

    # --- Queue-depth thresholds ---
    if queue_depth > 200:
        factor, reason = min(factor, 0.10), f"critical_queue({queue_depth})"
    elif queue_depth > 100:
        factor, reason = min(factor, 0.25), f"high_queue({queue_depth})"
    elif queue_depth > 50:
        factor, reason = min(factor, 0.50), f"moderate_queue({queue_depth})"

    # --- CPU-load thresholds ---
    if cpu_load_ratio > 3.0:
        new_factor = 0.10
        if new_factor < factor:
            factor, reason = new_factor, f"critical_cpu({cpu_load_ratio:.1f})"
    elif cpu_load_ratio > 2.0:
        new_factor = 0.25
        if new_factor < factor:
            factor, reason = new_factor, f"high_cpu({cpu_load_ratio:.1f})"
    elif cpu_load_ratio > 1.5:
        new_factor = 0.50
        if new_factor < factor:
            factor, reason = new_factor, f"moderate_cpu({cpu_load_ratio:.1f})"

    effective = max(1, int(base_limit * factor))
    return effective, factor, reason


# ---------------------------------------------------------------------------
# Core sliding-window check (Redis sorted set)
# ---------------------------------------------------------------------------


def _check_and_record(
    r: redis.Redis,
    user_id: str,
    window: int,
    effective_limit: int,
) -> dict[str, Any] | None:
    """Atomically check the user's upload count and record the new upload.

    Uses a Redis sorted set where each member is a unique timestamp-based ID
    and the score is the Unix timestamp.  Entries older than *window* seconds
    are pruned on every call so the set never grows unbounded.

    Returns:
        ``None`` if the request is allowed, or a ``dict`` with ``count``,
        ``limit``, and ``retry_after`` if the limit is exceeded.
    """
    key = f"{_KEY_PREFIX}:{user_id}"
    now = time.time()
    window_start = now - window

    pipe = r.pipeline(transaction=True)
    # 1. Remove entries outside the window
    pipe.zremrangebyscore(key, "-inf", window_start)
    # 2. Count current entries
    pipe.zcard(key)
    # 3. Retrieve the oldest entry's score (to compute retry_after)
    pipe.zrange(key, 0, 0, withscores=True)
    results = pipe.execute()

    current_count: int = results[1]
    oldest_entries: list = results[2]

    if current_count >= effective_limit:
        # Compute how long until the oldest entry expires from the window.
        if oldest_entries:
            oldest_score = oldest_entries[0][1]
            retry_after = max(1, int((oldest_score + window) - now))
        else:
            retry_after = max(1, window // 2)
        return {
            "count": current_count,
            "limit": effective_limit,
            "retry_after": retry_after,
        }

    # 4. Record this upload (unique member = timestamp with random suffix)
    member = f"{now}:{os.urandom(4).hex()}"
    pipe2 = r.pipeline(transaction=True)
    pipe2.zadd(key, {member: now})
    pipe2.expire(key, window + 60)  # TTL slightly longer than window
    pipe2.execute()

    return None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_upload_rate_limit(request: Request) -> None:
    """FastAPI dependency that enforces per-user upload rate limits.

    The dependency is designed to **fail open**: if Redis is unavailable the
    request is allowed through so that uploads are never blocked by a
    monitoring outage.

    Raises:
        HTTPException: 429 Too Many Requests when the per-user upload limit
            is exceeded.  The ``Retry-After`` header indicates how many
            seconds the client should wait before retrying.
    """
    r = _get_redis()
    if r is None:
        # Redis unavailable – fail open.
        return

    # Identify the user (owner_id for multi-user, IP fallback).
    user_id = get_current_owner_id(request)
    if not user_id:
        user_id = f"ip:{request.client.host}" if request.client else "ip:unknown"

    base_limit: int = settings.upload_rate_limit_per_user
    window: int = settings.upload_rate_limit_window

    # Gather health metrics and compute effective limit.
    try:
        queue_depth = _get_queue_depth(r)
    except Exception:  # noqa: BLE001
        queue_depth = 0

    cpu_load_ratio = _get_cpu_load_ratio()
    effective_limit, factor, health_reason = compute_effective_limit(base_limit, queue_depth, cpu_load_ratio)

    # Sliding-window check.
    try:
        rejection = _check_and_record(r, user_id, window, effective_limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Upload rate-limit check failed (allowing request): %s", exc)
        return

    if rejection is not None:
        retry_after = rejection["retry_after"]
        logger.warning(
            "Upload rate limit exceeded: user=%s count=%d/%d window=%ds health=%s retry_after=%ds",
            user_id,
            rejection["count"],
            rejection["limit"],
            window,
            health_reason,
            retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Upload rate limit exceeded ({rejection['count']}/{rejection['limit']} "
                f"in {window}s). Retry after {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    if factor < 1.0:
        logger.info(
            "Upload allowed with reduced limit: user=%s effective=%d/%d health=%s",
            user_id,
            effective_limit,
            base_limit,
            health_reason,
        )
