"""
Tests for app/utils/sentry.py

Tests Sentry SDK initialisation logic, including:
- No-op when DSN is absent
- Successful init when DSN is present
- Celery integration activation
- Missing sentry-sdk package handling
- Sample rate clamping
"""

import builtins
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestInitSentry:
    """Test init_sentry() behaviour under various configurations"""

    def test_returns_false_when_no_dsn(self, mocker):
        """init_sentry returns False and does nothing when SENTRY_DSN is not set."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = None

        from app.utils.sentry import init_sentry

        result = init_sentry()

        assert result is False

    def test_returns_false_when_dsn_empty_string(self, mocker):
        """init_sentry returns False when SENTRY_DSN is an empty string."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = ""

        from app.utils.sentry import init_sentry

        result = init_sentry()

        assert result is False

    def test_returns_false_when_sentry_not_installed(self, mocker):
        """init_sentry returns False and logs a warning when sentry_sdk is missing."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@sentry.io/123"

        # Simulate sentry_sdk not being importable by patching the import at module level

        original_import = builtins.__import__

        def _block_sentry(name, *args, **kwargs):
            if name.startswith("sentry_sdk"):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=_block_sentry)

        from app.utils.sentry import init_sentry

        result = init_sentry()

        assert result is False

    def test_initialises_sentry_with_dsn(self, mocker):
        """init_sentry calls sentry_sdk.init when a DSN is provided."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@o123.ingest.sentry.io/456"
        mock_settings.sentry_environment = "production"
        mock_settings.sentry_traces_sample_rate = 0.1
        mock_settings.sentry_profiles_sample_rate = 0.0
        mock_settings.sentry_send_default_pii = False
        mock_settings.version = "1.2.3"

        mock_sdk_init = mocker.patch("sentry_sdk.init")
        # Patch the integrations so we don't need real Sentry internals
        mocker.patch("sentry_sdk.integrations.fastapi.FastApiIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.starlette.StarletteIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.sqlalchemy.SqlalchemyIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.logging.LoggingIntegration", return_value=MagicMock())

        from app.utils.sentry import init_sentry

        result = init_sentry()

        assert result is True
        mock_sdk_init.assert_called_once()
        call_kwargs = mock_sdk_init.call_args.kwargs
        assert call_kwargs["dsn"] == "https://key@o123.ingest.sentry.io/456"
        assert call_kwargs["environment"] == "production"
        assert call_kwargs["release"] == "1.2.3"
        assert call_kwargs["send_default_pii"] is False

    def test_celery_integration_included_when_requested(self, mocker):
        """CeleryIntegration is appended when integrations_extra=['celery']."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "staging"
        mock_settings.sentry_traces_sample_rate = 0.5
        mock_settings.sentry_profiles_sample_rate = 0.0
        mock_settings.sentry_send_default_pii = False
        mock_settings.version = None

        mock_sdk_init = mocker.patch("sentry_sdk.init")
        mock_celery_cls = mocker.patch("sentry_sdk.integrations.celery.CeleryIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.fastapi.FastApiIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.starlette.StarletteIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.sqlalchemy.SqlalchemyIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.logging.LoggingIntegration", return_value=MagicMock())

        from app.utils.sentry import init_sentry

        result = init_sentry(integrations_extra=["celery"])

        assert result is True
        mock_celery_cls.assert_called_once_with(monitor_beat_tasks=True)

    def test_traces_sample_rate_clamped_above_one(self, mocker):
        """Traces sample rate values above 1.0 are clamped to 1.0."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "test"
        mock_settings.sentry_traces_sample_rate = 99.0  # invalid – too high
        mock_settings.sentry_profiles_sample_rate = 0.0
        mock_settings.sentry_send_default_pii = False
        mock_settings.version = None

        mock_sdk_init = mocker.patch("sentry_sdk.init")
        mocker.patch("sentry_sdk.integrations.fastapi.FastApiIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.starlette.StarletteIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.sqlalchemy.SqlalchemyIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.logging.LoggingIntegration", return_value=MagicMock())

        from app.utils.sentry import init_sentry

        init_sentry()

        call_kwargs = mock_sdk_init.call_args.kwargs
        assert call_kwargs["traces_sample_rate"] == 1.0

    def test_traces_sample_rate_clamped_below_zero(self, mocker):
        """Traces sample rate values below 0.0 are clamped to 0.0."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "test"
        mock_settings.sentry_traces_sample_rate = -5.0  # invalid – negative
        mock_settings.sentry_profiles_sample_rate = 0.0
        mock_settings.sentry_send_default_pii = False
        mock_settings.version = None

        mock_sdk_init = mocker.patch("sentry_sdk.init")
        mocker.patch("sentry_sdk.integrations.fastapi.FastApiIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.starlette.StarletteIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.sqlalchemy.SqlalchemyIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.logging.LoggingIntegration", return_value=MagicMock())

        from app.utils.sentry import init_sentry

        init_sentry()

        call_kwargs = mock_sdk_init.call_args.kwargs
        assert call_kwargs["traces_sample_rate"] == 0.0

    def test_no_celery_integration_when_not_requested(self, mocker):
        """CeleryIntegration is not included when integrations_extra is empty."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "test"
        mock_settings.sentry_traces_sample_rate = 0.0
        mock_settings.sentry_profiles_sample_rate = 0.0
        mock_settings.sentry_send_default_pii = False
        mock_settings.version = None

        mock_sdk_init = mocker.patch("sentry_sdk.init")
        mock_celery_cls = mocker.patch("sentry_sdk.integrations.celery.CeleryIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.fastapi.FastApiIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.starlette.StarletteIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.sqlalchemy.SqlalchemyIntegration", return_value=MagicMock())
        mocker.patch("sentry_sdk.integrations.logging.LoggingIntegration", return_value=MagicMock())

        from app.utils.sentry import init_sentry

        init_sentry()

        mock_celery_cls.assert_not_called()
        mock_sdk_init.assert_called_once()


