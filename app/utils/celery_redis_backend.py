"""Failover-aware Redis result backend helpers for Celery workers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import redis
from celery import Celery
from celery.backends.redis import RedisBackend
from redis.exceptions import ReadOnlyError

logger = logging.getLogger(__name__)

_REDIS_SCHEMES = ("redis://", "rediss://", "unix://")


def is_redis_backend(url: str | None) -> bool:
    """Return whether *url* points at a Redis-compatible Celery backend."""
    return bool(url and url.lower().startswith(_REDIS_SCHEMES))


def assert_redis_backend_writable(url: str, *, timeout_seconds: float = 2.0) -> None:
    """Fail unless *url* resolves to a writable Redis primary.

    ``PING`` alone is not enough: a replica responds successfully but rejects
    Celery's task-result writes.  The probe therefore checks ``ROLE`` and then
    performs a short-lived write/delete round trip before a worker may consume
    work.
    """
    client = redis.Redis.from_url(
        url,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
    )
    probe_key = f"docuelevate:worker-preflight:{uuid.uuid4()}"
    wrote_probe = False
    try:
        role_response = client.role()
        role = role_response[0] if role_response else None
        if isinstance(role, bytes):
            role = role.decode("ascii", errors="replace")
        if str(role).lower() != "master":
            raise RuntimeError("Redis result backend resolved to a read-only replica")

        wrote_probe = bool(client.set(probe_key, "1", ex=10, nx=True))
        if not wrote_probe:
            raise RuntimeError("Redis result backend rejected the worker write probe")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Redis result backend is unavailable or not writable") from exc
    finally:
        if wrote_probe:
            try:
                client.delete(probe_key)
            except Exception:
                logger.warning("Could not remove Redis worker preflight key", exc_info=True)
        client.connection_pool.disconnect()


class FailoverAwareRedisBackend(RedisBackend):
    """Redis result backend that reconnects after primary demotion.

    Celery does not consider ``ReadOnlyError`` retryable by default.  With a
    TCP load balancer, an existing connection can remain attached to the old
    primary after Redis promotes another node.  Treating the error as
    retryable and disconnecting the pool forces the retry through the current
    writable-primary route.
    """

    def __init__(
        self,
        *args: Any,
        url: str | None = None,
        app: Celery | None = None,
        **kwargs: Any,
    ) -> None:
        effective_url = url or (app.conf.result_backend if app is not None else None)
        super().__init__(*args, url=effective_url, app=app, **kwargs)

    def exception_safe_to_retry(self, exc: Exception) -> bool:
        return isinstance(exc, ReadOnlyError) or super().exception_safe_to_retry(exc)

    def on_backend_retryable_error(self, exc: Exception) -> None:
        if isinstance(exc, ReadOnlyError):
            logger.warning("Redis result backend was demoted to read-only; reconnecting to the writable primary")
        try:
            self.client.connection_pool.disconnect()
        except Exception:
            logger.warning("Could not reset the Redis result-backend connection pool", exc_info=True)
        super().on_backend_retryable_error(exc)
