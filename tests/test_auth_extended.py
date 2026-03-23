"""Extended tests for app/auth.py to improve coverage.

Covers:
- get_current_user with server-side session validation
- _resolve_bearer_user function
- get_current_user_id
- require_login Bearer token paths
- login() mobile redirect handling
- social_login() function
- _normalize_social_userinfo() function
- social_callback() function
- _ensure_user_profile admin update logic
- oauth_callback session token + mobile/onboarding paths
- _record_login_event exception handling
- _create_mobile_redirect() function
- auth() local user paths and multi-user mode
- auth() admin mobile redirect
- logout() session token revocation
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from starlette.responses import RedirectResponse

# ---------------------------------------------------------------------------
# get_current_user — server-side session validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentUserSessionValidation:
    """Tests for get_current_user with server-side session tokens."""

    def test_valid_server_session_returns_user(self):
        """Valid _session_token should keep the user in session and return them."""
        from app.auth import get_current_user

        mock_request = MagicMock(spec=Request)
        user = {"id": "u1", "preferred_username": "alice"}
        mock_request.session = {"user": user, "_session_token": "valid-token"}

        mock_session_obj = MagicMock()  # truthy — session is valid

        with (
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.utils.session_manager.validate_session", return_value=mock_session_obj),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            result = get_current_user(mock_request)

        assert result == user

    def test_invalid_server_session_clears_user(self):
        """When validate_session returns None the session is cleared and None is returned."""
        from app.auth import get_current_user

        mock_request = MagicMock(spec=Request)
        user = {"id": "u1", "preferred_username": "alice"}
        mock_request.session = {"user": user, "_session_token": "expired-token"}

        with (
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.utils.session_manager.validate_session", return_value=None),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            result = get_current_user(mock_request)

        assert result is None
        assert "user" not in mock_request.session
        assert "_session_token" not in mock_request.session

    def test_session_validation_exception_returns_user(self):
        """If validate_session raises, the error is swallowed and the user is returned."""
        from app.auth import get_current_user

        mock_request = MagicMock(spec=Request)
        user = {"id": "u1", "preferred_username": "alice"}
        mock_request.session = {"user": user, "_session_token": "token"}

        with (
            patch("app.database.SessionLocal") as mock_session_local,
            patch("app.utils.session_manager.validate_session", side_effect=RuntimeError("db down")),
        ):
            mock_db = MagicMock()
            mock_session_local.return_value = mock_db

            result = get_current_user(mock_request)

        # Exception must be swallowed; the user is still returned
        assert result == user


# ---------------------------------------------------------------------------
# _resolve_bearer_user
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveBearerUser:
    """Tests for _resolve_bearer_user()."""

    def _make_db(self, token_obj=None):
        """Return a mock db whose query chain yields *token_obj*."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = token_obj
        return mock_db

    def _make_request(self, auth_header: str = "", client_ip: str = "1.2.3.4"):
        """Return a mock request with the given Authorization header."""
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"authorization": auth_header, "x-forwarded-for": client_ip}
        mock_request.client = MagicMock()
        mock_request.client.host = client_ip
        return mock_request

    def test_no_bearer_header_returns_none(self):
        """Missing Authorization header returns None."""
        from app.auth import _resolve_bearer_user

        result = _resolve_bearer_user(self._make_request(), self._make_db())
        assert result is None

    def test_wrong_scheme_returns_none(self):
        """Authorization header not starting with 'Bearer ' returns None."""
        from app.auth import _resolve_bearer_user

        result = _resolve_bearer_user(self._make_request("Basic abc123"), self._make_db())
        assert result is None

    def test_empty_token_after_prefix_returns_none(self):
        """'Bearer ' with empty token returns None."""
        from app.auth import _resolve_bearer_user

        result = _resolve_bearer_user(self._make_request("Bearer "), self._make_db())
        assert result is None

    def test_no_matching_token_returns_none(self):
        """Token hash not found in DB returns None."""
        from app.auth import _resolve_bearer_user

        with patch("app.api.api_tokens.hash_token", return_value="deadbeef"):
            result = _resolve_bearer_user(self._make_request("Bearer mytoken"), self._make_db(None))

        assert result is None

    def test_valid_token_returns_user_dict(self):
        """Valid active token returns synthetic user dict."""
        from app.auth import _resolve_bearer_user

        mock_token = MagicMock()
        mock_token.id = 1
        mock_token.owner_id = "alice@example.com"
        mock_token.expires_at = None
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(self._make_request("Bearer plaintext"), mock_db)

        assert result is not None
        assert result["id"] == "alice@example.com"
        assert result["email"] == "alice@example.com"
        assert result["is_admin"] is False
        assert result["_api_token_id"] == 1

    def test_expired_token_returns_none(self):
        """Token past its expiry datetime is rejected."""
        from app.auth import _resolve_bearer_user

        expired = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_token = MagicMock()
        mock_token.id = 2
        mock_token.owner_id = "bob@example.com"
        mock_token.expires_at = expired
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(self._make_request("Bearer plaintext"), mock_db)

        assert result is None

    def test_expired_token_naive_datetime_returns_none(self):
        """Token with timezone-naive expires_at in the past is rejected."""
        from app.auth import _resolve_bearer_user

        # naive datetime far in the past
        expired_naive = datetime(2020, 1, 1)  # no tzinfo
        mock_token = MagicMock()
        mock_token.id = 3
        mock_token.owner_id = "carol@example.com"
        mock_token.expires_at = expired_naive
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(self._make_request("Bearer plaintext"), mock_db)

        assert result is None

    def test_future_expiry_token_accepted(self):
        """Token with future expires_at is accepted."""
        from app.auth import _resolve_bearer_user

        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        mock_token = MagicMock()
        mock_token.id = 4
        mock_token.owner_id = "dave@example.com"
        mock_token.expires_at = future
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(self._make_request("Bearer plaintext"), mock_db)

        assert result is not None
        assert result["id"] == "dave@example.com"

    def test_update_tracking_exception_still_returns_user(self):
        """If db.commit() fails during usage tracking, the token user is still returned."""
        from app.auth import _resolve_bearer_user

        mock_token = MagicMock()
        mock_token.id = 5
        mock_token.owner_id = "eve@example.com"
        mock_token.expires_at = None
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)
        mock_db.commit.side_effect = Exception("DB write error")

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(self._make_request("Bearer plaintext"), mock_db)

        assert result is not None
        assert result["id"] == "eve@example.com"
        mock_db.rollback.assert_called_once()

    def test_x_forwarded_for_header_used_for_ip(self):
        """IP is extracted from X-Forwarded-For when present."""
        from app.auth import _resolve_bearer_user

        mock_token = MagicMock()
        mock_token.id = 6
        mock_token.owner_id = "frank@example.com"
        mock_token.expires_at = None
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "authorization": "Bearer plaintoken",
            "x-forwarded-for": "10.0.0.1, 192.168.1.1",
        }
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(mock_request, mock_db)

        assert result is not None
        assert mock_token.last_used_ip == "10.0.0.1"

    def test_no_client_and_no_forwarded_for(self):
        """Falls back to None IP when no forwarded-for and no client."""
        from app.auth import _resolve_bearer_user

        mock_token = MagicMock()
        mock_token.id = 7
        mock_token.owner_id = "grace@example.com"
        mock_token.expires_at = None
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"authorization": "Bearer plaintoken", "x-forwarded-for": ""}
        mock_request.client = None  # no client

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(mock_request, mock_db)

        assert result is not None
        assert mock_token.last_used_ip is None

    def test_no_forwarded_for_but_client_exists(self):
        """Falls back to request.client.host when x-forwarded-for is absent/empty."""
        from app.auth import _resolve_bearer_user

        mock_token = MagicMock()
        mock_token.id = 8
        mock_token.owner_id = "holly@example.com"
        mock_token.expires_at = None
        mock_token.is_active = True

        mock_db = self._make_db(mock_token)

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"authorization": "Bearer plaintoken", "x-forwarded-for": ""}
        mock_client = MagicMock()
        mock_client.host = "10.10.10.1"
        mock_request.client = mock_client  # client exists

        with patch("app.api.api_tokens.hash_token", return_value="abc123"):
            result = _resolve_bearer_user(mock_request, mock_db)

        assert result is not None
        assert mock_token.last_used_ip == "10.10.10.1"