@pytest.mark.unit
class TestGetAppVersion:
    """Test the internal _get_app_version helper."""

    def test_returns_version_from_settings(self, mocker):
        """_get_app_version returns settings.version when available."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.version = "2.0.0"

        from app.utils.sentry import _get_app_version

        assert _get_app_version() == "2.0.0"

    def test_returns_none_when_version_unknown(self, mocker):
        """_get_app_version returns None when version is 'unknown' or empty."""
        mock_settings = mocker.patch("app.utils.sentry.settings")
        mock_settings.version = None

        from app.utils.sentry import _get_app_version

        assert _get_app_version() is None


@pytest.mark.unit
class TestSentryJsTemplateContext:
    """Test that Sentry Browser SDK config is injected into the template context."""

    def test_sentry_dsn_exposed_when_configured(self, mocker):
        """sentry_dsn is set in the template context when SENTRY_DSN is configured."""
        mock_settings = mocker.patch("app.views.base.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "production"
        mock_settings.sentry_js_traces_sample_rate = 0.1
        mock_settings.sentry_js_replay_session_sample_rate = 0.0
        mock_settings.sentry_js_replay_on_error_sample_rate = 0.1

        from app.views.base import _inject_global_context

        ctx: dict = {}
        _inject_global_context(ctx)

        assert ctx["sentry_dsn"] == "https://key@o1.ingest.sentry.io/1"

    def test_sentry_dsn_none_when_not_configured(self, mocker):
        """sentry_dsn is None in the template context when SENTRY_DSN is unset."""
        mock_settings = mocker.patch("app.views.base.settings")
        mock_settings.sentry_dsn = None
        mock_settings.sentry_environment = "production"
        mock_settings.sentry_js_traces_sample_rate = 0.0
        mock_settings.sentry_js_replay_session_sample_rate = 0.0
        mock_settings.sentry_js_replay_on_error_sample_rate = 0.1

        from app.views.base import _inject_global_context

        ctx: dict = {}
        _inject_global_context(ctx)

        assert ctx["sentry_dsn"] is None

    def test_sentry_dsn_empty_string_becomes_none(self, mocker):
        """An empty-string SENTRY_DSN is normalised to None in the template context."""
        mock_settings = mocker.patch("app.views.base.settings")
        mock_settings.sentry_dsn = ""
        mock_settings.sentry_environment = "production"
        mock_settings.sentry_js_traces_sample_rate = 0.0
        mock_settings.sentry_js_replay_session_sample_rate = 0.0
        mock_settings.sentry_js_replay_on_error_sample_rate = 0.1

        from app.views.base import _inject_global_context

        ctx: dict = {}
        _inject_global_context(ctx)

        assert ctx["sentry_dsn"] is None

    def test_js_sample_rates_exposed_in_context(self, mocker):
        """Browser SDK sample rates are passed through to the template context."""
        mock_settings = mocker.patch("app.views.base.settings")
        mock_settings.sentry_dsn = "https://key@o1.ingest.sentry.io/1"
        mock_settings.sentry_environment = "staging"
        mock_settings.sentry_js_traces_sample_rate = 0.5
        mock_settings.sentry_js_replay_session_sample_rate = 0.2
        mock_settings.sentry_js_replay_on_error_sample_rate = 0.8

        from app.views.base import _inject_global_context

        ctx: dict = {}
        _inject_global_context(ctx)

        assert ctx["sentry_environment"] == "staging"
        assert ctx["sentry_js_traces_sample_rate"] == 0.5
        assert ctx["sentry_js_replay_session_sample_rate"] == 0.2
        assert ctx["sentry_js_replay_on_error_sample_rate"] == 0.8

    def test_js_sample_rates_default_values(self, mocker):
        """Browser SDK sample rates fall back to safe defaults when attrs are absent."""
        mock_settings = mocker.patch("app.views.base.settings")
        # Simulate settings object without the new JS attributes
        del mock_settings.sentry_js_traces_sample_rate
        del mock_settings.sentry_js_replay_session_sample_rate
        del mock_settings.sentry_js_replay_on_error_sample_rate
        mock_settings.sentry_dsn = None
        mock_settings.sentry_environment = "production"

        from app.views.base import _inject_global_context

        ctx: dict = {}
        _inject_global_context(ctx)

        assert ctx["sentry_js_traces_sample_rate"] == 0.0
        assert ctx["sentry_js_replay_session_sample_rate"] == 0.0
        assert ctx["sentry_js_replay_on_error_sample_rate"] == 0.1


_MINIMAL_SETTINGS_KWARGS = {
    "database_url": "sqlite:///./test.db",
    "redis_url": "redis://localhost:6379",
    "openai_api_key": "test",
    "azure_ai_key": "test",
    "azure_region": "test",
    "azure_endpoint": "https://test.example.com",
    "gotenberg_url": "http://localhost:3000",
    "workdir": "/tmp",
    "auth_enabled": False,
    "session_secret": "a-test-secret-that-is-at-least-32-chars-long!",
}


@pytest.mark.unit
class TestSentryJsConfig:
    """Test the new JS-specific Settings fields."""

    def test_js_traces_sample_rate_default(self):
        """SENTRY_JS_TRACES_SAMPLE_RATE defaults to 0.0."""
        from app.config import settings

        assert settings.sentry_js_traces_sample_rate == 0.0

    def test_js_replay_session_sample_rate_default(self):
        """SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE defaults to 0.0."""
        from app.config import settings

        assert settings.sentry_js_replay_session_sample_rate == 0.0

    def test_js_replay_on_error_sample_rate_default(self):
        """SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE defaults to 0.1."""
        from app.config import settings

        assert settings.sentry_js_replay_on_error_sample_rate == 0.1

    def test_js_traces_sample_rate_can_be_set(self):
        """SENTRY_JS_TRACES_SAMPLE_RATE can be set directly via constructor."""
        from app.config import Settings

        s = Settings(**_MINIMAL_SETTINGS_KWARGS, sentry_js_traces_sample_rate=0.5)
        assert s.sentry_js_traces_sample_rate == 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
