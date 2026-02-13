"""
Tests for app/tasks/uptime_kuma_tasks.py

Tests Uptime Kuma health check ping functionality.
"""

from unittest.mock import Mock, patch

import pytest
import requests


@pytest.mark.unit
class TestUptimeKumaTasks:
    """Test Uptime Kuma ping task"""

    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_no_url_configured(self, mock_settings):
        """Test that task does nothing when URL is not configured"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = None

        result = ping_uptime_kuma()

        # Should return None and not make any requests
        assert result is None

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_success(self, mock_settings, mock_get):
        """Test successful ping to Uptime Kuma"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = ping_uptime_kuma()

        # Should return True on success
        assert result is True
        mock_get.assert_called_once_with("https://uptime.example.com/ping/123", timeout=10)
        mock_response.raise_for_status.assert_called_once()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_connection_error(self, mock_settings, mock_get):
        """Test handling of connection errors"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Mock connection error
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        result = ping_uptime_kuma()

        # Should return False on error
        assert result is False
        mock_get.assert_called_once()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_timeout(self, mock_settings, mock_get):
        """Test handling of request timeout"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Mock timeout error
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        result = ping_uptime_kuma()

        # Should return False on timeout
        assert result is False
        mock_get.assert_called_once()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_http_error(self, mock_settings, mock_get):
        """Test handling of HTTP errors (4xx, 5xx)"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Mock HTTP error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        mock_get.return_value = mock_response

        result = ping_uptime_kuma()

        # Should return False on HTTP error
        assert result is False
        mock_get.assert_called_once()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_generic_request_exception(self, mock_settings, mock_get):
        """Test handling of generic request exceptions"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Mock generic request exception
        mock_get.side_effect = requests.exceptions.RequestException("Generic error")

        result = ping_uptime_kuma()

        # Should return False on any request exception
        assert result is False
        mock_get.assert_called_once()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_empty_url(self, mock_settings, mock_get):
        """Test handling of empty URL string"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = ""

        result = ping_uptime_kuma()

        # Should return None and not make any requests
        assert result is None
        mock_get.assert_not_called()

    @patch("app.tasks.uptime_kuma_tasks.requests.get")
    @patch("app.tasks.uptime_kuma_tasks.settings")
    def test_ping_uptime_kuma_with_various_status_codes(self, mock_settings, mock_get):
        """Test successful ping with various 2xx status codes"""
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        mock_settings.uptime_kuma_url = "https://uptime.example.com/ping/123"

        # Test with 200 OK
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = ping_uptime_kuma()
        assert result is True

        # Test with 204 No Content
        mock_response.status_code = 204
        result = ping_uptime_kuma()
        assert result is True

        # Test with 202 Accepted
        mock_response.status_code = 202
        result = ping_uptime_kuma()
        assert result is True
