"""
Tests for the Redis caching utility module.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.utils.cache import (
    _KEY_PREFIX,
    cache_delete,
    cache_delete_pattern,
    cache_get,
    cache_set,
)


@pytest.fixture(autouse=True)
def _reset_redis_client():
    """Reset the module-level Redis client between tests."""
    import app.utils.cache as cache_mod

    cache_mod._redis_client = None
    yield
    cache_mod._redis_client = None


# ---------------------------------------------------------------------------
# cache_get
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_get_returns_none_when_redis_unavailable():
    """cache_get should return None when Redis is not reachable."""
    with patch("app.utils.cache._get_redis", return_value=None):
        assert cache_get("some_key") is None


@pytest.mark.unit
def test_cache_get_returns_none_on_miss():
    """cache_get should return None when the key does not exist."""
    mock_client = MagicMock()
    mock_client.get.return_value = None
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        assert cache_get("nonexistent") is None
    mock_client.get.assert_called_once_with(f"{_KEY_PREFIX}nonexistent")


@pytest.mark.unit
def test_cache_get_returns_deserialized_value():
    """cache_get should deserialize the stored JSON string."""
    mock_client = MagicMock()
    mock_client.get.return_value = json.dumps(["application/pdf", "image/png"])
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        result = cache_get("mime_types")
    assert result == ["application/pdf", "image/png"]


@pytest.mark.unit
def test_cache_get_returns_none_on_exception():
    """cache_get should not raise when Redis throws an error."""
    mock_client = MagicMock()
    mock_client.get.side_effect = Exception("connection lost")
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        assert cache_get("key") is None


# ---------------------------------------------------------------------------
# cache_set
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_set_stores_json_with_ttl():
    """cache_set should serialise value as JSON and set with TTL."""
    mock_client = MagicMock()
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_set("my_key", {"a": 1}, ttl=60)
    mock_client.setex.assert_called_once_with(f"{_KEY_PREFIX}my_key", 60, json.dumps({"a": 1}))


@pytest.mark.unit
def test_cache_set_uses_default_ttl():
    """cache_set should default to 300 seconds TTL."""
    mock_client = MagicMock()
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_set("key", "val")
    _, args, _ = mock_client.setex.mock_calls[0]
    assert args[1] == 300


@pytest.mark.unit
def test_cache_set_noop_when_redis_unavailable():
    """cache_set should silently do nothing when Redis is down."""
    with patch("app.utils.cache._get_redis", return_value=None):
        cache_set("key", "val")  # Should not raise


@pytest.mark.unit
def test_cache_set_ignores_exception():
    """cache_set should not raise on Redis errors."""
    mock_client = MagicMock()
    mock_client.setex.side_effect = Exception("write failed")
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_set("key", "val")  # Should not raise


# ---------------------------------------------------------------------------
# cache_delete
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_delete_removes_key():
    """cache_delete should delete the prefixed key."""
    mock_client = MagicMock()
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_delete("old_key")
    mock_client.delete.assert_called_once_with(f"{_KEY_PREFIX}old_key")


@pytest.mark.unit
def test_cache_delete_noop_when_redis_unavailable():
    """cache_delete should silently do nothing when Redis is down."""
    with patch("app.utils.cache._get_redis", return_value=None):
        cache_delete("key")  # Should not raise


@pytest.mark.unit
def test_cache_delete_ignores_exception():
    """cache_delete should not raise on Redis errors."""
    mock_client = MagicMock()
    mock_client.delete.side_effect = Exception("delete failed")
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_delete("key")  # Should not raise


# ---------------------------------------------------------------------------
# cache_delete_pattern
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cache_delete_pattern_scans_and_deletes():
    """cache_delete_pattern should use SCAN to find and delete matching keys."""
    mock_client = MagicMock()
    # Simulate SCAN returning keys in one batch then cursor 0
    mock_client.scan.return_value = (0, [f"{_KEY_PREFIX}mime_types", f"{_KEY_PREFIX}mime_list"])
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_delete_pattern("mime_*")
    mock_client.scan.assert_called_once_with(0, match=f"{_KEY_PREFIX}mime_*", count=100)
    mock_client.delete.assert_called_once_with(f"{_KEY_PREFIX}mime_types", f"{_KEY_PREFIX}mime_list")


@pytest.mark.unit
def test_cache_delete_pattern_noop_when_redis_unavailable():
    """cache_delete_pattern should silently do nothing when Redis is down."""
    with patch("app.utils.cache._get_redis", return_value=None):
        cache_delete_pattern("mime_*")  # Should not raise


@pytest.mark.unit
def test_cache_delete_pattern_handles_empty_scan():
    """cache_delete_pattern should not call delete when SCAN returns no keys."""
    mock_client = MagicMock()
    mock_client.scan.return_value = (0, [])
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_delete_pattern("none_*")
    mock_client.delete.assert_not_called()


@pytest.mark.unit
def test_cache_delete_pattern_ignores_exception():
    """cache_delete_pattern should not raise on Redis errors."""
    mock_client = MagicMock()
    mock_client.scan.side_effect = Exception("scan failed")
    with patch("app.utils.cache._get_redis", return_value=mock_client):
        cache_delete_pattern("x*")  # Should not raise


# ---------------------------------------------------------------------------
# _get_redis
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_redis_returns_none_on_connection_failure():
    """_get_redis should return None when Redis connection fails."""
    import app.utils.cache as cache_mod

    with patch("app.utils.cache.redis.from_url", side_effect=Exception("refused")):
        result = cache_mod._get_redis()
    assert result is None


@pytest.mark.unit
def test_get_redis_caches_client():
    """_get_redis should reuse the cached client on subsequent calls."""
    import app.utils.cache as cache_mod

    mock_client = MagicMock()
    mock_client.ping.return_value = True

    with patch("app.utils.cache.redis.from_url", return_value=mock_client):
        first = cache_mod._get_redis()
        second = cache_mod._get_redis()

    assert first is second
    # from_url should only have been called once
    assert first is mock_client