# ---------------------------------------------------------------------------
# get_current_user_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetCurrentUserId:
    """Tests for get_current_user_id()."""

    def test_returns_anonymous_when_no_user(self):
        """Returns 'anonymous' when there is no session user."""
        from app.auth import get_current_user_id

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.state = MagicMock(spec=[])

        result = get_current_user_id(mock_request)
        assert result == "anonymous"

    def test_returns_preferred_username(self):
        """Returns preferred_username when available."""
        from app.auth import get_current_user_id

        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"preferred_username": "alice", "email": "a@e.com", "id": "1"}}

        result = get_current_user_id(mock_request)
        assert result == "alice"

    def test_falls_back_to_email(self):
        """Falls back to email when preferred_username is absent."""
        from app.auth import get_current_user_id

        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"email": "bob@example.com", "id": "2"}}

        result = get_current_user_id(mock_request)
        assert result == "bob@example.com"

    def test_falls_back_to_id(self):
        """Falls back to id when preferred_username and email are absent."""
        from app.auth import get_current_user_id

        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"id": "user-123"}}

        result = get_current_user_id(mock_request)
        assert result == "user-123"

    def test_returns_anonymous_when_all_fields_missing(self):
        """Returns 'anonymous' when user dict has no identifier fields."""
        from app.auth import get_current_user_id

        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"name": "No Fields"}}

        result = get_current_user_id(mock_request)
        assert result == "anonymous"


