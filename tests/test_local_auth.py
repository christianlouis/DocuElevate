"""Tests for local user authentication: signup, email verification, and password reset.

Covers:
- POST /api/auth/signup (success, disabled, SMTP missing, password mismatch, conflicts)
- GET  /verify-email (valid token, invalid token, expired token)
- POST /api/auth/resend-verification
- POST /api/auth/request-password-reset
- POST /api/auth/reset-password
- GET  /signup (page route)
- GET  /verify-email-sent (page route)
- GET  /reset-password (page route)
- app/utils/local_auth utility functions
- auth() login flow with LocalUser
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.models import LocalUser, UserProfile
from app.utils.local_auth import (
    build_session_user,
    generate_token,
    hash_password,
    is_token_expired,
    verify_password,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture()
def la_engine():
    """In-memory SQLite engine for local auth tests."""
    engine = create_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def la_session(la_engine):
    """DB session for one test."""
    Session = sessionmaker(bind=la_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def la_client(la_engine):
    """TestClient with DB dependency overridden."""
    from app.main import app

    Session = sessionmaker(bind=la_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=True) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def active_user(la_session):
    """A fully active LocalUser in the DB."""
    user = LocalUser(
        email="active@example.com",
        username="activeuser",
        display_name="Active User",
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    la_session.add(user)
    la_session.add(UserProfile(user_id="active@example.com", display_name="Active User", onboarding_completed=True))
    la_session.commit()
    return user


@pytest.fixture()
def pending_user(la_session):
    """A LocalUser with a pending email verification token."""
    token = "validtoken123"
    user = LocalUser(
        email="pending@example.com",
        username="pendinguser",
        hashed_password=hash_password("password123"),
        is_active=False,
        email_verification_token=token,
        email_verification_sent_at=datetime.now(tz=timezone.utc),
    )
    la_session.add(user)
    la_session.commit()
    return user


# ---------------------------------------------------------------------------
# Unit tests: local_auth utilities
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hash_and_verify_password():
    """hash_password produces a bcrypt hash that verify_password validates."""
    plain = "super$ecret99"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong", hashed) is False


@pytest.mark.unit
def test_verify_password_bad_hash_returns_false():
    """verify_password returns False for a non-bcrypt string."""
    assert verify_password("any", "notahash") is False


@pytest.mark.unit
def test_generate_token_unique():
    """generate_token returns distinct non-empty strings."""
    tokens = {generate_token() for _ in range(10)}
    assert len(tokens) == 10
    for t in tokens:
        assert len(t) > 20


@pytest.mark.unit
def test_is_token_expired_none():
    """None sent_at is treated as expired."""
    assert is_token_expired(None) is True


@pytest.mark.unit
def test_is_token_expired_old():
    """Token sent more than 24 h ago is expired."""
    old = datetime.now(tz=timezone.utc) - timedelta(hours=25)
    assert is_token_expired(old) is True


@pytest.mark.unit
def test_is_token_expired_fresh():
    """Token sent recently is not expired."""
    fresh = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    assert is_token_expired(fresh) is False


@pytest.mark.unit
def test_build_session_user():
    """build_session_user returns the expected dict structure."""
    user = MagicMock()
    user.email = "u@example.com"
    user.username = "uname"
    user.display_name = "Display Name"
    user.is_admin = False
    with patch("app.auth.get_gravatar_url", return_value="https://gravatar.com/test"):
        result = build_session_user(user)
    assert result["email"] == "u@example.com"
    assert result["preferred_username"] == "uname"
    assert result["name"] == "Display Name"
    assert result["is_admin"] is False
    assert result["auth_method"] == "local"
    assert "picture" in result


# ---------------------------------------------------------------------------
# Integration tests: signup
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_signup_disabled(la_client):
    """POST /api/auth/signup returns 403 when allow_local_signup is False."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.allow_local_signup = False
        mock_settings.email_host = "smtp.example.com"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "a@example.com",
                "username": "auser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 403


@pytest.mark.integration
def test_signup_smtp_not_configured(la_client):
    """POST /api/auth/signup succeeds without SMTP and activates the account immediately."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = None
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "a@example.com",
                "username": "auser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email_verification_required"] is False
    assert "now log in" in data["message"]


@pytest.mark.integration
def test_signup_password_mismatch(la_client):
    """POST /api/auth/signup returns 422 when passwords do not match."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = "smtp.example.com"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "a@example.com",
                "username": "auser",
                "password": "password1",
                "password_confirm": "different1",
            },
        )
    assert resp.status_code == 422


