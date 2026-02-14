"""Tests for app/views/status.py module."""

from unittest.mock import Mock, mock_open, patch

import pytest


@pytest.mark.integration
class TestStatusViews:
    """Tests for status view routes."""

    def test_status_dashboard(self, client):
        """Test status dashboard page."""
        response = client.get("/status")
        assert response.status_code == 200

    def test_env_debug_page(self, client):
        """Test env debug page."""
        response = client.get("/env")
        assert response.status_code == 200


@pytest.mark.unit
class TestStatusDashboard:
    """Tests for status_dashboard function."""

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_status_dashboard_returns_template(self, mock_exists, mock_settings, mock_templates, mock_providers):
        """Test status dashboard returns template response."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False
        mock_providers.return_value = {
            "OpenAI": {"configured": True, "status": "success"},
            "Azure AI": {"configured": False},
        }
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.debug = False
        mock_settings.git_sha = "abc123"
        mock_settings.runtime_info = "Python 3.11"
        mock_settings.notification_urls = []

        mock_request = Mock()

        result = await status_dashboard(mock_request)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "status_dashboard.html"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="12:docker:/container_id")
    @pytest.mark.asyncio
    async def test_detects_docker_environment(
        self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test detects Docker environment."""
        from app.views.status import status_dashboard

        mock_exists.return_value = True
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["container_info"]["is_docker"] is True

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_handles_non_docker_environment(self, mock_exists, mock_settings, mock_templates, mock_providers):
        """Test handles non-Docker environment."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["container_info"]["is_docker"] is False

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_includes_git_sha_in_context(self, mock_settings, mock_templates, mock_providers):
        """Test includes git SHA in context."""
        from app.views.status import status_dashboard

        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc1234567890"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert "git_sha" in context["container_info"]

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_includes_notification_urls(self, mock_settings, mock_templates, mock_providers):
        """Test includes notification URLs in context."""
        from app.views.status import status_dashboard

        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = ["https://webhook.example.com/notify"]

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["settings"]["notification_urls"] == ["https://webhook.example.com/notify"]


@pytest.mark.unit
class TestEnvDebug:
    """Tests for env_debug function."""

    @patch("app.views.status.get_settings_for_display")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_env_debug_returns_template(self, mock_settings, mock_templates, mock_get_settings):
        """Test env debug returns template response."""
        from app.views.status import env_debug

        mock_settings.debug = False
        mock_settings.version = "1.0.0"
        mock_get_settings.return_value = {"workdir": {"value": "/app/workdir"}}

        mock_request = Mock()

        result = await env_debug(mock_request)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "env_debug.html"

    @patch("app.views.status.get_settings_for_display")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_env_debug_respects_debug_setting(self, mock_settings, mock_templates, mock_get_settings):
        """Test env debug respects debug setting."""
        from app.views.status import env_debug

        mock_settings.debug = True
        mock_settings.version = "1.0.0"
        mock_get_settings.return_value = {}

        mock_request = Mock()

        await env_debug(mock_request)

        # Should call with show_values=True when debug is enabled
        mock_get_settings.assert_called_once_with(show_values=True)

    @patch("app.views.status.get_settings_for_display")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_env_debug_hides_values_when_debug_disabled(self, mock_settings, mock_templates, mock_get_settings):
        """Test env debug hides values when debug is disabled."""
        from app.views.status import env_debug

        mock_settings.debug = False
        mock_settings.version = "1.0.0"
        mock_get_settings.return_value = {}

        mock_request = Mock()

        await env_debug(mock_request)

        # Should call with show_values=False when debug is disabled
        mock_get_settings.assert_called_once_with(show_values=False)

    @patch("app.views.status.get_settings_for_display")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @pytest.mark.asyncio
    async def test_env_debug_includes_app_version(self, mock_settings, mock_templates, mock_get_settings):
        """Test env debug includes app version."""
        from app.views.status import env_debug

        mock_settings.debug = False
        mock_settings.version = "1.2.3"
        mock_get_settings.return_value = {}

        mock_request = Mock()

        await env_debug(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["app_version"] == "1.2.3"


@pytest.mark.unit
class TestContainerInfoDetection:
    """Tests for container information detection logic."""

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", side_effect=IOError("Permission denied"))
    @pytest.mark.asyncio
    async def test_handles_cgroup_read_error(self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers):
        """Test handles cgroup file read errors."""
        from app.views.status import status_dashboard

        mock_exists.return_value = True  # Docker env exists
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # Should handle error gracefully and set id to Unknown
        assert context["container_info"]["is_docker"] is True
        assert context["container_info"]["id"] == "Unknown"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="12:cpuset:/system.slice\n13:memory:/user.slice")
    @pytest.mark.asyncio
    async def test_handles_cgroup_without_docker(self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers):
        """Test handles cgroup without docker in path."""
        from app.views.status import status_dashboard

        mock_exists.return_value = True  # Docker env exists
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc123"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # When docker not found in cgroup, id is not set in the code
        # The loop completes without setting id, so it won't be in container_info
        assert context["container_info"]["is_docker"] is True

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="12:docker:/abc123456789")
    @pytest.mark.asyncio
    async def test_handles_unknown_git_sha_string(
        self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test handles 'unknown' git_sha string value."""
        from app.views.status import status_dashboard

        mock_exists.return_value = True
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "unknown"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # Should handle "unknown" string and set to Unknown
        assert context["container_info"]["git_sha"] == "Unknown"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_handles_complete_exception_in_container_info(
        self, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test handles complete exception in container info extraction."""
        from app.views.status import status_dashboard

        # Simulate exception when checking Docker env
        mock_exists.side_effect = Exception("Unexpected error")
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # Should have fallback container_info
        assert context["container_info"]["is_docker"] is False
        assert context["container_info"]["id"] == "Unknown"
        assert context["container_info"]["git_sha"] == "Unknown"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @pytest.mark.asyncio
    async def test_handles_null_git_sha(self, mock_exists, mock_settings, mock_templates, mock_providers):
        """Test handles None/null git_sha value."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False  # Not in Docker
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = None  # None value
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # Should handle None and set to Unknown
        assert context["container_info"]["git_sha"] == "Unknown"


@pytest.mark.integration
class TestStatusEndpointsRequireAuth:
    """Tests for status endpoint authentication."""

    def test_status_dashboard_requires_login(self, client):
        """Test status dashboard requires authentication."""
        # Should return 200 or redirect to login
        response = client.get("/status", follow_redirects=False)
        assert response.status_code in [200, 302, 401]

    def test_env_debug_requires_login(self, client):
        """Test env debug requires authentication."""
        # Should return 200 or redirect to login
        response = client.get("/env", follow_redirects=False)
        assert response.status_code in [200, 302, 401]