# ---------------------------------------------------------------------------
# require_login — Bearer token paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireLoginBearer:
    """Tests for require_login Bearer token authentication on /api/ paths."""

    @pytest.mark.asyncio
    async def test_bearer_token_auth_allows_async_endpoint(self):
        """Valid Bearer token authenticates an async /api/ endpoint."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def api_endpoint(request: Request):
                return {"user": request.state.api_token_user}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = MagicMock()
            mock_request.url.__str__ = MagicMock(return_value="http://test.com/api/files")

            api_user = {"id": "tok_user", "email": "tok_user"}

            with (
                patch("app.database.SessionLocal") as mock_sl,
                patch("app.auth._resolve_bearer_user", return_value=api_user),
            ):
                mock_db = MagicMock()
                mock_sl.return_value = mock_db

                result = await api_endpoint(mock_request)

            assert result["user"] == api_user
            assert mock_request.state.api_token_user == api_user

    @pytest.mark.asyncio
    async def test_bearer_token_auth_allows_sync_endpoint(self):
        """Valid Bearer token authenticates a sync /api/ endpoint."""
        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            def api_endpoint(request: Request):
                return {"user": request.state.api_token_user}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = MagicMock()
            mock_request.url.__str__ = MagicMock(return_value="http://test.com/api/upload")

            api_user = {"id": "tok_user_sync", "email": "tok_user_sync"}

            with (
                patch("app.database.SessionLocal") as mock_sl,
                patch("app.auth._resolve_bearer_user", return_value=api_user),
            ):
                mock_db = MagicMock()
                mock_sl.return_value = mock_db

                result = await api_endpoint(mock_request)

            assert result["user"] == api_user

    @pytest.mark.asyncio
    async def test_bearer_db_exception_returns_401(self):
        """Exception during db setup falls back to 401 for /api/ paths."""
        from fastapi.responses import JSONResponse

        with patch("app.auth.AUTH_ENABLED", True):
            from app.auth import require_login

            @require_login
            async def api_endpoint(request: Request):
                return {"ok": True}

            mock_request = MagicMock(spec=Request)
            mock_request.session = {}
            mock_request.url = MagicMock()
            mock_request.url.__str__ = MagicMock(return_value="http://test.com/api/files")

            with patch("app.database.SessionLocal", side_effect=Exception("db error")):
                result = await api_endpoint(mock_request)

            assert isinstance(result, JSONResponse)
            assert result.status_code == 401


# ---------------------------------------------------------------------------
# login() — mobile redirect handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoginMobileRedirect:
    """Tests for the mobile redirect handling inside login()."""

    @pytest.mark.asyncio
    async def test_mobile_flag_with_docuelevate_scheme_stores_uri(self):
        """mobile=1 with a docuelevate:// redirect_uri stores it in the session."""
        from app.auth import login

        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"mobile": "1", "redirect_uri": "docuelevate://callback"}
        mock_request.session = {}

        with patch("app.auth.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = "page"
            await login(mock_request)

        assert mock_request.session.get("mobile_redirect_uri") == "docuelevate://callback"

    @pytest.mark.asyncio
    async def test_mobile_flag_with_exp_scheme_stores_uri(self):
        """mobile=1 with an exp:// redirect_uri (Expo Go) stores it in the session."""
        from app.auth import login

        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"mobile": "1", "redirect_uri": "exp://192.168.1.1:19000/--/auth"}
        mock_request.session = {}

        with patch("app.auth.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = "page"
            await login(mock_request)

        assert mock_request.session.get("mobile_redirect_uri") == "exp://192.168.1.1:19000/--/auth"

    @pytest.mark.asyncio
    async def test_mobile_flag_with_http_scheme_is_rejected(self):
        """mobile=1 with an http:// redirect_uri (open-redirect risk) is not stored."""
        from app.auth import login

        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"mobile": "1", "redirect_uri": "http://evil.example.com/phish"}
        mock_request.session = {}

        with patch("app.auth.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = "page"
            await login(mock_request)

        assert "mobile_redirect_uri" not in mock_request.session

    @pytest.mark.asyncio
    async def test_no_mobile_flag_does_not_set_uri(self):
        """Standard browser login (no mobile=1) does not store a mobile redirect URI."""
        from app.auth import login

        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {}
        mock_request.session = {}

        with patch("app.auth.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = "page"
            await login(mock_request)

        assert "mobile_redirect_uri" not in mock_request.session

    @pytest.mark.asyncio
    async def test_mobile_flag_with_empty_redirect_uri_is_rejected(self):
        """mobile=1 with an empty redirect_uri is silently ignored."""
        from app.auth import login

        mock_request = MagicMock(spec=Request)
        mock_request.query_params = {"mobile": "1", "redirect_uri": ""}
        mock_request.session = {}

        with patch("app.auth.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = "page"
            await login(mock_request)

        assert "mobile_redirect_uri" not in mock_request.session


# ---------------------------------------------------------------------------
# social_login()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSocialLogin:
    """Tests for social_login()."""

    @pytest.mark.asyncio
    async def test_unknown_provider_redirects(self):
        """Unknown social provider returns redirect to /login?error=..."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)

        with patch("app.auth.SOCIAL_PROVIDERS", {}):
            result = await social_login(mock_request, provider="unknown")

        assert isinstance(result, RedirectResponse)
        assert "Unknown+social+provider" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_registered_provider_oauth_client_missing_redirects(self):
        """Provider is registered but OAuth client not initialised → redirect."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)
        mock_request.url_for = MagicMock(return_value="http://localhost/social-callback/google")

        fake_providers = {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}

        mock_oauth = MagicMock(spec=[])  # no attributes

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_login(mock_request, provider="google")

        assert isinstance(result, RedirectResponse)
        assert "Provider+not+configured" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_registered_provider_initiates_oauth(self):
        """Registered provider with OAuth client initiates the OAuth redirect."""
        from app.auth import social_login

        mock_request = MagicMock(spec=Request)
        mock_request.url_for = MagicMock(return_value="http://localhost/social-callback/google")

        fake_providers = {"google": {"name": "Google", "icon": "fab fa-google", "color": "red"}}

        mock_google_client = MagicMock()
        mock_google_client.authorize_redirect = AsyncMock(return_value="oauth_redirect")

        mock_oauth = MagicMock()
        mock_oauth.google = mock_google_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_login(mock_request, provider="google")

        assert result == "oauth_redirect"
        mock_google_client.authorize_redirect.assert_called_once()


# ---------------------------------------------------------------------------
# _normalize_social_userinfo()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSocialUserinfo:
    """Tests for _normalize_social_userinfo()."""

    def test_dropbox_provider_normalisation(self):
        """Dropbox userinfo is mapped to the common format."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "account_id": "dbid:ABC123",
            "email": "dan@example.com",
            "name": {"display_name": "Dan Dropbox"},
            "profile_photo_url": "https://cdn.dropbox.com/photo.jpg",
        }

        result = _normalize_social_userinfo("dropbox", {}, raw)

        assert result["sub"] == "dbid:ABC123"
        assert result["email"] == "dan@example.com"
        assert result["name"] == "Dan Dropbox"
        assert result["preferred_username"] == "dan@example.com"
        assert result["picture"] == "https://cdn.dropbox.com/photo.jpg"

    def test_dropbox_string_name_field(self):
        """Dropbox userinfo with a string (not dict) name field is handled."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "account_id": "dbid:XYZ",
            "email": "eve@example.com",
            "name": "Eve String",  # string instead of dict
        }

        result = _normalize_social_userinfo("dropbox", {}, raw)
        assert result["name"] == "Eve String"

    def test_dropbox_no_account_id_falls_back_to_email(self):
        """Dropbox sub falls back to email when account_id is absent."""
        from app.auth import _normalize_social_userinfo

        raw = {"email": "frank@example.com"}
        result = _normalize_social_userinfo("dropbox", {}, raw)
        assert result["sub"] == "frank@example.com"

    def test_google_provider_normalisation(self):
        """Standard OIDC (Google) userinfo is mapped to the common format."""
        from app.auth import _normalize_social_userinfo

        raw = {
            "sub": "google-sub-123",
            "email": "grace@gmail.com",
            "name": "Grace Google",
            "picture": "https://lh3.googleusercontent.com/photo.jpg",
        }

        result = _normalize_social_userinfo("google", {}, raw)

        assert result["sub"] == "google-sub-123"
        assert result["email"] == "grace@gmail.com"
        assert result["preferred_username"] == "grace@gmail.com"
        assert result["picture"] == "https://lh3.googleusercontent.com/photo.jpg"

    def test_standard_provider_empty_userinfo(self):
        """Standard OIDC provider with empty userinfo returns empty strings."""
        from app.auth import _normalize_social_userinfo

        result = _normalize_social_userinfo("microsoft", {}, {})

        assert result["sub"] == ""
        assert result["email"] == ""
        assert result["preferred_username"] == ""

    def test_none_raw_userinfo_treated_as_empty(self):
        """raw_userinfo=None is treated as an empty dict."""
        from app.auth import _normalize_social_userinfo

        result = _normalize_social_userinfo("google", {}, None)

        assert result["sub"] == ""
        assert result["email"] == ""


# ---------------------------------------------------------------------------
# social_callback()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSocialCallback:
    """Tests for social_callback()."""

    @pytest.mark.asyncio
    async def test_unknown_provider_redirects(self):
        """Unknown provider returns immediate redirect."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_db = MagicMock()

        with patch("app.auth.SOCIAL_PROVIDERS", {}):
            result = await social_callback(mock_request, provider="unknown", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "Unknown+social+provider" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_provider_not_configured_redirects(self):
        """Registered provider with no OAuth client returns redirect."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_db = MagicMock()

        fake_providers = {"google": {}}
        mock_oauth = MagicMock(spec=[])

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "Provider+not+configured" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_success_stores_user_in_session(self):
        """Successful callback stores user in session and redirects."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {"user-agent": "TestBrowser/1.0"}
        mock_db = MagicMock()

        token = {"userinfo": {"sub": "g-sub", "email": "g@gmail.com", "name": "Google User"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session") as mock_create_session,
        ):
            mock_user_session = MagicMock()
            mock_user_session.session_token = "tok-abc"
            mock_create_session.return_value = mock_user_session

            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "user" in mock_request.session
        assert mock_request.session["user"]["email"] == "g@gmail.com"

    @pytest.mark.asyncio
    async def test_no_email_redirects(self):
        """Callback with user data missing email returns error redirect."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        token = {"userinfo": {"sub": "g-sub", "name": "No Email"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "Could+not+retrieve+email" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_exception_in_callback_returns_error_redirect(self):
        """Unhandled exception during callback returns error redirect."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(side_effect=Exception("provider error"))

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "Social+login+failed" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_userinfo_fetched_from_endpoint_when_not_in_token(self):
        """When userinfo is not embedded in the token, it's fetched from the endpoint."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {"user-agent": "TestBrowser/1.0"}
        mock_db = MagicMock()

        # Token without embedded userinfo
        token = {}
        userinfo_resp = {"sub": "g-sub", "email": "fetch@gmail.com", "name": "Fetched User"}

        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)
        mock_client.userinfo = AsyncMock(return_value=userinfo_resp)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session"),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert mock_request.session["user"]["email"] == "fetch@gmail.com"

    @pytest.mark.asyncio
    async def test_userinfo_endpoint_exception_falls_back_to_empty(self):
        """If the userinfo endpoint raises, an empty dict is used and missing email → redirect."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        token = {}  # no userinfo embedded
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)
        mock_client.userinfo = AsyncMock(side_effect=Exception("endpoint error"))

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        # no email → redirect with error
        assert isinstance(result, RedirectResponse)
        assert "Could+not+retrieve+email" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_social_callback_adds_gravatar_when_no_picture(self):
        """social_callback adds a Gravatar URL when the provider returns no picture."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        token = {"userinfo": {"sub": "g-sub", "email": "nopic@gmail.com", "name": "No Pic"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session"),
        ):
            await social_callback(mock_request, provider="google", db=mock_db)

        assert mock_request.session["user"].get("picture", "").startswith("https://www.gravatar.com/")

    @pytest.mark.asyncio
    async def test_social_callback_session_token_exception(self):
        """Exception during server-side session creation is swallowed."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        token = {"userinfo": {"sub": "g-sub", "email": "exc@gmail.com"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session", side_effect=Exception("session error")),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        # Should not crash; user still in session
        assert "user" in mock_request.session

    @pytest.mark.asyncio
    async def test_social_callback_mobile_redirect(self):
        """When mobile redirect URI is in session, the mobile redirect is returned."""
        from app.auth import social_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        token = {"userinfo": {"sub": "g-sub", "email": "mob@gmail.com"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        mobile_resp = RedirectResponse(url="docuelevate://callback?token=abc", status_code=302)

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=mobile_resp),
            patch("app.utils.session_manager.create_session"),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert result is mobile_resp

    @pytest.mark.asyncio
    async def test_social_callback_onboarding_redirect(self):
        """First-time users who haven't completed onboarding are sent to /onboarding."""
        from app.auth import social_callback
        from app.models import UserProfile

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        # Simulate incomplete onboarding
        profile = UserProfile(user_id="g-sub", onboarding_completed=False)
        mock_db.query.return_value.filter.return_value.first.return_value = profile

        token = {"userinfo": {"sub": "g-sub", "email": "new@gmail.com"}}
        mock_client = MagicMock()
        mock_client.authorize_access_token = AsyncMock(return_value=token)

        fake_providers = {"google": {"name": "Google", "icon": "", "color": "red"}}
        mock_oauth = MagicMock()
        mock_oauth.google = mock_client

        with (
            patch("app.auth.SOCIAL_PROVIDERS", fake_providers),
            patch("app.auth.oauth", mock_oauth),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session"),
        ):
            result = await social_callback(mock_request, provider="google", db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/onboarding"


# ---------------------------------------------------------------------------
# _ensure_user_profile — admin update logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEnsureUserProfileAdminUpdate:
    """Tests for _ensure_user_profile() admin-specific update logic."""

    def test_admin_sets_complimentary_and_upgrades_free_tier(self):
        """Existing admin profile with is_complimentary=False and free tier gets upgraded."""
        from app.auth import _ensure_user_profile
        from app.models import UserProfile

        mock_db = MagicMock()
        existing = UserProfile(user_id="admin-u", subscription_tier="free", is_complimentary=False)
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with patch("app.utils.subscription.TIER_ORDER", ["free", "pro", "enterprise"]):
            _ensure_user_profile(mock_db, {"sub": "admin-u"}, is_admin=True)

        assert existing.is_complimentary is True
        assert existing.subscription_tier == "enterprise"
        mock_db.commit.assert_called_once()

    def test_admin_already_complimentary_no_free_tier_no_commit(self):
        """Existing admin profile that is already complimentary on a paid tier is left alone."""
        from app.auth import _ensure_user_profile
        from app.models import UserProfile

        mock_db = MagicMock()
        existing = UserProfile(user_id="admin-u2", subscription_tier="enterprise", is_complimentary=True)
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with patch("app.utils.subscription.TIER_ORDER", ["free", "pro", "enterprise"]):
            _ensure_user_profile(mock_db, {"sub": "admin-u2"}, is_admin=True)

        mock_db.commit.assert_not_called()

    def test_admin_complimentary_but_on_free_tier_upgrades(self):
        """Admin profile that is complimentary but still on 'free' tier gets upgraded."""
        from app.auth import _ensure_user_profile
        from app.models import UserProfile

        mock_db = MagicMock()
        existing = UserProfile(user_id="admin-u3", subscription_tier="free", is_complimentary=True)
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        with patch("app.utils.subscription.TIER_ORDER", ["free", "pro", "enterprise"]):
            _ensure_user_profile(mock_db, {"sub": "admin-u3"}, is_admin=True)

        assert existing.subscription_tier == "enterprise"
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# oauth_callback — session token + mobile/onboarding
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOAuthCallbackExtended:
    """Additional tests for oauth_callback()."""

    @pytest.mark.asyncio
    async def test_session_token_stored_when_sub_present(self):
        """oauth_callback stores server-side session token in session dict."""
        from app.auth import oauth_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {"user-agent": "Test/1.0"}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # no profile

        userinfo = {"sub": "oidc-sub", "email": "oidc@example.com"}
        mock_authentik = MagicMock()
        mock_authentik.authorize_access_token = AsyncMock(return_value={"userinfo": userinfo})

        mock_session_obj = MagicMock()
        mock_session_obj.session_token = "server-side-tok"

        with (
            patch("app.auth.oauth") as mock_oauth,
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.auth._record_login_event"),
            patch("app.utils.session_manager.create_session", return_value=mock_session_obj),
        ):
            mock_oauth.authentik = mock_authentik
            mock_settings.admin_group_name = "admin"

            await oauth_callback(mock_request, db=mock_db)

        assert mock_request.session.get("_session_token") == "server-side-tok"

    @pytest.mark.asyncio
    async def test_session_token_exception_is_swallowed(self):
        """Exception during server-side session creation is logged and swallowed."""
        from app.auth import oauth_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        userinfo = {"sub": "oidc-sub2", "email": "oidc2@example.com"}
        mock_authentik = MagicMock()
        mock_authentik.authorize_access_token = AsyncMock(return_value={"userinfo": userinfo})

        with (
            patch("app.auth.oauth") as mock_oauth,
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.auth._record_login_event"),
            patch("app.utils.session_manager.create_session", side_effect=Exception("session create failed")),
        ):
            mock_oauth.authentik = mock_authentik
            mock_settings.admin_group_name = "admin"

            result = await oauth_callback(mock_request, db=mock_db)

        # Should complete without crashing and redirect
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_oauth_callback_mobile_redirect_returned(self):
        """oauth_callback returns mobile redirect when mobile_redirect_uri is in session."""
        from app.auth import oauth_callback

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        userinfo = {"sub": "mob-sub", "email": "mob@example.com"}
        mock_authentik = MagicMock()
        mock_authentik.authorize_access_token = AsyncMock(return_value={"userinfo": userinfo})

        mobile_resp = RedirectResponse(url="docuelevate://callback?token=xyz", status_code=302)

        with (
            patch("app.auth.oauth") as mock_oauth,
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=mobile_resp),
            patch("app.auth._record_login_event"),
            patch("app.utils.session_manager.create_session"),
        ):
            mock_oauth.authentik = mock_authentik
            mock_settings.admin_group_name = "admin"

            result = await oauth_callback(mock_request, db=mock_db)

        assert result is mobile_resp

    @pytest.mark.asyncio
    async def test_oauth_callback_onboarding_redirect(self):
        """oauth_callback sends first-time users to /onboarding."""
        from app.auth import oauth_callback
        from app.models import UserProfile

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_request.headers = {}
        mock_db = MagicMock()

        profile = UserProfile(user_id="new-sub", onboarding_completed=False)
        mock_db.query.return_value.filter.return_value.first.return_value = profile

        userinfo = {"sub": "new-sub", "email": "new@example.com"}
        mock_authentik = MagicMock()
        mock_authentik.authorize_access_token = AsyncMock(return_value={"userinfo": userinfo})

        with (
            patch("app.auth.oauth") as mock_oauth,
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.auth._record_login_event"),
            patch("app.utils.session_manager.create_session"),
        ):
            mock_oauth.authentik = mock_authentik
            mock_settings.admin_group_name = "admin"

            result = await oauth_callback(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/onboarding"


# ---------------------------------------------------------------------------
# _record_login_event — exception handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordLoginEvent:
    """Tests for _record_login_event()."""

    def test_exception_in_record_event_is_swallowed(self):
        """If record_event raises, _record_login_event swallows the error."""
        from app.auth import _record_login_event

        mock_db = MagicMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client = None

        with patch("app.utils.audit_service.record_event", side_effect=Exception("audit DB down")):
            # Must not raise
            _record_login_event(mock_db, mock_request, "alice", success=True)

    def test_records_successful_login(self):
        """Successful login emits a 'login' event with method and no reason."""
        from app.auth import _record_login_event

        mock_db = MagicMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"x-forwarded-for": ""}
        mock_request.client = None

        with patch("app.utils.audit_service.record_event") as mock_record:
            _record_login_event(mock_db, mock_request, "bob", success=True, method="local")

        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs["action"] == "login"
        assert call_kwargs["severity"] == "info"

    def test_records_failed_login_with_detail(self):
        """Failed login emits a 'login.failure' event with the detail reason."""
        from app.auth import _record_login_event

        mock_db = MagicMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"x-forwarded-for": ""}
        mock_request.client = None

        with patch("app.utils.audit_service.record_event") as mock_record:
            _record_login_event(mock_db, mock_request, "carol", success=False, detail="wrong_password")

        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs["action"] == "login.failure"
        assert call_kwargs["severity"] == "warning"
        assert call_kwargs["details"]["reason"] == "wrong_password"