@pytest.mark.integration
def test_signup_success(la_client):
    """POST /api/auth/signup creates user and returns 201."""
    with (
        patch("app.api.local_auth.settings") as mock_settings,
        patch("app.api.local_auth.send_verification_email") as mock_send,
    ):
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = "smtp.example.com"
        mock_settings.version = "test"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "new@example.com",
                "username": "newuser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 201
    assert "Verification email sent" in resp.json()["message"]
    assert resp.json()["email_verification_required"] is True
    mock_send.assert_called_once()


@pytest.mark.integration
def test_signup_duplicate_email(la_client, active_user):
    """POST /api/auth/signup returns 409 when email already registered."""
    with (
        patch("app.api.local_auth.settings") as mock_settings,
        patch("app.api.local_auth.send_verification_email"),
    ):
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = "smtp.example.com"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "active@example.com",
                "username": "otheruser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 409
    assert "Email" in resp.json()["detail"]


@pytest.mark.integration
def test_signup_duplicate_username(la_client, active_user):
    """POST /api/auth/signup returns 409 when username already taken."""
    with (
        patch("app.api.local_auth.settings") as mock_settings,
        patch("app.api.local_auth.send_verification_email"),
    ):
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = "smtp.example.com"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "different@example.com",
                "username": "activeuser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 409
    assert "Username" in resp.json()["detail"]


@pytest.mark.integration
def test_signup_smtp_failure_cleans_up(la_client, la_session):
    """POST /api/auth/signup cleans up user records if email send fails."""
    with (
        patch("app.api.local_auth.settings") as mock_settings,
        patch("app.api.local_auth.send_verification_email", side_effect=RuntimeError("SMTP down")),
    ):
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.email_host = "smtp.example.com"
        resp = la_client.post(
            "/api/auth/signup",
            json={
                "email": "fail@example.com",
                "username": "failuser",
                "password": "password1",
                "password_confirm": "password1",
            },
        )
    assert resp.status_code == 503
    # User should NOT exist in the DB
    user = la_session.query(LocalUser).filter(LocalUser.email == "fail@example.com").first()
    assert user is None


# ---------------------------------------------------------------------------
# Integration tests: email verification
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_verify_email_valid_token(la_client, pending_user):
    """GET /verify-email with valid token activates account and redirects."""
    resp = la_client.get(
        f"/verify-email?token={pending_user.email_verification_token}",
        follow_redirects=False,
    )
    assert resp.status_code == 302


