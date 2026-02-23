"""
Targeted tests to fill remaining coverage gaps in:
- app/views/base.py (lines 36-41)
- app/views/general.py (lines 64-66, 111, 133-134, 138)
- app/views/status.py (lines 53-54, 59-60, 68-69)
- app/utils/config_validator/providers.py (lines 68-78, 86-100, 243)
- app/utils/settings_sync.py (lines 71-72, 95-98)
- app/api/logs.py (additional branches)
"""

from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

# ===========================================================================
# app/views/base.py  – kwargs context path (lines 36-41)
# ===========================================================================


@pytest.mark.unit
class TestViewsBase:
    """Tests for template_response_with_version wrapper in app/views/base.py."""

    def test_kwargs_context_version_injection(self):
        """Test version injection when context is passed as a keyword argument."""
        from app.views.base import template_response_with_version

        with patch("app.views.base.original_template_response") as mock_orig:
            mock_orig.return_value = "response"
            req = MagicMock()
            # Make the request NOT have a csrf_token on its state
            del req.state.csrf_token  # ensure AttributeError on hasattr

            result = template_response_with_version(
                "template.html",
                context={"request": req, "title": "Test"},
            )

        mock_orig.assert_called_once()
        _, kwargs = mock_orig.call_args
        assert "version" in kwargs["context"]

    def test_kwargs_context_csrf_token_injection(self):
        """Test CSRF token injection when context has request with csrf_token."""
        from app.views.base import template_response_with_version

        with patch("app.views.base.original_template_response") as mock_orig:
            mock_orig.return_value = "response"
            req = MagicMock()
            req.state.csrf_token = "test-csrf-token"

            template_response_with_version(
                "template.html",
                context={"request": req},
            )

        _, kwargs = mock_orig.call_args
        assert kwargs["context"].get("csrf_token") == "test-csrf-token"

    def test_positional_context_with_csrf_token(self):
        """Test CSRF token injection via positional args."""
        from app.views.base import template_response_with_version

        with patch("app.views.base.original_template_response") as mock_orig:
            mock_orig.return_value = "response"
            req = MagicMock()
            req.state.csrf_token = "my-csrf"

            context = {"request": req}
            template_response_with_version("template.html", context)

        args, _ = mock_orig.call_args
        assert args[1].get("csrf_token") == "my-csrf"

    def test_kwargs_context_no_request(self):
        """Test kwargs context path when request is not in context."""
        from app.views.base import template_response_with_version

        with patch("app.views.base.original_template_response") as mock_orig:
            mock_orig.return_value = "response"

            template_response_with_version(
                "template.html",
                context={"title": "No request"},
            )

        mock_orig.assert_called_once()
        _, kwargs = mock_orig.call_args
        assert "version" in kwargs["context"]

    def test_no_args_no_context(self):
        """Test with no args and no context (edge case)."""
        from app.views.base import template_response_with_version

        with patch("app.views.base.original_template_response") as mock_orig:
            mock_orig.return_value = "response"
            template_response_with_version("template.html")

        mock_orig.assert_called_once()


# ===========================================================================
# app/views/general.py  – error branches
# ===========================================================================


