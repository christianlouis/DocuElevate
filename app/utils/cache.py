"""
Lightweight Redis caching layer for frequently accessed data.

Provides a thin wrapper around Redis GET/SET with JSON serialization and
configurable TTLs.  All operations are **fail-open**: if Redis is
unavailable the caller simply gets a cache miss and falls back to the
database or other source of truth.

Usage::

    from app.utils.cache import cache_get, cache_set, cache_delete

    # Try cache first
    value = cache_get("my_key")
    if value is None:
        value = expensive_query()
        cache_set("my_key", value, ttl=300)
"""

import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)

#: Prefix applied to all cache keys to avoid collisions with other Redis users.
_KEY_PREFIX = "docuelevate:cache:"

#: Module-level Redis client – lazily initialised on first use.
_redis_client: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    """Return a shared Redis client, or *None* if Redis is unreachable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        from app.config import settings

        _redis_client = redis.from_url(settings.redis_url, socket_connect_timeout=2, decode_responses=True)
        # Quick connectivity check
        _redis_client.ping()
        return _redis_client
    except Exception as exc:
        logger.debug(f"Redis cache unavailable: {exc}")
        _redis_client = None
        return None


def cache_get(key: str) -> Any | None:
    """
    Retrieve a cached value by *key*.

    Returns the deserialised Python object, or ``None`` on cache miss or
    Redis error.
    """
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(f"{_KEY_PREFIX}{key}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug(f"Cache get failed for {key}: {exc}")
        return None


def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """
    Store *value* under *key* with a time-to-live of *ttl* seconds.

    Silently ignores errors so callers are never blocked by cache issues.
    """
    client = _get_redis()
    if client is None:
        return
    try:
        client.setex(f"{_KEY_PREFIX}{key}", ttl, json.dumps(value))
    except Exception as exc:
        logger.debug(f"Cache set failed for {key}: {exc}")


def cache_delete(key: str) -> None:
    """
    Remove *key* from the cache.

    Silently ignores errors.
    """
    client = _get_redis()
    if client is None:
        return
    try:
        client.delete(f"{_KEY_PREFIX}{key}")
    except Exception as exc:
        logger.debug(f"Cache delete failed for {key}: {exc}")


def cache_delete_pattern(pattern: str) -> None:
    """
    Remove all keys matching *pattern* (glob-style) from the cache.

    Silently ignores errors.
    """
    client = _get_redis()
    if client is None:
        return
    try:
        full_pattern = f"{_KEY_PREFIX}{pattern}"
        cursor = 0
        while True:
            cursor, keys = client.scan(cursor, match=full_pattern, count=100)  # type: ignore[misc]  # sync Redis returns tuple
            if keys:
                client.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        logger.debug(f"Cache delete pattern failed for {pattern}: {exc}")
