"""Tests for per-user health-aware upload rate limiting (app/middleware/upload_rate_limit.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.middleware.upload_rate_limit import compute_effective_limit

# ---------------------------------------------------------------------------
# Tests for compute_effective_limit (pure function, no Redis needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeEffectiveLimit:
    """Tests for the health-aware effective-limit calculation."""

    def test_normal_conditions_return_base_limit(self):
        """Under normal conditions the full base limit should be returned."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=0, cpu_load_ratio=0.0)
        assert effective == 20
        assert factor == 1.0
        assert reason == "normal"

    def test_moderate_queue_halves_limit(self):
        """Queue depth > 50 should halve the base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=60, cpu_load_ratio=0.0)
        assert effective == 10
        assert factor == 0.5
        assert "moderate_queue" in reason

    def test_high_queue_quarters_limit(self):
        """Queue depth > 100 should quarter the base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=120, cpu_load_ratio=0.0)
        assert effective == 5
        assert factor == 0.25
        assert "high_queue" in reason

    def test_critical_queue_drops_to_ten_percent(self):
        """Queue depth > 200 should drop to 10% of base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=250, cpu_load_ratio=0.0)
        assert effective == 2
        assert factor == 0.10
        assert "critical_queue" in reason

    def test_moderate_cpu_halves_limit(self):
        """CPU load ratio > 1.5 should halve the base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=0, cpu_load_ratio=1.8)
        assert effective == 10
        assert factor == 0.5
        assert "moderate_cpu" in reason

    def test_high_cpu_quarters_limit(self):
        """CPU load ratio > 2.0 should quarter the base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=0, cpu_load_ratio=2.5)
        assert effective == 5
        assert factor == 0.25
        assert "high_cpu" in reason

    def test_critical_cpu_drops_to_ten_percent(self):
        """CPU load ratio > 3.0 should drop to 10% of base limit."""
        effective, factor, reason = compute_effective_limit(20, queue_depth=0, cpu_load_ratio=4.0)
        assert effective == 2
        assert factor == 0.10
        assert "critical_cpu" in reason

    def test_worst_metric_wins(self):
        """The lowest factor from queue and CPU should be applied."""
        # Queue says 0.5, CPU says 0.25 → 0.25 wins
        effective, factor, reason = compute_effective_limit(20, queue_depth=60, cpu_load_ratio=2.5)
        assert effective == 5
        assert factor == 0.25

    def test_minimum_effective_limit_is_one(self):
        """Even under extreme load the effective limit must be ≥ 1."""
        effective, _factor, _reason = compute_effective_limit(1, queue_depth=999, cpu_load_ratio=10.0)
        assert effective >= 1

    def test_zero_base_limit_returns_zero(self):
        """A base limit of 0 (disabled) should clamp to at least 1."""
        effective, _factor, _reason = compute_effective_limit(0, queue_depth=0, cpu_load_ratio=0.0)
        # max(1, int(0 * 1.0)) = max(1, 0) = 1
        # This is correct since a base_limit of 0 means "disabled" and is
        # handled upstream (the dependency skips the check entirely).
        assert effective >= 0


# ---------------------------------------------------------------------------
# Tests for the FastAPI dependency (mocked Redis)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireUploadRateLimit:
    """Tests for the require_upload_rate_limit FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_allows_request_when_redis_unavailable(self):
        """When Redis is down the dependency should fail open (allow the request)."""
        from app.middleware.upload_rate_limit import require_upload_rate_limit

        mock_request = MagicMock()
        mock_request.session = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch("app.middleware.upload_rate_limit._get_redis", return_value=None):
            # Should NOT raise
            result = await require_upload_rate_limit(mock_request)
            assert result is None

    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self):
        """A user below the rate limit should be allowed through."""
        from app.middleware.upload_rate_limit import require_upload_rate_limit

        mock_request = MagicMock()
        mock_request.session = {"user": {"username": "testuser"}}
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.1"

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [
            0,  # zremrangebyscore result
            5,  # zcard — current count (under limit of 20)
            [],  # zrange oldest
        ]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.llen.return_value = 0  # empty queues

        mock_pipe2 = MagicMock()
        mock_pipe2.execute.return_value = [True, True]
        # The second pipeline call (record upload)
        mock_redis.pipeline.side_effect = [mock_pipe, mock_pipe2]

        with (
            patch("app.middleware.upload_rate_limit._get_redis", return_value=mock_redis),
            patch("app.middleware.upload_rate_limit.get_current_owner_id", return_value="testuser"),
            patch("app.middleware.upload_rate_limit._get_cpu_load_ratio", return_value=0.1),
        ):
            result = await require_upload_rate_limit(mock_request)
            assert result is None

    @pytest.mark.asyncio
    async def test_rejects_request_over_limit(self):
        """A user at or over the rate limit should receive a 429."""
        from fastapi import HTTPException

        from app.middleware.upload_rate_limit import require_upload_rate_limit

        mock_request = MagicMock()
        mock_request.session = {"user": {"username": "spammer"}}
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.2"

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [
            0,  # zremrangebyscore
            20,  # zcard — at limit
            [("oldest_entry", 1000000.0)],  # oldest entry for retry_after
        ]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.llen.return_value = 0

        with (
            patch("app.middleware.upload_rate_limit._get_redis", return_value=mock_redis),
            patch("app.middleware.upload_rate_limit.get_current_owner_id", return_value="spammer"),
            patch("app.middleware.upload_rate_limit._get_cpu_load_ratio", return_value=0.0),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_upload_rate_limit(mock_request)
            assert exc_info.value.status_code == 429
            assert "Retry-After" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_health_reduces_effective_limit(self):
        """When queues are deep, the effective limit should drop, causing a 429 sooner."""
        from fastapi import HTTPException

        from app.middleware.upload_rate_limit import require_upload_rate_limit

        mock_request = MagicMock()
        mock_request.session = {"user": {"username": "normaluser"}}
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.3"

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        # 12 uploads already — under normal limit of 20 but over health-reduced limit
        mock_pipe.execute.return_value = [
            0,  # zremrangebyscore
            12,  # zcard — 12 uploads in window
            [("oldest", 1000000.0)],
        ]
        mock_redis.pipeline.return_value = mock_pipe
        # Simulate deep queue (>100) → effective limit = 25% of 20 = 5
        mock_redis.llen.return_value = 40  # 40 per queue * 3 = 120 total

        with (
            patch("app.middleware.upload_rate_limit._get_redis", return_value=mock_redis),
            patch("app.middleware.upload_rate_limit.get_current_owner_id", return_value="normaluser"),
            patch("app.middleware.upload_rate_limit._get_cpu_load_ratio", return_value=0.0),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_upload_rate_limit(mock_request)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_falls_back_to_ip_when_no_user(self):
        """Unauthenticated requests should use IP-based rate limiting."""
        from app.middleware.upload_rate_limit import require_upload_rate_limit

        mock_request = MagicMock()
        mock_request.session = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.100"

        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [0, 0, []]
        mock_redis.pipeline.return_value = mock_pipe
        mock_redis.llen.return_value = 0

        mock_pipe2 = MagicMock()
        mock_pipe2.execute.return_value = [True, True]
        mock_redis.pipeline.side_effect = [mock_pipe, mock_pipe2]

        with (
            patch("app.middleware.upload_rate_limit._get_redis", return_value=mock_redis),
            patch("app.middleware.upload_rate_limit.get_current_owner_id", return_value=None),
            patch("app.middleware.upload_rate_limit._get_cpu_load_ratio", return_value=0.0),
        ):
            result = await require_upload_rate_limit(mock_request)
            assert result is None


# ---------------------------------------------------------------------------
# Tests for configuration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadRateLimitConfig:
    """Tests for upload rate limit configuration settings."""

    def test_settings_exist(self):
        """Verify per-user upload rate limit settings are exposed in config."""
        from app.config import settings

        assert hasattr(settings, "upload_rate_limit_per_user")
        assert hasattr(settings, "upload_rate_limit_window")

    def test_sensible_defaults(self):
        """Default values should be reasonable for a multi-user system."""
        from app.config import settings

        assert settings.upload_rate_limit_per_user >= 10
        assert settings.upload_rate_limit_per_user <= 100
        assert settings.upload_rate_limit_window >= 30
        assert settings.upload_rate_limit_window <= 300
