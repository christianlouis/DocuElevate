#!/usr/bin/env python3

"""
Tests for AuditLogMiddleware and associated helper functions.

Validates:
- Sensitive query-parameter masking
- Client-IP extraction
- Username extraction from session
- Middleware initialisation (enabled / disabled)
- Audit log entries for normal requests
- Elevated security-event log entries for 401 / 403 / 5xx responses
  and for authentication-endpoint POST requests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Response

from app.middleware.audit_log import (
    AuditLogMiddleware,
    get_client_ip,
    get_username,
    mask_query_string,
)


# ---------------------------------------------------------------------------
# mask_query_string
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMaskQueryString:
    """Tests for the mask_query_string helper."""

    def test_empty_string_returns_empty(self):
        assert mask_query_string("") == ""

    def test_non_sensitive_param_unchanged(self):
        assert mask_query_string("page=2&limit=10") == "page=2&limit=10"

    def test_password_param_masked(self):
        result = mask_query_string("user=alice&password=secret123")
        assert "secret123" not in result
        assert "password=[REDACTED]" in result
        assert "user=alice" in result

    def test_token_param_masked(self):
        result = mask_query_string("access_token=abc123&foo=bar")
        assert "abc123" not in result
        assert "access_token=[REDACTED]" in result

    def test_multiple_sensitive_params_all_masked(self):
        result = mask_query_string("key=mykey&secret=mysecret&name=test")
        assert "mykey" not in result
        assert "mysecret" not in result
        assert "key=[REDACTED]" in result
        assert "secret=[REDACTED]" in result
        assert "name=test" in result

    def test_case_insensitive_masking(self):
        result = mask_query_string("PASSWORD=topsecret")
        assert "topsecret" not in result
        assert "PASSWORD=[REDACTED]" in result

    def test_param_without_value(self):
        """A bare param name (no '=') should be left as-is."""
        result = mask_query_string("flag")
        assert result == "flag"

    def test_api_key_masked(self):
        result = mask_query_string("api_key=supersecret&query=docs")
        assert "supersecret" not in result
        assert "api_key=[REDACTED]" in result

    def test_refresh_token_masked(self):
        result = mask_query_string("refresh_token=r3fr3sh")
        assert "r3fr3sh" not in result
        assert "refresh_token=[REDACTED]" in result

    def test_non_sensitive_value_not_masked(self):
        result = mask_query_string("username=alice&page=1")
        assert result == "username=alice&page=1"


# ---------------------------------------------------------------------------
# get_client_ip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetClientIp:
    """Tests for the get_client_ip helper."""

    def _make_request(self, headers=None, client_host=None):
        req = MagicMock()
        req.headers = headers or {}
        if client_host:
            req.client = MagicMock()
            req.client.host = client_host
        else:
            req.client = None
        return req

    def test_returns_forwarded_for_first_ip(self):
        req = self._make_request(
            headers={"x-forwarded-for": "203.0.113.1, 10.0.0.1"},
            client_host="10.0.0.1",
        )
        assert get_client_ip(req) == "203.0.113.1"

    def test_falls_back_to_client_host(self):
        req = self._make_request(client_host="192.168.1.42")
        assert get_client_ip(req) == "192.168.1.42"

    def test_returns_unknown_when_no_client(self):
        req = self._make_request()
        assert get_client_ip(req) == "unknown"

    def test_single_forwarded_for_value(self):
        req = self._make_request(headers={"x-forwarded-for": "1.2.3.4"})
        assert get_client_ip(req) == "1.2.3.4"


# ---------------------------------------------------------------------------
# get_username
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetUsername:
    """Tests for the get_username helper."""

    def _make_request(self, session_user=None, has_session=True):
        req = MagicMock()
        if has_session:
            req.session = {"user": session_user} if session_user is not None else {}
        else:
            del req.session
        return req

    def test_returns_anonymous_when_no_session(self):
        req = self._make_request(has_session=False)
        assert get_username(req) == "anonymous"

    def test_returns_anonymous_when_user_not_in_session(self):
        req = self._make_request(session_user=None)
        assert get_username(req) == "anonymous"

    def test_returns_preferred_username(self):
        req = self._make_request(session_user={"preferred_username": "alice", "email": "alice@example.com"})
        assert get_username(req) == "alice"

    def test_falls_back_to_email(self):
        req = self._make_request(session_user={"email": "bob@example.com"})
        assert get_username(req) == "bob@example.com"

    def test_falls_back_to_id(self):
        req = self._make_request(session_user={"id": "admin"})
        assert get_username(req) == "admin"

    def test_returns_anonymous_for_empty_dict(self):
        req = self._make_request(session_user={})
        assert get_username(req) == "anonymous"

    def test_returns_string_for_non_dict_user(self):
        req = self._make_request(session_user="some_user")
        assert get_username(req) == "some_user"


# ---------------------------------------------------------------------------
# AuditLogMiddleware initialisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuditLogMiddlewareInit:
    """Tests for AuditLogMiddleware.__init__."""

    def _make_config(self, enabled=True, include_ip=True):
        cfg = MagicMock()
        cfg.audit_logging_enabled = enabled
        cfg.audit_log_include_client_ip = include_ip
        return cfg

    def test_middleware_enabled_flag(self):
        mw = AuditLogMiddleware(app=None, config=self._make_config(enabled=True))
        assert mw.enabled is True

    def test_middleware_disabled_flag(self):
        mw = AuditLogMiddleware(app=None, config=self._make_config(enabled=False))
        assert mw.enabled is False

    def test_include_ip_flag(self):
        mw = AuditLogMiddleware(app=None, config=self._make_config(include_ip=True))
        assert mw.include_ip is True

    def test_exclude_ip_flag(self):
        mw = AuditLogMiddleware(app=None, config=self._make_config(include_ip=False))
        assert mw.include_ip is False


# ---------------------------------------------------------------------------
# AuditLogMiddleware.dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuditLogMiddlewareDispatch:
    """Tests for AuditLogMiddleware.dispatch."""

    def _make_middleware(self, enabled=True, include_ip=True):
        cfg = MagicMock()
        cfg.audit_logging_enabled = enabled
        cfg.audit_log_include_client_ip = include_ip
        return AuditLogMiddleware(app=None, config=cfg)

    def _make_request(self, path="/test", query="", method="GET", session_user=None):
        req = MagicMock()
        req.method = method
        req.url.path = path
        req.url.query = query
        req.headers = {}
        req.client = MagicMock()
        req.client.host = "127.0.0.1"
        req.session = {"user": session_user} if session_user else {}
        return req

    @pytest.mark.asyncio
    async def test_disabled_middleware_passes_through(self):
        mw = self._make_middleware(enabled=False)
        mock_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=mock_response)

        req = self._make_request()
        result = await mw.dispatch(req, call_next)

        assert result is mock_response
        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_enabled_middleware_logs_request(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/api/test", method="GET")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        # At least one info call should contain [AUDIT]
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("[AUDIT]" in c for c in info_calls)

    @pytest.mark.asyncio
    async def test_sensitive_query_param_masked_in_log(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/search", query="q=hello&password=supersecret")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        all_calls = " ".join(str(c) for c in mock_logger.info.call_args_list)
        assert "supersecret" not in all_calls
        assert "[REDACTED]" in all_calls

    @pytest.mark.asyncio
    async def test_401_triggers_security_warning(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="unauth", status_code=401)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/api/protected")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("AUTH_FAILURE" in c for c in warning_calls)

    @pytest.mark.asyncio
    async def test_403_triggers_security_warning(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="forbidden", status_code=403)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/admin")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
        assert any("ACCESS_DENIED" in c for c in warning_calls)

    @pytest.mark.asyncio
    async def test_5xx_triggers_security_error(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="error", status_code=500)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/api/crash")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("SERVER_ERROR" in c for c in error_calls)

    @pytest.mark.asyncio
    async def test_login_post_triggers_auth_attempt_log(self):
        mw = self._make_middleware(enabled=True)
        mock_response = Response(content="ok", status_code=302)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request(path="/auth", method="POST")

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("AUTH_ATTEMPT" in c for c in info_calls)

    @pytest.mark.asyncio
    async def test_ip_included_in_log_when_enabled(self):
        mw = self._make_middleware(enabled=True, include_ip=True)
        mock_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request()

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        # 127.0.0.1 should appear somewhere in the log
        assert any("127.0.0.1" in c for c in info_calls)

    @pytest.mark.asyncio
    async def test_ip_excluded_from_log_when_disabled(self):
        mw = self._make_middleware(enabled=True, include_ip=False)
        mock_response = Response(content="ok", status_code=200)
        call_next = AsyncMock(return_value=mock_response)
        req = self._make_request()

        with patch("app.middleware.audit_log.logger") as mock_logger:
            await mw.dispatch(req, call_next)

        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert not any("127.0.0.1" in c for c in info_calls)


# ---------------------------------------------------------------------------
# Configuration settings
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuditLoggingConfiguration:
    """Tests that the audit logging settings are present in the app config."""

    def test_audit_logging_enabled_setting_exists(self):
        from app.config import settings

        assert hasattr(settings, "audit_logging_enabled")
        assert isinstance(settings.audit_logging_enabled, bool)

    def test_audit_log_include_client_ip_setting_exists(self):
        from app.config import settings

        assert hasattr(settings, "audit_log_include_client_ip")
        assert isinstance(settings.audit_log_include_client_ip, bool)

    def test_audit_logging_enabled_by_default(self):
        from app.config import Settings

        # Instantiate with only the required minimal fields
        s = Settings(
            database_url="sqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
        )
        assert s.audit_logging_enabled is True

    def test_audit_log_include_client_ip_enabled_by_default(self):
        from app.config import Settings

        s = Settings(
            database_url="sqlite:///:memory:",
            redis_url="redis://localhost:6379/0",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
        )
        assert s.audit_log_include_client_ip is True
