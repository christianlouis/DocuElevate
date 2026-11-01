"""Integration coverage for the provider limiter's real Redis Lua scripts."""

import hashlib
import os
import time
import uuid

import pytest
import redis

from app.utils import provider_limits


@pytest.fixture
def real_redis():
    url = os.getenv("PROVIDER_LIMITS_TEST_REDIS_URL", "redis://localhost:6379/15")
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except redis.RedisError as exc:
        pytest.skip(f"Redis integration server unavailable: {exc}")
    prefix = f"docuelevate:test:{uuid.uuid4().hex}"
    keys = [f"{prefix}:{suffix}" for suffix in ("rpm", "tpm", "pages", "concurrency", "cooldown", "tokens", "amounts")]
    try:
        yield client, keys
    finally:
        client.delete(*keys)


def reserve(client, keys, *, rpm=0, tpm=0, pages=0, concurrency=0, tokens=0, page_amount=0, ttl=30, token=None):
    token = token or uuid.uuid4().hex
    return token, client.eval(
        provider_limits._RESERVE_SCRIPT,
        len(keys),
        *keys,
        int(time.time()),
        ttl,
        rpm,
        tpm,
        pages,
        concurrency,
        tokens,
        page_amount,
        token,
        max(125, ttl + 5),
    )


def test_rpm_and_usage_remain_after_concurrency_release(real_redis):
    client, keys = real_redis
    token, result = reserve(client, keys, rpm=1, tpm=100, pages=10, concurrency=1, tokens=20, page_amount=2)
    assert result == 1
    client.eval(provider_limits._RELEASE_SCRIPT, 1, keys[3], token)
    _, denied = reserve(client, keys, rpm=1, tpm=100, pages=10, concurrency=1, tokens=20, page_amount=2)
    assert denied == 0


def test_concurrency_is_atomic_and_reusable_after_release(real_redis):
    client, keys = real_redis
    token, result = reserve(client, keys, concurrency=1)
    assert result == 1
    _, denied = reserve(client, keys, concurrency=1)
    assert denied == 0
    client.eval(provider_limits._RELEASE_SCRIPT, 1, keys[3], token)
    _, accepted = reserve(client, keys, concurrency=1)
    assert accepted == 1


def test_token_and_page_amounts_are_counted_in_window(real_redis):
    client, keys = real_redis
    _, first = reserve(client, keys, tpm=100, pages=3, tokens=80, page_amount=2)
    _, second = reserve(client, keys, tpm=100, pages=3, tokens=21, page_amount=1)
    assert first == 1
    assert second == 0


def test_stale_amounts_are_removed_with_expired_events(real_redis):
    client, keys = real_redis
    old = str(int(time.time()) - 61)
    token = uuid.uuid4().hex
    client.zadd(keys[1], {token: old})
    client.hset(keys[5], token, 100)
    _, result = reserve(client, keys, tpm=100, tokens=100)
    assert result == 1
    assert client.hexists(keys[5], token) is False


def test_cooldown_does_not_shorten_existing_longer_cooldown(real_redis, monkeypatch):
    client, _ = real_redis
    monkeypatch.setattr(provider_limits, "_redis_client", client)
    monkeypatch.setattr(
        provider_limits,
        "settings",
        type(
            "S",
            (),
            {
                "provider_limits_enabled": True,
                "provider_limits_rpm": 1,
                "provider_limits_tpm": 0,
                "provider_limits_pages_per_minute": 0,
                "provider_limits_concurrency": 0,
            },
        )(),
    )
    provider_limits.record_cooldown("test", "model", credential="key", retry_after=30)
    provider_limits.record_cooldown("test", "model", credential="key", retry_after=5)
    fingerprint = hashlib.sha256(b"key").hexdigest()[:16]
    assert client.ttl(f"docuelevate:provider:test:model:{fingerprint}:cooldown") > 20
