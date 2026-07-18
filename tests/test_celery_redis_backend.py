"""Tests for failover-aware Celery Redis result handling."""

from unittest.mock import MagicMock, patch

import pytest
from celery import Celery
from celery.backends.redis import RedisBackend
from redis.exceptions import ConnectionError, ReadOnlyError

from app.utils.celery_redis_backend import (
    FailoverAwareRedisBackend,
    assert_redis_backend_writable,
    is_redis_backend,
)


@pytest.mark.unit
class TestRedisWriteabilityProbe:
    def test_recognizes_supported_redis_schemes(self):
        assert is_redis_backend("redis://redis:6379/0")
        assert is_redis_backend("rediss://redis.example/0")
        assert is_redis_backend("unix:///run/redis.sock")
        assert not is_redis_backend("db+postgresql://database/results")

    @patch("app.utils.celery_redis_backend.redis.Redis.from_url")
    def test_primary_requires_successful_write_round_trip(self, mock_from_url):
        client = mock_from_url.return_value
        client.role.return_value = [b"master", 0, []]
        client.set.return_value = True

        assert_redis_backend_writable("redis://primary:6379/0")

        client.set.assert_called_once()
        client.delete.assert_called_once()
        client.connection_pool.disconnect.assert_called_once()

    @patch("app.utils.celery_redis_backend.redis.Redis.from_url")
    def test_replica_is_rejected_without_a_write(self, mock_from_url):
        client = mock_from_url.return_value
        client.role.return_value = [b"slave", "primary", 6379, "connected", 0]

        with pytest.raises(RuntimeError, match="read-only replica"):
            assert_redis_backend_writable("redis://replica:6379/0")

        client.set.assert_not_called()
        client.connection_pool.disconnect.assert_called_once()

    @patch("app.utils.celery_redis_backend.redis.Redis.from_url")
    def test_connection_failure_is_reported_without_endpoint_details(self, mock_from_url):
        client = mock_from_url.return_value
        client.role.side_effect = ConnectionError("secret-hostname:6379 refused")

        with pytest.raises(RuntimeError, match="unavailable or not writable") as exc_info:
            assert_redis_backend_writable("redis://user:secret@secret-hostname:6379/0")

        assert "secret" not in str(exc_info.value)


@pytest.mark.unit
class TestFailoverAwareBackend:
    def _backend_without_init(self):
        backend = object.__new__(FailoverAwareRedisBackend)
        backend.__dict__["client"] = MagicMock()
        return backend

    def test_read_only_error_is_retryable(self):
        backend = self._backend_without_init()

        assert backend.exception_safe_to_retry(ReadOnlyError("READONLY")) is True

    def test_store_result_reconnects_and_retries_after_demotion(self):
        app = Celery("redis-failover-test")
        app.conf.update(
            result_backend_always_retry=True,
            result_backend_max_retries=2,
            result_backend_base_sleep_between_retries_ms=1,
            result_backend_max_sleep_between_retries_ms=1,
        )
        backend = FailoverAwareRedisBackend(app=app, url="redis://unused:6379/0")
        backend.__dict__["client"] = MagicMock()
        backend._store_result = MagicMock(side_effect=[ReadOnlyError("READONLY"), None])
        backend._sleep = MagicMock()

        result = backend.store_result("task-1", {"ok": True}, "SUCCESS")

        assert result == {"ok": True}
        assert backend._store_result.call_count == 2
        backend.client.connection_pool.disconnect.assert_called_once()

    @patch.object(RedisBackend, "on_backend_retryable_error")
    def test_retry_disconnects_cached_connection_pool(self, mock_super):
        backend = self._backend_without_init()
        error = ReadOnlyError("READONLY")

        backend.on_backend_retryable_error(error)

        backend.client.connection_pool.disconnect.assert_called_once()
        mock_super.assert_called_once_with(error)