@pytest.mark.integration
def test_verify_email_invalid_token(la_client):
    """GET /verify-email with unknown token redirects to login with error."""
    resp = la_client.get("/verify-email?token=doesnotexist", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


@pytest.mark.integration
def test_verify_email_expired_token(la_client, la_session):
    """GET /verify-email with expired token redirects to login with error."""
    old_time = datetime.now(tz=timezone.utc) - timedelta(hours=25)
    user = LocalUser(
        email="expired@example.com",
        username="expireduser",
        hashed_password=hash_password("password123"),
        is_active=False,
        email_verification_token="expiredtoken",
        email_verification_sent_at=old_time,
    )
    la_session.add(user)
    la_session.commit()

    resp = la_client.get("/verify-email?token=expiredtoken", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Integration tests: resend verification
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_resend_verification_always_200(la_client):
    """POST /api/auth/resend-verification returns 200 for unknown email."""
    with patch("app.api.local_auth.send_verification_email"):
        resp = la_client.post(
            "/api/auth/resend-verification",
            json={"email": "nobody@example.com"},
        )
    assert resp.status_code == 200


@pytest.mark.integration
def test_resend_verification_sends_email(la_client, pending_user):
    """POST /api/auth/resend-verification sends email for pending user."""
    with patch("app.api.local_auth.send_verification_email") as mock_send:
        resp = la_client.post(
            "/api/auth/resend-verification",
            json={"email": pending_user.email},
        )
    assert resp.status_code == 200
    mock_send.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests: password reset
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_request_password_reset_always_200(la_client):
    """POST /api/auth/request-password-reset returns 200 for unknown email."""
    with patch("app.api.local_auth.send_password_reset_email"):
        resp = la_client.post(
            "/api/auth/request-password-reset",
            json={"email": "nobody@example.com"},
        )
    assert resp.status_code == 200


@pytest.mark.integration
def test_request_password_reset_sends_email(la_client, active_user):
    """POST /api/auth/request-password-reset sends email for known user."""
    with patch("app.api.local_auth.send_password_reset_email") as mock_send:
        resp = la_client.post(
            "/api/auth/request-password-reset",
            json={"email": active_user.email},
        )
    assert resp.status_code == 200
    mock_send.assert_called_once()


@pytest.mark.integration
def test_reset_password_success(la_client, la_session):
    """POST /api/auth/reset-password updates password with valid token."""
    token = "resettoken123"
    user = LocalUser(
        email="reset@example.com",
        username="resetuser",
        hashed_password=hash_password("oldpassword"),
        is_active=True,
        password_reset_token=token,
        password_reset_sent_at=datetime.now(tz=timezone.utc),
    )
    la_session.add(user)
    la_session.commit()

    resp = la_client.post(
        "/api/auth/reset-password",
        json={
            "token": token,
            "new_password": "newpassword1",
            "new_password_confirm": "newpassword1",
        },
    )
    assert resp.status_code == 200
    la_session.refresh(user)
    assert verify_password("newpassword1", user.hashed_password)
    assert user.password_reset_token is None


@pytest.mark.integration
def test_reset_password_invalid_token(la_client):
    """POST /api/auth/reset-password returns 400 for invalid token."""
    resp = la_client.post(
        "/api/auth/reset-password",
        json={
            "token": "badtoken",
            "new_password": "newpassword1",
            "new_password_confirm": "newpassword1",
        },
    )
    assert resp.status_code == 400


@pytest.mark.integration
def test_reset_password_mismatch(la_client, la_session):
    """POST /api/auth/reset-password returns 422 when passwords do not match."""
    token = "mismatchtoken"
    user = LocalUser(
        email="mismatch@example.com",
        username="mismatchuser",
        hashed_password=hash_password("old"),
        is_active=True,
        password_reset_token=token,
        password_reset_sent_at=datetime.now(tz=timezone.utc),
    )
    la_session.add(user)
    la_session.commit()

    resp = la_client.post(
        "/api/auth/reset-password",
        json={
            "token": token,
            "new_password": "newpassword1",
            "new_password_confirm": "different_pw",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests: page routes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_signup_page_disabled_redirects(la_client):
    """GET /signup redirects when allow_local_signup is False."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.allow_local_signup = False
        resp = la_client.get("/signup", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["location"]


@pytest.mark.integration
def test_signup_page_enabled(la_client):
    """GET /signup returns 200 when allow_local_signup is True."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.allow_local_signup = True
        mock_settings.multi_user_enabled = True
        mock_settings.version = "test"
        resp = la_client.get("/signup")
    assert resp.status_code == 200
    assert b"Create" in resp.content


@pytest.mark.integration
def test_verify_email_sent_page(la_client):
    """GET /verify-email-sent returns 200."""
    resp = la_client.get("/verify-email-sent")
    assert resp.status_code == 200


@pytest.mark.integration
def test_reset_password_page(la_client):
    """GET /reset-password returns 200."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.version = "test"
        resp = la_client.get("/reset-password?token=abc123")
    assert resp.status_code == 200
    assert b"password" in resp.content.lower()


# ---------------------------------------------------------------------------
# Integration tests: auth() login flow with LocalUser
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", True)
async def test_local_login_success(la_session, active_user):
    """auth() with valid LocalUser credentials sets session and redirects."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"username": "activeuser", "password": "password123"})
    mock_request.session = {}

    result = await auth(mock_request, db=la_session)
    assert result.status_code == 302
    assert "user" in mock_request.session
    assert mock_request.session["user"]["email"] == "active@example.com"


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", True)
async def test_local_login_by_email(la_session, active_user):
    """auth() accepts email as username for LocalUser lookup."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"username": "active@example.com", "password": "password123"})
    mock_request.session = {}

    result = await auth(mock_request, db=la_session)
    assert result.status_code == 302
    assert "user" in mock_request.session


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", True)
async def test_local_login_wrong_password(la_session, active_user):
    """auth() with wrong password redirects to login with error."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"username": "activeuser", "password": "wrongpassword"})
    mock_request.session = {}

    result = await auth(mock_request, db=la_session)
    assert result.status_code == 302
    assert "/login" in result.headers["location"]
    assert "user" not in mock_request.session


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", True)
async def test_local_login_unverified(la_session, pending_user):
    """auth() for unverified user redirects with verification message."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"username": "pendinguser", "password": "password123"})
    mock_request.session = {}

    result = await auth(mock_request, db=la_session)
    assert result.status_code == 302
    assert "verify" in result.headers["location"].lower()


# ---------------------------------------------------------------------------
# Single-user backward-compatibility: LocalUser table must NOT be queried
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", False)
async def test_single_user_mode_skips_local_user_table(la_session, active_user):
    """In single-user mode auth() must not query LocalUser even when a matching
    row exists.  It should fall through to the admin-credential check."""
    from unittest.mock import AsyncMock, MagicMock
    from unittest.mock import patch as _patch

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    # Use the active LocalUser's credentials — they must NOT work in single-user mode
    # because the whole LocalUser block is skipped.
    mock_request.form = AsyncMock(return_value={"username": "activeuser", "password": "password123"})
    mock_request.session = {}

    with (
        _patch.object(settings, "admin_username", "activeuser"),
        _patch.object(settings, "admin_password", "password123"),
    ):
        result = await auth(mock_request, db=la_session)

    # Should succeed via admin-credentials path (is_admin=True), not LocalUser path
    assert result.status_code == 302
    assert "user" in mock_request.session
    # Admin path sets is_admin=True and id="admin"
    assert mock_request.session["user"]["is_admin"] is True
    assert mock_request.session["user"]["id"] == "admin"


# ---------------------------------------------------------------------------
# Integration tests: admin local user management
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_session_client(la_engine):
    """TestClient with admin access via dependency override."""
    from app.api.admin_users import _require_admin
    from app.main import app

    Session = sessionmaker(bind=la_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_require_admin():
        return {"id": "admin@example.com", "is_admin": True, "display_name": "Admin"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_require_admin] = override_require_admin
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=True) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(_require_admin, None)


@pytest.mark.integration
def test_admin_list_local_users_empty(admin_session_client):
    """GET /api/admin/users/local returns an empty list when no local users exist."""
    resp = admin_session_client.get("/api/admin/users/local")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
def test_admin_create_local_user(admin_session_client, la_session):
    """POST /api/admin/users/local creates a new active local user."""
    resp = admin_session_client.post(
        "/api/admin/users/local",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "password1",
            "is_admin": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert data["is_active"] is True
    assert data["is_admin"] is False

    user = la_session.query(LocalUser).filter(LocalUser.email == "newuser@example.com").first()
    assert user is not None
    assert user.is_active is True


@pytest.mark.integration
def test_admin_create_local_user_duplicate_email(admin_session_client, active_user):
    """POST /api/admin/users/local returns 409 when email already exists."""
    resp = admin_session_client.post(
        "/api/admin/users/local",
        json={
            "email": "active@example.com",
            "username": "differentuser",
            "password": "password1",
        },
    )
    assert resp.status_code == 409


@pytest.mark.integration
def test_admin_create_local_user_duplicate_username(admin_session_client, active_user):
    """POST /api/admin/users/local returns 409 when username already taken."""
    resp = admin_session_client.post(
        "/api/admin/users/local",
        json={
            "email": "different@example.com",
            "username": "activeuser",
            "password": "password1",
        },
    )
    assert resp.status_code == 409


@pytest.mark.integration
def test_admin_delete_local_user(admin_session_client, la_session, active_user):
    """DELETE /api/admin/users/local/{id} removes the account."""
    user_id = active_user.id
    resp = admin_session_client.delete(f"/api/admin/users/local/{user_id}")
    assert resp.status_code == 204

    user = la_session.query(LocalUser).filter(LocalUser.id == user_id).first()
    assert user is None


@pytest.mark.integration
def test_admin_delete_local_user_not_found(admin_session_client):
    """DELETE /api/admin/users/local/{id} returns 404 for unknown ID."""
    resp = admin_session_client.delete("/api/admin/users/local/99999")
    assert resp.status_code == 404


@pytest.mark.integration
def test_admin_local_user_list_after_create(admin_session_client):
    """GET /api/admin/users/local returns the created user."""
    admin_session_client.post(
        "/api/admin/users/local",
        json={"email": "listed@example.com", "username": "listeduser", "password": "password1"},
    )
    resp = admin_session_client.get("/api/admin/users/local")
    assert resp.status_code == 200
    users = resp.json()
    assert any(u["email"] == "listed@example.com" for u in users)
