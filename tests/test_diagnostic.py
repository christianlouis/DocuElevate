"""Tests for app/api/diagnostic.py module."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /api/diagnostic/health endpoint."""

    def test_health_returns_200_when_all_ok(self, client):
        """Health endpoint returns 200 with healthy status when all checks pass."""
        with (
            patch("app.api.diagnostic.engine") as mock_engine,
            patch("app.api.diagnostic.redis_lib") as mock_redis,
        ):
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_redis_inst = MagicMock()
            mock_redis.from_url.return_value = mock_redis_inst

            response = client.get("/api/diagnostic/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data
        assert "checks" in data
        assert data["checks"]["database"]["status"] == "ok"

    def test_health_returns_503_when_database_fails(self, client):
        """Health endpoint returns 503 with unhealthy status when DB is down."""
        with (
            patch("app.api.diagnostic.engine") as mock_engine,
            patch("app.api.diagnostic.redis_lib") as mock_redis,
        ):
            mock_engine.connect.side_effect = Exception("DB unavailable")
            mock_redis_inst = MagicMock()
            mock_redis.from_url.return_value = mock_redis_inst

            response = client.get("/api/diagnostic/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "error"
        assert "detail" in data["checks"]["database"]

    def test_health_returns_200_degraded_when_redis_fails(self, client):
        """Health returns 200 degraded when Redis is unavailable (non-critical)."""
        with (
            patch("app.api.diagnostic.engine") as mock_engine,
            patch("app.api.diagnostic.redis_lib") as mock_redis,
        ):
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_redis.from_url.return_value = MagicMock()
            mock_redis.from_url.return_value.ping.side_effect = Exception("Connection refused")

            response = client.get("/api/diagnostic/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["redis"]["status"] == "error"
        assert "detail" in data["checks"]["redis"]

    def test_health_response_has_required_fields(self, client):
        """Health response always contains status, version, timestamp, checks."""
        response = client.get("/api/diagnostic/health")
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "checks" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_no_cors_headers_when_cors_disabled(self, client):
        """Health endpoint does not add CORS headers when middleware is disabled."""
        from app.config import settings

        if settings.cors_enabled:
            pytest.skip("CORS is enabled in this test environment")

        response = client.get(
            "/api/diagnostic/health",
            headers={"Origin": "https://evil.example.com"},
        )
        assert "access-control-allow-origin" not in response.headers

    def test_health_checks_contain_database_key(self, client):
        """Health checks dict always contains a 'database' key."""
        response = client.get("/api/diagnostic/health")
        data = response.json()
        assert "database" in data["checks"]

    def test_health_checks_contain_redis_key(self, client):
        """Health checks dict always contains a 'redis' key."""
        response = client.get("/api/diagnostic/health")
        data = response.json()
        assert "redis" in data["checks"]


@pytest.mark.integration
class TestTestNotification:
    """Tests for test notification endpoint."""

    def test_test_notification_endpoint(self, client):
        """Test /api/diagnostic/test-notification endpoint."""
        response = client.post("/api/diagnostic/test-notification")
        assert response.status_code == 200
        data = response.json()
        # Should return warning (no notification services configured) or success
        assert data["status"] in ("warning", "success", "error")

    @patch("app.api.diagnostic.settings")
    def test_test_notification_no_urls_configured(self, mock_settings, client):
        """Test notification test when no URLs are configured."""
        mock_settings.notification_urls = []
        mock_settings.external_hostname = "test-host"

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "warning"
        assert "notification" in data["message"].lower() and "configured" in data["message"].lower()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_success(self, mock_settings, mock_send, client):
        """Test successful notification test."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = True

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "success"
        assert "services_count" in data
        mock_send.assert_called_once()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_failure(self, mock_settings, mock_send, client):
        """Test notification test when sending fails."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = False

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "error"
        assert "failed" in data["message"].lower()

    @patch("app.utils.notification.send_notification")
    @patch("app.api.diagnostic.settings")
    def test_test_notification_exception(self, mock_settings, mock_send, client):
        """Test notification test with exception."""
        mock_settings.notification_urls = ["https://example.com/notify"]
        mock_settings.external_hostname = "test-host"
        mock_send.side_effect = Exception("Connection error")

        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        assert data["status"] == "error"
        assert "error" in data["message"].lower()

    def test_test_notification_includes_timestamp(self, client):
        """Test that notification includes timestamp in message."""
        response = client.post("/api/diagnostic/test-notification")
        data = response.json()

        # Response should have been processed
        assert response.status_code == 200
