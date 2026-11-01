"""Distributed provider budgets shared by all Celery workers.

Budgets are deliberately opt-in (all limits default to zero).  Reservations are
atomic Redis operations and expire automatically, so a crashed worker cannot
hold a provider slot forever.  When enabled, Redis errors fail closed.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class ProviderQuotaError(RuntimeError):
    """Base class for distributed provider admission failures."""

    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))


class ProviderQuotaExceeded(ProviderQuotaError):
    """The configured RPM/TPM/page/concurrency budget is currently full."""


class ProviderRateLimited(ProviderQuotaError):
    """The upstream returned a rate-limit response; retry after its hint."""


class ProviderQuotaUnavailable(ProviderQuotaError):
    """The limiter could not reach Redis while limits were enabled."""


@dataclass(frozen=True)
class ProviderLease:
    token: str
    key_prefix: str
    ttl: int


_redis_client: redis.Redis | None = None
_RESERVE_SCRIPT = """
local now = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local rpm = tonumber(ARGV[3])
local tpm = tonumber(ARGV[4])
local pages = tonumber(ARGV[5])
local concurrency = tonumber(ARGV[6])
local limits = {rpm, tpm, pages, concurrency}
local amounts = {1, tonumber(ARGV[7]), tonumber(ARGV[8]), 1}
for i=1,4 do
  if limits[i] > 0 then
    local current = tonumber(redis.call('GET', KEYS[i]) or '0')
    if current + amounts[i] > limits[i] then return 0 end
  end
end
for i=1,4 do
  if limits[i] > 0 then
    redis.call('INCRBY', KEYS[i], amounts[i])
    redis.call('EXPIRE', KEYS[i], ttl)
  end
end
redis.call('SET', KEYS[5], ARGV[9], 'EX', ttl, 'NX')
return 1
"""
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[5]) ~= ARGV[1] then return 0 end
for i=1,4 do
  local amount = tonumber(ARGV[i])
  if amount > 0 then redis.call('DECRBY', KEYS[i], amount) end
end
redis.call('DEL', KEYS[5])
return 1
"""


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    _redis_client.ping()
    return _redis_client


def _fingerprint(value: str | None) -> str:
    return hashlib.sha256((value or "shared").encode("utf-8")).hexdigest()[:16]


def _limits() -> tuple[int, int, int, int]:
    return (
        max(0, int(getattr(settings, "provider_limits_rpm", 0))),
        max(0, int(getattr(settings, "provider_limits_tpm", 0))),
        max(0, int(getattr(settings, "provider_limits_pages_per_minute", 0))),
        max(0, int(getattr(settings, "provider_limits_concurrency", 0))),
    )


def limits_enabled() -> bool:
    return bool(getattr(settings, "provider_limits_enabled", False)) and any(_limits())


def acquire(provider: str, model: str, *, credential: str | None = None, tokens: int = 0, pages: int = 0) -> ProviderLease | None:
    """Atomically reserve provider capacity, or raise a retryable error."""
    if not limits_enabled():
        return None
    rpm, tpm, page_limit, concurrency = _limits()
    ttl = max(10, int(getattr(settings, "provider_limits_lease_seconds", 300)))
    prefix = f"docuelevate:provider:{provider}:{model}:{_fingerprint(credential)}"
    token = secrets.token_urlsafe(18)
    keys = [f"{prefix}:rpm", f"{prefix}:tpm", f"{prefix}:pages", f"{prefix}:concurrency", f"{prefix}:lease:{token}"]
    try:
        ok = _client().eval(_RESERVE_SCRIPT, len(keys), *keys, int(time.time()), ttl, rpm, tpm, page_limit, concurrency, max(0, int(tokens)), max(0, int(pages)), token)
    except Exception as exc:  # fail closed while configured
        raise ProviderQuotaUnavailable("Provider limiter unavailable; retrying later", 30) from exc
    if not ok:
        raise ProviderQuotaExceeded(f"Provider budget exhausted for {provider}/{model}", 30)
    return ProviderLease(token, prefix, ttl)


def release(lease: ProviderLease | None, *, tokens: int = 0, pages: int = 0) -> None:
    if lease is None:
        return
    rpm, tpm, page_limit, concurrency = _limits()
    keys = [f"{lease.key_prefix}:rpm", f"{lease.key_prefix}:tpm", f"{lease.key_prefix}:pages", f"{lease.key_prefix}:concurrency", f"{lease.key_prefix}:lease:{lease.token}"]
    try:
        _client().eval(
            _RELEASE_SCRIPT,
            len(keys),
            *keys,
            lease.token,
            1 if rpm else 0,
            max(0, int(tokens)) if tpm else 0,
            max(0, int(pages)) if page_limit else 0,
            1 if concurrency else 0,
        )
    except Exception:
        logger.warning("Provider lease release failed; it will expire automatically", exc_info=True)


def retry_after_from_exception(exc: BaseException, default: float = 30.0) -> float:
    """Extract a provider Retry-After value without depending on SDK types."""
    response = getattr(exc, "response", None)
    headers: Any = getattr(response, "headers", None) or getattr(exc, "headers", None)
    if headers:
        value = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return max(1.0, float(value))
        except (TypeError, ValueError):
            pass
    return default

