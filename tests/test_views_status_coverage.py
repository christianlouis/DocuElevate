"""Comprehensive tests for app/views/status.py to improve coverage."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestStatusDashboard:
    """Tests for status_dashboard view function."""

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_renders(self, mock_settings, mock_templates):
        """Test status dashboard renders with provider info."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.notification_urls = []

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status") as mock_provider:
            mock_provider.return_value = {
                "OpenAI": {"configured": True, "status": "ok"},
                "Dropbox": {"configured": False},
            }
            with patch("app.views.status.os.path.exists", return_value=False):
                result = await status_dashboard(mock_request)
                mock_templates.TemplateResponse.assert_called_once()

                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                assert context["app_version"] == "1.0.0"
                assert context["build_date"] == "2024-01-01"
                assert context["debug_enabled"] is False
                assert context["container_info"]["is_docker"] is False

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_in_docker(self, mock_settings, mock_templates):
        """Test status dashboard inside Docker container."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = True
        mock_settings.notification_urls = ["https://hooks.example.com/notify"]
        mock_settings.git_sha = "abc1234567890"
        mock_settings.runtime_info = "Python 3.11"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status", return_value={}):
            with patch("app.views.status.os.path.exists") as mock_exists:
                mock_exists.return_value = True
                with patch("builtins.open", create=True) as mock_file:
                    mock_file.return_value.__enter__ = MagicMock(
                        return_value=MagicMock(
                            __iter__=MagicMock(
                                return_value=iter(
                                    ["12:devices:/docker/abc123def456\n"]
                                )
                            )
                        )
                    )
                    mock_file.return_value.__exit__ = MagicMock(return_value=False)

                    result = await status_dashboard(mock_request)
                    call_args = mock_templates.TemplateResponse.call_args
                    context = call_args[0][1]
                    assert context["container_info"]["is_docker"] is True
                    assert context["debug_enabled"] is True

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_git_sha_unknown(self, mock_settings, mock_templates):
        """Test status dashboard with unknown git SHA."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.build_date = "Unknown"
        mock_settings.debug = False
        mock_settings.notification_urls = []
        mock_settings.git_sha = "unknown"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status", return_value={}):
            with patch("app.views.status.os.path.exists", return_value=False):
                result = await status_dashboard(mock_request)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                assert context["container_info"]["git_sha"] == "Unknown"

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_git_sha_valid(self, mock_settings, mock_templates):
        """Test status dashboard with valid git SHA gets truncated."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.notification_urls = []
        mock_settings.git_sha = "abc123def456789"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status", return_value={}):
            with patch("app.views.status.os.path.exists", return_value=False):
                result = await status_dashboard(mock_request)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                assert context["container_info"]["git_sha"] == "abc123d"

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_exception_in_container_info(self, mock_settings, mock_templates):
        """Test status dashboard handles exception in container info gracefully."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.debug = False
        mock_settings.notification_urls = []
        del mock_settings.build_date

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status", return_value={}):
            with patch("app.views.status.os.path.exists", side_effect=Exception("Unexpected")):
                result = await status_dashboard(mock_request)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                assert context["container_info"]["is_docker"] is False

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_status_dashboard_notification_urls(self, mock_settings, mock_templates):
        """Test status dashboard passes notification URLs."""
        from app.views.status import status_dashboard

        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.notification_urls = ["https://example.com/hook1", "https://example.com/hook2"]
        mock_settings.git_sha = "abc1234"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_provider_status", return_value={}):
            with patch("app.views.status.os.path.exists", return_value=False):
                result = await status_dashboard(mock_request)
                call_args = mock_templates.TemplateResponse.call_args
                context = call_args[0][1]
                assert len(context["settings"]["notification_urls"]) == 2


@pytest.mark.unit
class TestEnvDebug:
    """Tests for env_debug view function."""

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_env_debug_with_debug_enabled(self, mock_settings, mock_templates):
        """Test env debug page with debug enabled shows values."""
        from app.views.status import env_debug

        mock_settings.debug = True
        mock_settings.version = "1.0.0"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_settings_for_display") as mock_display:
            mock_display.return_value = {"key": "value"}
            result = await env_debug(mock_request)
            mock_display.assert_called_once_with(show_values=True)
            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            assert context["debug_enabled"] is True

    @pytest.mark.asyncio
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    async def test_env_debug_with_debug_disabled(self, mock_settings, mock_templates):
        """Test env debug page with debug disabled hides values."""
        from app.views.status import env_debug

        mock_settings.debug = False
        mock_settings.version = "1.0.0"

        mock_request = MagicMock()
        mock_templates.TemplateResponse.return_value = MagicMock()

        with patch("app.utils.config_validator.get_settings_for_display") as mock_display:
            mock_display.return_value = {"key": "***"}
            result = await env_debug(mock_request)
            mock_display.assert_called_once_with(show_values=False)
            call_args = mock_templates.TemplateResponse.call_args
            context = call_args[0][1]
            assert context["debug_enabled"] is False


@pytest.mark.integration
class TestStatusViewsIntegration:
    """Integration tests for status views via TestClient."""

    def test_status_dashboard_accessible(self, client):
        """Test status dashboard returns 200."""
        response = client.get("/status")
        assert response.status_code == 200

    def test_env_debug_accessible(self, client):
        """Test env debug page returns 200."""
        response = client.get("/env")
        assert response.status_code == 200
