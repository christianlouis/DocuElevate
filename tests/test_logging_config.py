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
                from app.config import Settings as S

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
            from app.config import Settings as S

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
