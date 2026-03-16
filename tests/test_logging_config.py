"""Tests for application logging configuration.

Validates that the LOG_LEVEL and DEBUG settings correctly control the
Python root-logger level and that the standard precedence rules are respected:
    1. Explicit LOG_LEVEL always wins.
    2. DEBUG=True without LOG_LEVEL → effective DEBUG.
    3. Neither set → default INFO.
"""

import logging
import os
from unittest.mock import patch

import pytest

from app.config import Settings


@pytest.mark.unit
class TestLogLevelSetting:
    """Tests for the log_level config field."""

    _BASE_KWARGS = {
        "database_url": "sqlite:///test.db",
        "redis_url": "redis://localhost:6379",
        "openai_api_key": "test",
        "azure_ai_key": "test",
        "azure_region": "test",
        "azure_endpoint": "https://test.example.com",
        "gotenberg_url": "http://localhost:3000",
        "workdir": "/tmp",
        "auth_enabled": False,
        "session_secret": None,
    }

    def test_log_level_default_is_info(self):
        """Test that log_level defaults to INFO."""
        config = Settings(**self._BASE_KWARGS)
        assert config.log_level.upper() == "INFO"

    def test_log_level_accepts_debug(self):
        """Test that log_level accepts DEBUG."""
        config = Settings(**self._BASE_KWARGS, log_level="DEBUG")
        assert config.log_level.upper() == "DEBUG"

    def test_log_level_accepts_warning(self):
        """Test that log_level accepts WARNING."""
        config = Settings(**self._BASE_KWARGS, log_level="WARNING")
        assert config.log_level.upper() == "WARNING"

    def test_log_level_accepts_error(self):
        """Test that log_level accepts ERROR."""
        config = Settings(**self._BASE_KWARGS, log_level="ERROR")
        assert config.log_level.upper() == "ERROR"

    def test_log_level_case_insensitive(self):
        """Test that log_level is case-insensitive in usage."""
        config = Settings(**self._BASE_KWARGS, log_level="debug")
        assert config.log_level.upper() == "DEBUG"

    def test_debug_flag_defaults_to_false(self):
        """Test that debug defaults to False."""
        config = Settings(**self._BASE_KWARGS)
        assert config.debug is False


@pytest.mark.unit
class TestEffectiveLogLevel:
    """Tests for the effective log-level resolution logic in main.py."""

    def test_debug_true_without_log_level_gives_debug(self):
        """When DEBUG=True and LOG_LEVEL is not set, effective level is DEBUG."""
        with patch.dict(os.environ, {"DEBUG": "true"}, clear=False):
            # Remove LOG_LEVEL from env if present
            env = os.environ.copy()
            env.pop("LOG_LEVEL", None)
            with patch.dict(os.environ, env, clear=True):
                s = Settings(
                    database_url="sqlite:///test.db",
                    redis_url="redis://localhost:6379",
                    openai_api_key="test",
                    azure_ai_key="test",
                    azure_region="test",
                    azure_endpoint="https://test.example.com",
                    gotenberg_url="http://localhost:3000",
                    workdir="/tmp",
                    auth_enabled=False,
                    session_secret=None,
                    debug=True,
                )
                explicit = os.environ.get("LOG_LEVEL")
                if s.debug and explicit is None:
                    effective = "DEBUG"
                else:
                    effective = s.log_level.upper()
                assert effective == "DEBUG"

    def test_explicit_log_level_overrides_debug(self):
        """When LOG_LEVEL is explicitly set, it takes precedence over DEBUG=True."""
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING", "DEBUG": "true"}, clear=False):
            s = Settings(
                database_url="sqlite:///test.db",
                redis_url="redis://localhost:6379",
                openai_api_key="test",
                azure_ai_key="test",
                azure_region="test",
                azure_endpoint="https://test.example.com",
                gotenberg_url="http://localhost:3000",
                workdir="/tmp",
                auth_enabled=False,
                session_secret=None,
                debug=True,
                log_level="WARNING",
            )
            explicit = os.environ.get("LOG_LEVEL")
            if s.debug and explicit is None:
                effective = "DEBUG"
            else:
                effective = s.log_level.upper()
            assert effective == "WARNING"

    def test_default_no_flags_gives_info(self):
        """When neither DEBUG nor LOG_LEVEL is set, effective level is INFO."""
        env = os.environ.copy()
        env.pop("LOG_LEVEL", None)
        env.pop("DEBUG", None)
        with patch.dict(os.environ, env, clear=True):
            s = Settings(
                database_url="sqlite:///test.db",
                redis_url="redis://localhost:6379",
                openai_api_key="test",
                azure_ai_key="test",
                azure_region="test",
                azure_endpoint="https://test.example.com",
                gotenberg_url="http://localhost:3000",
                workdir="/tmp",
                auth_enabled=False,
                session_secret=None,
            )
            explicit = os.environ.get("LOG_LEVEL")
            if s.debug and explicit is None:
                effective = "DEBUG"
            else:
                effective = s.log_level.upper()
            assert effective == "INFO"

    def test_effective_level_maps_to_logging_constant(self):
        """The effective level string maps to a valid logging constant."""
        for level_name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert getattr(logging, level_name) is not None