# ---------------------------------------------------------------------------
# _create_mobile_redirect()
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateMobileRedirect:
    """Tests for _create_mobile_redirect()."""

    def test_returns_none_when_no_redirect_uri(self):
        """Returns None when no mobile_redirect_uri is in session."""
        from app.auth import _create_mobile_redirect

        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        mock_db = MagicMock()

        result = _create_mobile_redirect(mock_request, mock_db)
        assert result is None

    def test_returns_none_when_no_owner_id(self):
        """Returns None when user in session has no usable owner identifier."""
        from app.auth import _create_mobile_redirect

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "mobile_redirect_uri": "docuelevate://callback",
            "user": {},  # no sub/preferred_username/email/id
        }
        mock_db = MagicMock()

        result = _create_mobile_redirect(mock_request, mock_db)
        assert result is None

    def test_success_returns_redirect_with_token(self):
        """Successful mobile redirect creates token and returns RedirectResponse."""
        from app.auth import _create_mobile_redirect

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "mobile_redirect_uri": "docuelevate://callback",
            "user": {"sub": "mob-user"},
        }
        mock_request.headers = {}
        mock_db = MagicMock()

        mock_token_obj = MagicMock()
        mock_token_obj.id = 99
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        with (
            patch("app.api.api_tokens.generate_api_token", return_value="plaintexttoken12345"),
            patch("app.api.api_tokens.hash_token", return_value="hashvalue"),
        ):
            result = _create_mobile_redirect(mock_request, mock_db)

        assert isinstance(result, RedirectResponse)
        location = result.headers["location"]
        assert "docuelevate://callback" in location
        assert "token=" in location

    def test_db_commit_exception_returns_none(self):
        """If db.commit() raises when creating the mobile token, returns None."""
        from app.auth import _create_mobile_redirect

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "mobile_redirect_uri": "docuelevate://callback",
            "user": {"email": "mob@example.com"},
        }
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("commit failed")

        with (
            patch("app.api.api_tokens.generate_api_token", return_value="plaintext12345"),
            patch("app.api.api_tokens.hash_token", return_value="hashvalue"),
        ):
            result = _create_mobile_redirect(mock_request, mock_db)

        assert result is None
        mock_db.rollback.assert_called_once()

    def test_existing_query_params_preserved(self):
        """Token is appended correctly when the redirect URI already has query params."""
        from app.auth import _create_mobile_redirect

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "mobile_redirect_uri": "docuelevate://callback?existing=1",
            "user": {"sub": "user1"},
        }
        mock_request.headers = {}
        mock_db = MagicMock()

        with (
            patch("app.api.api_tokens.generate_api_token", return_value="plaintoken"),
            patch("app.api.api_tokens.hash_token", return_value="hashval"),
        ):
            result = _create_mobile_redirect(mock_request, mock_db)

        location = result.headers["location"]
        # Should use "&" separator since "?" already present
        assert "&token=" in location