@pytest.mark.unit
class TestGeneralViewsAdditional:
    """Additional tests for general view error branches."""

    @patch("app.views.general.get_provider_status")
    @patch("app.views.general.validate_storage_configs")
    @patch("app.views.general.templates")
    @pytest.mark.asyncio
    async def test_db_error_logged_but_page_still_renders(self, mock_templates, mock_storage, mock_providers):
        """Test that a DB error is logged but the page still renders (lines 64-66)."""
        from app.views.general import serve_index

        mock_providers.return_value = {}
        mock_storage.return_value = {}
        mock_templates.TemplateResponse = MagicMock(return_value="response")

        with patch("app.utils.settings_service.get_setting_from_db", return_value=None):
            with patch("app.utils.setup_wizard.is_setup_required", return_value=False):
                mock_request = MagicMock()
                mock_request.query_params.get = MagicMock(return_value=None)
                mock_db = MagicMock()
                # Make DB query fail to trigger the except block (lines 64-66)
                mock_db.query.side_effect = Exception("DB failure")

                result = await serve_index(mock_request, mock_db)

        # Page should still render with 0 processed_files
        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["stats"]["processed_files"] == 0

    @patch("app.views.general.templates")
    @pytest.mark.asyncio
    async def test_favicon_not_found_raises_404(self, mock_templates):
        """Test that missing favicon raises 404 HTTPException (line 111)."""
        from fastapi import HTTPException

        from app.views.general import favicon

        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                favicon()

        assert exc_info.value.status_code == 404

    @patch("app.views.general.templates")
    @pytest.mark.asyncio
    async def test_license_fallback_when_no_file_found(self, mock_templates):
        """Test that license page uses embedded text when no file found (lines 133-134, 138)."""
        from app.views.general import serve_license

        mock_templates.TemplateResponse = MagicMock(return_value="response")
        mock_request = MagicMock()

        # Patch open to raise FileNotFoundError for all paths
        with patch("builtins.open", side_effect=FileNotFoundError("No such file")):
            await serve_license(mock_request)

        # Template should be called with embedded license text
        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert "Apache License" in context["license_text"]

    def test_license_page_integration_always_renders(self, client):
        """Test license page renders (with real or embedded text)."""
        response = client.get("/license")
        assert response.status_code == 200


# ===========================================================================
# app/views/status.py  – Docker exception branches
# ===========================================================================