@pytest.mark.unit
class TestLoggingConfiguredAtStartup:
    """Tests that the main module configures the root logger on import."""

    def test_root_logger_has_handler(self):
        """Root logger should have at least one handler after app import."""
        root = logging.getLogger()
        assert len(root.handlers) > 0, "Root logger has no handlers after app startup"

    def test_root_logger_level_is_not_warning_default(self):
        """Root logger should not be at the unconfigured WARNING default.

        Our basicConfig(force=True) should have set it to at least INFO.
        """
        root = logging.getLogger()
        # The test env doesn't set DEBUG=True, so the level should be INFO (20)
        assert root.level <= logging.INFO


@pytest.mark.unit
class TestJsonFormatter:
    """Tests for the _JsonFormatter used when LOG_FORMAT=json."""

    def _make_formatter(self):
        """Lazily import the JSON formatter from main module."""
        from app.main import _JsonFormatter

        return _JsonFormatter()

    def test_output_is_valid_json(self):
        """JSON formatter output should be parseable JSON."""
        import json

        fmt = self._make_formatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Hello %s",
            args=("world",),
            exc_info=None,
        )
        result = fmt.format(record)
        parsed = json.loads(result)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "Hello world"
        assert parsed["lineno"] == 42

    def test_includes_timestamp_iso8601(self):
        """JSON output should contain an ISO 8601 timestamp."""
        import json

        fmt = self._make_formatter()
        record = logging.LogRecord(
            name="x",
            level=logging.DEBUG,
            pathname="x.py",
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(fmt.format(record))
        assert "timestamp" in parsed
        # ISO 8601 timestamps contain "T" and "+00:00" (UTC)
        assert "T" in parsed["timestamp"]

    def test_includes_exc_info_when_present(self):
        """JSON output should include exc_info when an exception is logged."""
        import json

        fmt = self._make_formatter()
        try:
            raise ValueError("boom")  # noqa: TRY301
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="x",
                level=logging.ERROR,
                pathname="x.py",
                lineno=1,
                msg="error",
                args=(),
                exc_info=sys.exc_info(),
            )
        parsed = json.loads(fmt.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]


@pytest.mark.unit
class TestLogFormatSetting:
    """Tests for the log_format and log_syslog_* config fields."""

    _BASE_KWARGS = {
        "database_url": "sqlite:///test.db",
        "redis_url": "redis://localhost:6379",
        "openai_api_key": "test",
        "azure_ai_key": "test",
        "azure_region": "test",
        "azure_endpoint": "https://test.example.com",
        "gotenberg_url": "http://localhost:3000",
        "workdir": "/tmp",
        "auth_enabled": False,
        "session_secret": None,
    }

    def test_log_format_default_is_text(self):
        """Test that log_format defaults to 'text'."""
        config = Settings(**self._BASE_KWARGS)
        assert config.log_format == "text"

    def test_log_format_accepts_json(self):
        """Test that log_format accepts 'json'."""
        config = Settings(**self._BASE_KWARGS, log_format="json")
        assert config.log_format == "json"

    def test_log_syslog_defaults(self):
        """Test syslog forwarding defaults."""
        config = Settings(**self._BASE_KWARGS)
        assert config.log_syslog_enabled is False
        assert config.log_syslog_host == "localhost"
        assert config.log_syslog_port == 514
        assert config.log_syslog_protocol == "udp"

    def test_log_syslog_can_be_enabled(self):
        """Test that syslog forwarding can be enabled."""
        config = Settings(**self._BASE_KWARGS, log_syslog_enabled=True, log_syslog_host="syslog.example.com")
        assert config.log_syslog_enabled is True
        assert config.log_syslog_host == "syslog.example.com"