# ---------------------------------------------------------------------------
# auth() — multi-user and local user paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuthLocalUserPaths:
    """Tests for auth() covering LocalUser authentication and multi-user mode."""

    def _make_local_user(
        self,
        *,
        email: str = "alice@example.com",
        username: str = "alice",
        is_active: bool = True,
        is_admin: bool = False,
        hashed_password: str = "hashed",  # noqa: S107
    ):
        """Build a mock LocalUser."""
        user = MagicMock()
        user.email = email
        user.username = username
        user.is_active = is_active
        user.is_admin = is_admin
        user.hashed_password = hashed_password
        return user

    def _make_db(self, local_user=None):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = local_user
        return mock_db

    @pytest.mark.asyncio
    async def test_empty_username_in_multi_user_mode_redirects(self):
        """Empty username in multi-user mode returns error redirect."""
        from app.auth import auth

        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={})  # no username
        mock_request.session = {}

        with patch("app.auth.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=self._make_db(None))

        assert isinstance(result, RedirectResponse)
        assert "Invalid+username+or+password" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_inactive_local_user_redirects_with_verify_email_message(self):
        """Inactive (unverified) local user gets an error asking for email verification."""
        from app.auth import auth

        local_user = self._make_local_user(is_active=False)
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "pw"})
        mock_request.session = {}

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._record_login_event"),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=self._make_db(local_user))

        assert isinstance(result, RedirectResponse)
        assert "verify+your+email" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_wrong_password_for_local_user_redirects(self):
        """Wrong password for a valid local user returns error redirect."""
        from app.auth import auth

        local_user = self._make_local_user()
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "wrongpw"})
        mock_request.session = {}

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._verify_password", return_value=False),
            patch("app.auth._record_login_event"),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=self._make_db(local_user))

        assert isinstance(result, RedirectResponse)
        assert "Invalid+username+or+password" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_successful_local_user_login(self):
        """Correct password for a local user sets session and redirects."""
        from app.auth import auth

        local_user = self._make_local_user()
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "correctpw"})
        mock_request.session = {}
        mock_request.headers = {}

        mock_session_obj = MagicMock()
        mock_session_obj.session_token = "local-session-tok"
        profile = MagicMock()
        profile.onboarding_completed = True

        def db_query_side_effect(model):
            """Return appropriate mock based on model being queried."""
            mock_q = MagicMock()
            mock_q.filter.return_value.first.return_value = profile
            return mock_q

        mock_db = MagicMock()
        mock_db.query.side_effect = db_query_side_effect

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._verify_password", return_value=True),
            patch("app.auth._build_session_user", return_value={"id": "alice", "email": "alice@example.com"}),
            patch("app.auth._record_login_event"),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session", return_value=mock_session_obj),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "user" in mock_request.session
        assert mock_request.session.get("_session_token") == "local-session-tok"

    @pytest.mark.asyncio
    async def test_local_user_mobile_redirect(self):
        """Successful local user login returns mobile redirect when URI is in session."""
        from app.auth import auth

        local_user = self._make_local_user()
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "pw"})
        mock_request.session = {}
        mock_request.headers = {}

        mobile_resp = RedirectResponse(url="docuelevate://callback?token=tok", status_code=302)

        mock_db = MagicMock()

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._verify_password", return_value=True),
            patch("app.auth._build_session_user", return_value={"id": "alice"}),
            patch("app.auth._record_login_event"),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=mobile_resp),
            patch("app.utils.session_manager.create_session"),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"
            mock_db.query.return_value.filter.return_value.first.return_value = local_user

            result = await auth(mock_request, db=mock_db)

        assert result is mobile_resp

    @pytest.mark.asyncio
    async def test_local_user_session_creation_exception_is_swallowed(self):
        """Exception during session creation for local user is swallowed; login still succeeds."""
        from app.auth import auth

        local_user = self._make_local_user()
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "pw"})
        mock_request.session = {}
        mock_request.headers = {}

        mock_db = MagicMock()
        profile = MagicMock()
        profile.onboarding_completed = True
        mock_db.query.return_value.filter.return_value.first.side_effect = [local_user, profile]

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._verify_password", return_value=True),
            patch("app.auth._build_session_user", return_value={"id": "alice"}),
            patch("app.auth._record_login_event"),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session", side_effect=Exception("session fail")),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=mock_db)

        # Should still redirect successfully despite the session creation failure
        assert isinstance(result, RedirectResponse)
        assert "user" in mock_request.session

    @pytest.mark.asyncio
    async def test_local_user_onboarding_redirect(self):
        """Local user who hasn't completed onboarding is sent to /onboarding."""
        from app.auth import auth
        from app.models import UserProfile

        local_user = self._make_local_user()
        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "alice", "password": "pw"})
        mock_request.session = {}
        mock_request.headers = {}

        profile = UserProfile(user_id="alice@example.com", onboarding_completed=False)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.side_effect = [local_user, profile]

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._verify_password", return_value=True),
            patch("app.auth._build_session_user", return_value={"id": "alice"}),
            patch("app.auth._record_login_event"),
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session"),
        ):
            mock_settings.multi_user_enabled = True
            mock_settings.admin_username = "admin"
            mock_settings.admin_password = "adminpass"

            result = await auth(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/onboarding"


# ---------------------------------------------------------------------------
# auth() — admin credentials paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAuthAdminExtended:
    """Additional coverage for admin auth paths."""

    def _make_db(self, local_user=None):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = local_user
        return mock_db

    @pytest.mark.asyncio
    async def test_admin_login_session_token_exception_is_swallowed(self):
        """Exception during admin session token creation is swallowed; redirect is still returned."""
        from app.auth import auth

        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "adminuser", "password": "adminpass"})
        mock_request.session = {}
        mock_request.headers = {}

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._record_login_event"),
            patch("app.auth._create_mobile_redirect", return_value=None),
            patch("app.utils.session_manager.create_session", side_effect=Exception("session fail")),
        ):
            mock_settings.admin_username = "adminuser"
            mock_settings.admin_password = "adminpass"
            mock_settings.multi_user_enabled = False

            result = await auth(mock_request, db=self._make_db(None))

        assert isinstance(result, RedirectResponse)
        # Session should still have user even if token creation failed
        assert "user" in mock_request.session

    @pytest.mark.asyncio
    async def test_admin_login_mobile_redirect(self):
        """Admin login returns mobile redirect when mobile_redirect_uri is in session."""
        from app.auth import auth

        mock_request = MagicMock(spec=Request)
        mock_request.form = AsyncMock(return_value={"username": "adminuser", "password": "adminpass"})
        mock_request.session = {}
        mock_request.headers = {}

        mobile_resp = RedirectResponse(url="docuelevate://callback?token=admin-tok", status_code=302)

        with (
            patch("app.auth.settings") as mock_settings,
            patch("app.auth._ensure_user_profile"),
            patch("app.auth._record_login_event"),
            patch("app.auth._create_mobile_redirect", return_value=mobile_resp),
            patch("app.utils.session_manager.create_session"),
        ):
            mock_settings.admin_username = "adminuser"
            mock_settings.admin_password = "adminpass"
            mock_settings.multi_user_enabled = False

            result = await auth(mock_request, db=self._make_db(None))

        assert result is mobile_resp


