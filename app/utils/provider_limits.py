"""Atomic distributed upstream budgets shared by all workers."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class ProviderQuotaError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 60.0) -> None:
        super().__init__(message)
        self.retry_after = max(1.0, float(retry_after))


class ProviderQuotaExceeded(ProviderQuotaError):
    """A configured rolling-window or concurrency budget is full."""


class ProviderRateLimited(ProviderQuotaError):
    """The upstream returned a rate-limit response."""


class ProviderQuotaUnavailable(ProviderQuotaError):
    """Redis admission control is unavailable while limits are enabled."""


@dataclass(frozen=True)
class ProviderLease:
    token: str
    key_prefix: str
    ttl: int


_redis_client: redis.Redis | None = None
_RESERVE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local expiry = now - 60
local cooldown = redis.call('TTL', KEYS[5])
if cooldown > 0 then return -cooldown end
local lease_until = now + tonumber(ARGV[2])
local rpm = tonumber(ARGV[3]); local tpm = tonumber(ARGV[4]); local pages = tonumber(ARGV[5]); local concurrency = tonumber(ARGV[6])
local token_amount = tonumber(ARGV[7]); local page_amount = tonumber(ARGV[8]); local token = ARGV[9]
for i=2,3 do
  local amounts = KEYS[i+4]
  for _, member in ipairs(redis.call('ZRANGEBYSCORE', KEYS[i], '-inf', expiry)) do
    redis.call('HDEL', amounts, member)
  end
end
for i=1,3 do redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', expiry) end
redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', now)
local function total(key, amount_key)
  local sum = 0
  for _, member in ipairs(redis.call('ZRANGE', key, 0, -1)) do sum = sum + tonumber(redis.call('HGET', amount_key, member) or '0') end
  return sum
end
if rpm > 0 and redis.call('ZCARD', KEYS[1]) + 1 > rpm then return 0 end
if tpm > 0 and total(KEYS[2], KEYS[6]) + token_amount > tpm then return 0 end
if pages > 0 and total(KEYS[3], KEYS[7]) + page_amount > pages then return 0 end
if concurrency > 0 and redis.call('ZCARD', KEYS[4]) + 1 > concurrency then return 0 end
redis.call('ZADD', KEYS[1], now, token); redis.call('ZADD', KEYS[2], now, token); redis.call('ZADD', KEYS[3], now, token); redis.call('ZADD', KEYS[4], lease_until, token)
redis.call('HSET', KEYS[6], token, token_amount); redis.call('HSET', KEYS[7], token, page_amount)
for _, i in ipairs({1,2,3,4,6,7}) do redis.call('EXPIRE', KEYS[i], tonumber(ARGV[10])) end
return 1
"""
_COOLDOWN_SCRIPT = """
local remaining = redis.call('TTL', KEYS[1])
if remaining < tonumber(ARGV[1]) then redis.call('SET', KEYS[1], '1', 'EX', ARGV[1]) end
return 1
"""
_RELEASE_SCRIPT = """redis.call('ZREM', KEYS[1], ARGV[1]); return 1"""


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    _redis_client.ping()
    return _redis_client


def _fingerprint(value: str | None) -> str:
    # This is a bounded, non-secret Redis key suffix, not password hashing.
    return hashlib.sha256((value or "shared").encode(), usedforsecurity=False).hexdigest()[:16]


def _limits(provider: str, model: str) -> tuple[int, int, int, int]:
    values: dict[str, Any] = {
        "rpm": getattr(settings, "provider_limits_rpm", 0),
        "tpm": getattr(settings, "provider_limits_tpm", 0),
        "pages_per_minute": getattr(settings, "provider_limits_pages_per_minute", 0),
        "concurrency": getattr(settings, "provider_limits_concurrency", 0),
    }
    raw = getattr(settings, "provider_limits_overrides", "")
    if raw:
        try:
            overrides = json.loads(raw) if isinstance(raw, str) else raw
            scope = overrides.get(f"{provider}/{model}") or overrides.get(provider) or {}
            if isinstance(scope, dict):
                values.update(scope)
        except (TypeError, ValueError, AttributeError):
            logger.warning("Invalid PROVIDER_LIMITS_OVERRIDES; using global limits")
    return tuple(max(0, int(values[name])) for name in ("rpm", "tpm", "pages_per_minute", "concurrency"))  # type: ignore[return-value]


def limits_enabled(provider: str | None = None, model: str | None = None) -> bool:
    return bool(getattr(settings, "provider_limits_enabled", False)) and any(
        _limits(provider or "default", model or "default")
    )


def acquire(
    provider: str, model: str, *, credential: str | None = None, tokens: int = 0, pages: int = 0
) -> ProviderLease | None:
    if not limits_enabled(provider, model):
        return None
    rpm, tpm, page_limit, concurrency = _limits(provider, model)
    ttl = max(10, int(getattr(settings, "provider_limits_lease_seconds", 300)))
    key_ttl = max(125, ttl + 5)
    prefix = f"docuelevate:provider:{provider}:{model}:{_fingerprint(credential)}"
    token = secrets.token_urlsafe(18)
    keys = [
        f"{prefix}:rpm",
        f"{prefix}:tpm",
        f"{prefix}:pages",
        f"{prefix}:concurrency",
        f"{prefix}:cooldown",
        f"{prefix}:token_amounts",
        f"{prefix}:page_amounts",
    ]
    try:
        client = _client()
        ok = client.eval(
            _RESERVE_SCRIPT,
            len(keys),
            *keys,
            0,  # Admission uses the shared Redis clock.
            ttl,
            rpm,
            tpm,
            page_limit,
            concurrency,
            max(0, int(tokens)),
            max(0, int(pages)),
            token,
            key_ttl,
        )
    except ProviderQuotaError:
        raise
    except Exception as exc:
        raise ProviderQuotaUnavailable("Provider limiter unavailable; retrying later", 30) from exc
    if ok < 0:
        raise ProviderQuotaExceeded(f"Provider cooldown active for {provider}/{model}", -ok)
    if not ok:
        raise ProviderQuotaExceeded(f"Provider budget exhausted for {provider}/{model}", 30)
    return ProviderLease(token, prefix, ttl)


def release(lease: ProviderLease | None) -> None:
    if lease is None:
        return
    try:
        _client().eval(_RELEASE_SCRIPT, 1, f"{lease.key_prefix}:concurrency", lease.token)
    except Exception:
        logger.warning("Provider lease release failed; it will expire automatically", exc_info=True)


def record_cooldown(provider: str, model: str, *, credential: str | None, retry_after: float) -> None:
    if not limits_enabled(provider, model):
        return
    try:
        _client().eval(
            _COOLDOWN_SCRIPT,
            1,
            f"docuelevate:provider:{provider}:{model}:{_fingerprint(credential)}:cooldown",
            max(1, math.ceil(retry_after)),
        )
    except Exception:
        logger.warning("Could not persist provider cooldown", exc_info=True)


def retry_after_from_exception(exc: BaseException, default: float = 30.0) -> float:
    response = getattr(exc, "response", None)
    headers: Any = getattr(response, "headers", None) or getattr(exc, "headers", None)
    if headers:
        try:
            return max(1.0, float(headers.get("retry-after") or headers.get("Retry-After")))
        except (TypeError, ValueError):
            try:
                date = parsedate_to_datetime(headers.get("retry-after") or headers.get("Retry-After"))
                return max(1.0, (date - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return default
