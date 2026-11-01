from types import SimpleNamespace

import pytest

from app.utils import provider_limits


class _Redis:
    def __init__(self, result=1):
        self.result = result
        self.calls = []

    def ping(self):
        return True

    def eval(self, *args):
        self.calls.append(args)
        return self.result


def test_provider_budget_reservation_is_atomic_and_releases(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(provider_limits, "settings", SimpleNamespace(
        provider_limits_enabled=True,
        provider_limits_rpm=2,
        provider_limits_tpm=100,
        provider_limits_pages_per_minute=10,
        provider_limits_concurrency=1,
        provider_limits_lease_seconds=30,
        redis_url="redis://unused",
    ))
    monkeypatch.setattr(provider_limits, "_redis_client", fake)

    lease = provider_limits.acquire("openai", "model", credential="secret", tokens=12, pages=2)
    assert lease is not None
    assert fake.calls[-1][0] == provider_limits._RESERVE_SCRIPT
    assert "secret" not in repr(fake.calls[-1])
    provider_limits.release(lease, tokens=12, pages=2)
    assert fake.calls[-1][0] == provider_limits._RELEASE_SCRIPT


def test_budget_denial_is_retryable(monkeypatch):
    monkeypatch.setattr(provider_limits, "settings", SimpleNamespace(
        provider_limits_enabled=True,
        provider_limits_rpm=1,
        provider_limits_tpm=0,
        provider_limits_pages_per_minute=0,
        provider_limits_concurrency=0,
        provider_limits_lease_seconds=30,
        redis_url="redis://unused",
    ))
    monkeypatch.setattr(provider_limits, "_redis_client", _Redis(result=0))
    with pytest.raises(provider_limits.ProviderQuotaExceeded) as caught:
        provider_limits.acquire("openai", "model")
    assert caught.value.retry_after >= 1


def test_redis_failure_fails_closed_when_enabled(monkeypatch):
    monkeypatch.setattr(provider_limits, "settings", SimpleNamespace(
        provider_limits_enabled=True,
        provider_limits_rpm=1,
        provider_limits_tpm=0,
        provider_limits_pages_per_minute=0,
        provider_limits_concurrency=0,
        provider_limits_lease_seconds=30,
        redis_url="redis://unused",
    ))

    class Broken:
        def ping(self):
            raise OSError("offline")

    monkeypatch.setattr(provider_limits, "_redis_client", Broken())
    with pytest.raises(provider_limits.ProviderQuotaUnavailable):
        provider_limits.acquire("openai", "model")