# ---------------------------------------------------------------------------
# logout() — session token revocation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogoutSessionRevocation:
    """Tests for logout() session token revocation."""

    @pytest.mark.asyncio
    async def test_logout_revokes_server_side_session(self):
        """logout() sets is_revoked=True on the UserSession and commits."""
        from app.auth import logout

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "user": {"preferred_username": "alice"},
            "_session_token": "active-session-token",
        }

        mock_user_session = MagicMock()
        mock_user_session.is_revoked = False

        mock_db = MagicMock()

        with (
            patch("app.utils.audit_service.record_event"),
            patch("app.utils.session_manager.validate_session", return_value=mock_user_session),
        ):
            result = await logout(mock_request, db=mock_db)

        assert mock_user_session.is_revoked is True
        mock_db.commit.assert_called_once()
        assert isinstance(result, RedirectResponse)
        assert "logged+out" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_when_session_token_already_invalid(self):
        """logout() handles validate_session returning None gracefully."""
        from app.auth import logout

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "user": {"preferred_username": "alice"},
            "_session_token": "orphan-token",
        }

        mock_db = MagicMock()

        with (
            patch("app.utils.audit_service.record_event"),
            patch("app.utils.session_manager.validate_session", return_value=None),
        ):
            result = await logout(mock_request, db=mock_db)

        # No commit since session was already gone
        mock_db.commit.assert_not_called()
        assert isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_logout_session_revoke_exception_is_swallowed(self):
        """Exception during session revocation is swallowed and logout still completes."""
        from app.auth import logout

        mock_request = MagicMock(spec=Request)
        mock_request.session = {
            "user": {"email": "bob@example.com"},
            "_session_token": "some-token",
        }

        mock_db = MagicMock()

        with (
            patch("app.utils.audit_service.record_event"),
            patch("app.utils.session_manager.validate_session", side_effect=Exception("db error")),
        ):
            result = await logout(mock_request, db=mock_db)

        # Should still redirect successfully
        assert isinstance(result, RedirectResponse)
        assert "logged+out" in result.headers["location"]

    @pytest.mark.asyncio
    async def test_logout_without_session_token_still_completes(self):
        """Logout without any _session_token in session completes normally."""
        from app.auth import logout

        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"preferred_username": "charlie"}}

        mock_db = MagicMock()

        with patch("app.utils.audit_service.record_event"):
            result = await logout(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert "logged+out" in result.headers["location"]
        assert "user" not in mock_request.session
