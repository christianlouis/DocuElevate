"""Tests for the optional Uptime Kuma monitor."""

from unittest.mock import Mock, patch

import pytest
import requests

URL = "https://uptime.example.com/api/push/private-token"


@pytest.mark.unit
class TestUptimeKumaTasks:
    def test_provider_details_redact_push_path_query_and_token(self):
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as settings:
            settings.uptime_kuma_url = "https://uptime.example.com/api/push/private-token?user=alice"
            settings.uptime_kuma_ping_interval = 5
            details = get_provider_status()["Uptime Kuma"]["details"]

        assert details["url"] == "https://uptime.example.com"
        assert "private-token" not in str(details)
        assert "alice" not in str(details)

    def test_disabled_monitor_is_truthful_and_skips_request(self):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get") as request,
        ):
            settings.uptime_kuma_url = None
            result = ping_uptime_kuma()
        assert result["status"] == "disabled"
        assert result["configured"] is False
        request.assert_not_called()

    def test_success_reports_safe_endpoint_and_status(self):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get", return_value=Mock(status_code=204)) as request,
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "success"
        assert result["http_status"] == 204
        assert result["endpoint"] == "https://uptime.example.com"
        assert "private-token" not in str(result)
        request.assert_called_once_with(URL, timeout=10)

    def test_redirect_is_not_treated_as_success(self):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get", return_value=Mock(status_code=302)),
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "error"
        assert result["http_status"] == 302

    def test_kuma_json_rejection_is_not_treated_as_success(self):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        response = Mock(status_code=200)
        response.json.return_value = {"ok": False}
        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get", return_value=response),
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "error"
        assert "rejected" in result["message"]

    def test_client_error_is_actionable_without_retry(self):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get", return_value=Mock(status_code=401)) as request,
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "error"
        assert result["http_status"] == 401
        assert result["attempts"] == 1
        assert "push URL" in result["message"]
        request.assert_called_once()

    @pytest.mark.parametrize("status_code", [500, 503])
    def test_server_error_retries_with_bounded_backoff(self, status_code):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch("app.tasks.uptime_kuma_tasks.requests.get", return_value=Mock(status_code=status_code)) as request,
            patch("app.tasks.uptime_kuma_tasks.time.sleep") as sleep,
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "error"
        assert result["http_status"] == status_code
        assert result["attempts"] == 3
        assert request.call_count == 3
        assert sleep.call_args_list[0].args == (1,)
        assert sleep.call_args_list[1].args == (2,)

    def test_timeout_retries_then_returns_actionable_error(self, caplog):
        from app.tasks.uptime_kuma_tasks import ping_uptime_kuma

        with (
            patch("app.tasks.uptime_kuma_tasks.settings") as settings,
            patch(
                "app.tasks.uptime_kuma_tasks.requests.get",
                side_effect=requests.exceptions.Timeout("secret URL details"),
            ) as request,
            patch("app.tasks.uptime_kuma_tasks.time.sleep") as sleep,
        ):
            settings.uptime_kuma_url = URL
            result = ping_uptime_kuma()
        assert result["status"] == "error"
        assert result["attempts"] == 3
        assert "timeout" in result["message"]
        assert "private-token" not in str(result)
        assert "private-token" not in caplog.text
        assert request.call_count == 3
        assert sleep.call_count == 2