@pytest.mark.unit
class TestStatusViewsAdditional:
    """Additional tests for status view exception branches."""

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="12:docker:/abc123")
    @pytest.mark.asyncio
    async def test_git_sha_exception_in_docker_env(
        self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test Docker env: git_sha[:7] raises exception → lines 53-54."""
        from app.views.status import status_dashboard

        mock_exists.return_value = True  # Docker env exists
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        # A bool is not subscriptable, so git_sha[:7] raises TypeError → lines 53-54
        mock_settings.git_sha = True
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["container_info"]["is_docker"] is True
        assert context["container_info"]["git_sha"] == "Unknown"

    @patch("app.views.status.get_provider_status")
    @patch("app.views.status.templates")
    @patch("app.views.status.settings")
    @patch("app.views.status.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data="12:docker:/abc123")
    @pytest.mark.asyncio
    async def test_runtime_info_exception_in_docker_env(
        self, mock_file, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test Docker env: settings.runtime_info raises exception → lines 59-60."""
        from unittest.mock import PropertyMock

        from app.views.status import status_dashboard

        mock_exists.return_value = True
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        mock_settings.git_sha = "abc1234567"
        mock_settings.notification_urls = []
        # Use spec to restrict runtime_info to raise AttributeError
        # since it's not a validated Settings attribute
        type(mock_settings).runtime_info = PropertyMock(side_effect=AttributeError("runtime_info not set"))

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
    async def test_git_sha_exception_in_non_docker_env(
        self, mock_exists, mock_settings, mock_templates, mock_providers
    ):
        """Test non-Docker env: git_sha[:7] raises exception → lines 68-69."""
        from app.views.status import status_dashboard

        mock_exists.return_value = False  # Not in Docker
        mock_providers.return_value = {}
        mock_settings.version = "1.0.0"
        mock_settings.build_date = "2024-01-01"
        # A bool is not subscriptable, so git_sha[:7] raises TypeError → lines 68-69
        mock_settings.git_sha = True
        mock_settings.notification_urls = []

        mock_request = Mock()

        await status_dashboard(mock_request)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["container_info"]["is_docker"] is False
        assert context["container_info"]["git_sha"] == "Unknown"


# ===========================================================================
# app/utils/config_validator/providers.py – alternative AI providers
# ===========================================================================


@pytest.mark.unit
class TestProvidersAlternativeAI:
    """Tests for alternative AI provider branches in get_provider_status."""

    def test_anthropic_configured(self):
        """Test provider status with anthropic AI provider (lines 68-69, 86-87)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "anthropic"
            mock_settings.ai_model = "claude-3-5-sonnet"
            mock_settings.anthropic_api_key = "sk-ant-key"
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is True
        assert ai_provider["details"]["provider"] == "anthropic"
        assert "api_key" in ai_provider["details"]

    def test_gemini_configured(self):
        """Test provider status with gemini AI provider (lines 70-71, 88-89)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "gemini"
            mock_settings.ai_model = "gemini-pro"
            mock_settings.gemini_api_key = "gemini-key-123"
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is True
        assert ai_provider["details"]["provider"] == "gemini"
        assert "api_key" in ai_provider["details"]

    def test_ollama_configured(self):
        """Test provider status with ollama AI provider (lines 72-73, 90-91)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "ollama"
            mock_settings.ai_model = "llama2"
            mock_settings.ollama_base_url = "http://localhost:11434"
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is True
        assert ai_provider["details"]["provider"] == "ollama"
        assert "base_url" in ai_provider["details"]

    def test_openrouter_configured(self):
        """Test provider status with openrouter AI provider (lines 74-75, 92-94)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "openrouter"
            mock_settings.ai_model = "openai/gpt-4"
            mock_settings.openrouter_api_key = "or-key-123"
            mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is True
        assert ai_provider["details"]["provider"] == "openrouter"
        assert "api_key" in ai_provider["details"]
        assert "base_url" in ai_provider["details"]

    def test_portkey_configured_with_virtual_key(self):
        """Test provider status with portkey AI provider including virtual key (lines 76-77, 95-100)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "portkey"
            mock_settings.ai_model = "claude-3"
            mock_settings.portkey_api_key = "pk-key-123"
            mock_settings.portkey_virtual_key = "vk-123"
            mock_settings.portkey_config = None
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is True
        assert ai_provider["details"]["provider"] == "portkey"
        assert "api_key" in ai_provider["details"]
        assert "virtual_key" in ai_provider["details"]

    def test_portkey_configured_with_config(self):
        """Test provider status with portkey AI provider including config."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "portkey"
            mock_settings.ai_model = "claude-3"
            mock_settings.portkey_api_key = "pk-key-123"
            mock_settings.portkey_virtual_key = None
            mock_settings.portkey_config = '{"strategy": "loadbalance"}'
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert "config" in ai_provider["details"]

    def test_unknown_ai_provider_not_configured(self):
        """Test that unknown provider returns configured=False (line 78 – return False)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "unknown_provider"
            mock_settings.ai_model = None
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        ai_provider = result["AI Provider"]
        assert ai_provider["configured"] is False

    def test_nextcloud_url_with_remote_php(self):
        """Test that nextcloud base URL is extracted correctly (line 243)."""
        from app.utils.config_validator.providers import get_provider_status

        with patch("app.utils.config_validator.providers.settings") as mock_settings:
            mock_settings.ai_provider = "openai"
            mock_settings.ai_model = "gpt-4o-mini"
            mock_settings.openai_api_key = "sk-key"
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.auth_enabled = False
            mock_settings.notification_urls = []
            mock_settings.azure_ai_key = None
            mock_settings.azure_endpoint = None
            mock_settings.azure_region = "eastus"
            # NextCloud URL with /remote.php should be split
            mock_settings.nextcloud_upload_url = "https://cloud.example.com/remote.php/dav/files/user"
            mock_settings.nextcloud_username = "user"
            mock_settings.nextcloud_password = "pass"
            mock_settings.nextcloud_folder = "/Docs"
            _set_minimal_provider_settings(mock_settings)

            result = get_provider_status()

        nextcloud = result["NextCloud"]
        assert nextcloud["details"]["base_url"] == "https://cloud.example.com"


def _set_minimal_provider_settings(mock_settings):
    """Helper to set the minimal settings attributes needed by get_provider_status."""
    defaults = {
        "authentik_client_id": None,
        "authentik_client_secret": None,
        "authentik_config_url": None,
        "admin_username": None,
        "oauth_provider_name": None,
        "session_secret": "secret",
        "notify_on_task_failure": True,
        "notify_on_credential_failure": True,
        "notify_on_startup": True,
        "notify_on_shutdown": False,
        "dropbox_app_key": None,
        "dropbox_app_secret": None,
        "dropbox_refresh_token": None,
        "dropbox_folder": "/",
        "email_host": None,
        "email_default_recipient": None,
        "email_port": 587,
        "email_username": None,
        "email_password": None,
        "email_use_tls": True,
        "email_sender": None,
        "ftp_host": None,
        "ftp_username": None,
        "ftp_password": None,
        "ftp_port": 21,
        "ftp_folder": "/",
        "ftp_use_tls": True,
        "ftp_allow_plaintext": False,
        "google_drive_client_id": None,
        "google_drive_client_secret": None,
        "google_drive_refresh_token": None,
        "google_drive_credentials_json": None,
        "google_drive_use_oauth": False,
        "google_drive_folder_id": None,
        "google_drive_delegate_to": None,
        "nextcloud_upload_url": None,
        "nextcloud_username": None,
        "nextcloud_password": None,
        "nextcloud_folder": "/",
        "onedrive_client_id": None,
        "onedrive_client_secret": None,
        "onedrive_refresh_token": None,
        "onedrive_tenant_id": None,
        "onedrive_folder_path": "/",
        "paperless_url": None,
        "paperless_api_token": None,
        "paperless_correspondent_name": None,
        "paperless_document_type_name": None,
        "s3_bucket_name": None,
        "s3_region": None,
        "aws_access_key_id": None,
        "aws_secret_access_key": None,
        "s3_folder_prefix": None,
        "sftp_host": None,
        "sftp_username": None,
        "sftp_password": None,
        "sftp_port": 22,
        "sftp_folder": "/",
        "sftp_private_key": None,
        "webdav_url": None,
        "webdav_username": None,
        "webdav_password": None,
        "webdav_folder": "/",
        "imap_host": None,
        "imap_username": None,
        "imap_password": None,
        "imap_folder": "INBOX",
        "gotenberg_url": "http://localhost:3000",
        "rclone_remote": None,
        "rclone_base_path": None,
        "uptime_kuma_push_url": None,
        # AI provider specifics (set None to avoid AttributeError)
        "anthropic_api_key": None,
        "gemini_api_key": None,
        "ollama_base_url": None,
        "openrouter_api_key": None,
        "openrouter_base_url": None,
        "portkey_api_key": None,
        "portkey_virtual_key": None,
        "portkey_config": None,
        "litellm": None,
        "openai_api_key": None,
        "openai_base_url": "https://api.openai.com/v1",
    }
    for attr, val in defaults.items():
        if not hasattr(mock_settings, attr) or getattr(mock_settings, attr, "NOTSET") == "NOTSET":
            setattr(mock_settings, attr, val)


# ===========================================================================
# app/utils/settings_sync.py  – reload failure and signal handler
# ===========================================================================


@pytest.mark.unit
class TestSettingsSyncAdditional:
    """Additional tests for settings_sync covering reload failure branch."""

    def test_reload_failure_is_logged_not_raised(self):
        """Test that a reload failure is logged, not raised (lines 71-72)."""
        from app.utils.settings_sync import notify_settings_updated

        with patch("app.utils.settings_sync.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = MagicMock()  # Redis OK
            with patch("app.utils.config_loader.reload_settings_from_db", side_effect=Exception("reload failed")):
                # Should not raise despite reload failure
                notify_settings_updated()

    def test_signal_handler_reloads_on_version_change(self):
        """Test the task_prerun signal handler reloads settings when version changes (lines 95-98)."""
        from app.utils.settings_sync import register_settings_reload_signal

        handler_fn = None

        # Capture the handler; the decorator pattern means connect(weak=False)
        # returns a decorator, which is then applied to _reload_if_stale
        def capture_connect(fn=None, weak=None, **kwargs):
            nonlocal handler_fn
            if fn is not None:
                handler_fn = fn
                return fn

            def decorator(func):
                nonlocal handler_fn
                handler_fn = func
                return func

            return decorator

        with patch("app.utils.settings_sync.task_prerun") as mock_signal:
            mock_signal.connect = capture_connect
            register_settings_reload_signal()

        assert handler_fn is not None

        # Simulate handler being called with a new version
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"1234567890.0"  # new version

        with patch("app.utils.settings_sync.redis") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_redis
            with patch("app.utils.config_loader.reload_settings_from_db") as mock_reload:
                with patch("app.utils.settings_sync._last_seen_version", ""):
                    handler_fn(sender=None)  # call the signal handler
                    mock_reload.assert_called_once()

    def test_signal_handler_skips_reload_when_version_unchanged(self):
        """Test that handler skips reload when version is same as last seen."""
        import app.utils.settings_sync as sync_module
        from app.utils.settings_sync import register_settings_reload_signal

        handler_fn = None

        def capture_connect(fn=None, weak=None, **kwargs):
            nonlocal handler_fn
            if fn is not None:
                handler_fn = fn
                return fn

            def decorator(func):
                nonlocal handler_fn
                handler_fn = func
                return func

            return decorator

        with patch("app.utils.settings_sync.task_prerun") as mock_signal:
            mock_signal.connect = capture_connect
            register_settings_reload_signal()

        assert handler_fn is not None

        version = "999.0"
        mock_redis = MagicMock()
        mock_redis.get.return_value = version.encode()

        with patch("app.utils.settings_sync.redis") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_redis
            with patch("app.utils.config_loader.reload_settings_from_db") as mock_reload:
                # Set last seen to same version
                sync_module._last_seen_version = version
                handler_fn(sender=None)
                mock_reload.assert_not_called()

    def test_signal_handler_handles_redis_failure(self):
        """Test that signal handler skips gracefully on Redis failure."""
        from app.utils.settings_sync import register_settings_reload_signal

        handler_fn = None

        def capture_connect(fn=None, weak=None, **kwargs):
            nonlocal handler_fn
            if fn is not None:
                handler_fn = fn
                return fn

            def decorator(func):
                nonlocal handler_fn
                handler_fn = func
                return func

            return decorator

        with patch("app.utils.settings_sync.task_prerun") as mock_signal:
            mock_signal.connect = capture_connect
            register_settings_reload_signal()

        assert handler_fn is not None

        with patch("app.utils.settings_sync.redis") as mock_redis_mod:
            mock_redis_mod.from_url.side_effect = Exception("Redis down")
            # Should not raise
            handler_fn(sender=None)


# ===========================================================================
# app/api/logs.py – additional branches
# ===========================================================================


@pytest.mark.integration
class TestLogsApiAdditional:
    """Additional tests for logs API to improve branch coverage."""

    def test_list_logs_filter_by_file_id(self, client, db_session):
        """Test filtering logs by file_id."""
        from app.models import FileRecord, ProcessingLog

        file_record = FileRecord(
            filehash="hash123",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        log = ProcessingLog(
            file_id=file_record.id,
            task_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            step_name="process",
            status="success",
            message="Done",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get(f"/api/logs?file_id={file_record.id}")
        assert response.status_code == 200
        data = response.json()
        assert all(entry["file_id"] == file_record.id for entry in data)

    def test_list_logs_with_null_timestamp(self, client, db_session):
        """Test log with null timestamp serializes to None."""
        from app.models import ProcessingLog

        log = ProcessingLog(
            task_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            step_name="step",
            status="success",
            message="msg",
        )
        log.timestamp = None
        db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs")
        assert response.status_code == 200

    def test_get_file_logs_returns_200(self, client, db_session):
        """Test get file logs endpoint returns data."""
        from app.models import FileRecord, ProcessingLog

        file_record = FileRecord(
            filehash="hash456",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=512,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        log = ProcessingLog(
            file_id=file_record.id,
            task_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            step_name="step",
            status="success",
            message="msg",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get(f"/api/logs/file/{file_record.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) >= 1
