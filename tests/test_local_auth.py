"""Tests for local user authentication: signup, email verification, and password reset.

Covers:
- POST /api/auth/signup (success, disabled, SMTP missing, password mismatch, conflicts)
- GET  /verify-email (valid token, invalid token, expired token)
- POST /api/auth/resend-verification
- POST /api/auth/request-password-reset
- POST /api/auth/reset-password
- POST /api/auth/forgot-username
- GET  /signup (page route)
- GET  /verify-email-sent (page route)
- GET  /reset-password (page route)
- GET  /forgot-password (page route)
- GET  /forgot-username (page route)
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


@pytest.mark.integration
def test_reset_password_activates_inactive_user(la_client, la_session):
    """POST /api/auth/reset-password sets is_active=True for inactive accounts.

    A user who registered when SMTP was configured starts out with is_active=False.
    Using the password-reset flow (which proves ownership of the email address) must
    also activate the account so the user can log in immediately afterwards.
    """
    token = "activatetoken456"
    user = LocalUser(
        email="inactive_reset@example.com",
        username="inactivereset",
        hashed_password=hash_password("oldpassword"),
        is_active=False,  # account not yet verified
        password_reset_token=token,
        password_reset_sent_at=datetime.now(tz=timezone.utc),
    )
    la_session.add(user)
    la_session.commit()

    resp = la_client.post(
        "/api/auth/reset-password",
        json={
            "token": token,
            "new_password": "newpassword2",
            "new_password_confirm": "newpassword2",
        },
    )
    assert resp.status_code == 200
    la_session.refresh(user)
    assert user.is_active is True, "reset_password must activate inactive accounts"
    assert verify_password("newpassword2", user.hashed_password)
    assert user.password_reset_token is None


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


@pytest.mark.unit
@pytest.mark.asyncio
@patch.object(settings, "multi_user_enabled", True)
async def test_local_login_unverified_wrong_password(la_session, pending_user):
    """auth() for unverified user with wrong password still shows the verify message.

    is_active is checked before password so that inactive users always receive
    the email-verification prompt regardless of whether they typed the correct
    password.  This avoids leaking whether the password is correct for an
    account that has not yet been verified.
    """
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from app.auth import auth

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(return_value={"username": "pendinguser", "password": "wrongpassword"})
    mock_request.session = {}

    result = await auth(mock_request, db=la_session)
    assert result.status_code == 302
    # Must send to the *verify* page, not the generic "invalid credentials" page.
    assert "verify" in result.headers["location"].lower()
    assert "user" not in mock_request.session


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


# ---------------------------------------------------------------------------
# Integration tests: forgot-username endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_forgot_username_returns_200_for_existing_email(la_client, la_session):
    """POST /api/auth/forgot-username returns 200 and sends email when account exists."""
    la_session.add(
        LocalUser(
            email="remindme@example.com",
            username="remindmeuser",
            hashed_password=hash_password("pw123456"),
            is_active=True,
        )
    )
    la_session.commit()

    with patch("app.api.local_auth.send_forgot_username_email") as mock_send:
        resp = la_client.post("/api/auth/forgot-username", json={"email": "remindme@example.com"})

    assert resp.status_code == 200
    assert "reminder" in resp.json()["message"].lower()
    mock_send.assert_called_once_with("remindme@example.com", "remindmeuser")


@pytest.mark.integration
def test_forgot_username_returns_200_for_unknown_email(la_client):
    """POST /api/auth/forgot-username always returns 200 (no info leak)."""
    with patch("app.api.local_auth.send_forgot_username_email") as mock_send:
        resp = la_client.post("/api/auth/forgot-username", json={"email": "nobody@example.com"})

    assert resp.status_code == 200
    mock_send.assert_not_called()


@pytest.mark.integration
def test_forgot_username_smtp_failure_does_not_raise(la_client, la_session):
    """POST /api/auth/forgot-username returns 200 even when SMTP fails."""
    la_session.add(
        LocalUser(
            email="smtpfail@example.com",
            username="smtpfailuser",
            hashed_password=hash_password("pw123456"),
            is_active=True,
        )
    )
    la_session.commit()

    with patch("app.api.local_auth.send_forgot_username_email", side_effect=RuntimeError("SMTP down")):
        resp = la_client.post("/api/auth/forgot-username", json={"email": "smtpfail@example.com"})

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Integration tests: new page routes
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_forgot_password_page(la_client):
    """GET /forgot-password returns 200."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.version = "test"
        resp = la_client.get("/forgot-password")
    assert resp.status_code == 200
    assert b"password" in resp.content.lower()


@pytest.mark.integration
def test_forgot_username_page(la_client):
    """GET /forgot-username returns 200."""
    with patch("app.api.local_auth.settings") as mock_settings:
        mock_settings.version = "test"
        resp = la_client.get("/forgot-username")
    assert resp.status_code == 200
    assert b"username" in resp.content.lower()


# ---------------------------------------------------------------------------
# Unit tests: send_forgot_username_email utility
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_send_forgot_username_email_calls_smtp():
    """send_forgot_username_email calls _smtp_send with the username."""
    from app.utils.local_auth import send_forgot_username_email

    with patch("app.utils.local_auth._smtp_send") as mock_smtp:
        send_forgot_username_email("u@example.com", "myusername")

    mock_smtp.assert_called_once()
    args = mock_smtp.call_args[0]
    # subject, html_body, plain_body, recipient
    assert "myusername" in args[1]  # HTML body
    assert "myusername" in args[2]  # plain body
    assert args[3] == "u@example.com"


@pytest.mark.unit
def test_send_forgot_username_email_no_smtp_raises():
    """send_forgot_username_email raises RuntimeError when EMAIL_HOST is not set."""
    from app.utils.local_auth import send_forgot_username_email

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = ""

        with pytest.raises(RuntimeError, match="SMTP"):
            send_forgot_username_email("u@example.com", "myusername")


# ---------------------------------------------------------------------------
# Unit tests: _smtp_send internals
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_smtp_send_no_email_host_raises():
    """_smtp_send raises RuntimeError when EMAIL_HOST is not configured."""
    from app.utils.local_auth import _smtp_send

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = None

        with pytest.raises(RuntimeError, match="SMTP is not configured"):
            _smtp_send("Subject", "<p>html</p>", "plain", "r@example.com")


@pytest.mark.unit
def test_smtp_send_dns_resolution_failure():
    """_smtp_send raises RuntimeError when the SMTP host cannot be resolved."""
    import socket

    from app.utils.local_auth import _smtp_send

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "badhost.invalid"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.email_username = None
        mock_settings.email_password = None
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False

        with patch("app.utils.local_auth.socket.gethostbyname", side_effect=socket.gaierror("Name resolution failed")):
            with pytest.raises(RuntimeError, match="Cannot resolve SMTP host"):
                _smtp_send("Subject", "<p>html</p>", "plain", "r@example.com")


@pytest.mark.unit
def test_smtp_send_success_no_tls_no_auth():
    """_smtp_send connects, skips TLS and auth when not configured, and sends the message."""
    from app.utils.local_auth import _smtp_send

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.email_username = None
        mock_settings.email_password = None
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False

        with patch("app.utils.local_auth.socket.gethostbyname", return_value="1.2.3.4"):
            with patch("app.utils.local_auth.smtplib.SMTP", mock_smtp_cls):
                _smtp_send("Test Subject", "<p>html</p>", "plain text", "recipient@example.com")

    mock_server.starttls.assert_not_called()
    mock_server.login.assert_not_called()
    mock_server.send_message.assert_called_once()


@pytest.mark.unit
def test_smtp_send_with_tls():
    """_smtp_send calls starttls() when email_use_tls is True."""
    from app.utils.local_auth import _smtp_send

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_sender = "sender@example.com"
        mock_settings.email_username = None
        mock_settings.email_password = None
        mock_settings.email_port = 587
        mock_settings.email_use_tls = True

        with patch("app.utils.local_auth.socket.gethostbyname", return_value="1.2.3.4"):
            with patch("app.utils.local_auth.smtplib.SMTP", mock_smtp_cls):
                _smtp_send("Test Subject", "<p>html</p>", "plain text", "recipient@example.com")

    mock_server.starttls.assert_called_once()
    mock_server.send_message.assert_called_once()


@pytest.mark.unit
def test_smtp_send_with_auth():
    """_smtp_send calls login() when email_username and email_password are set."""
    from app.utils.local_auth import _smtp_send

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_sender = None
        mock_settings.email_username = "user@example.com"
        mock_settings.email_password = "secret"
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False

        with patch("app.utils.local_auth.socket.gethostbyname", return_value="1.2.3.4"):
            with patch("app.utils.local_auth.smtplib.SMTP", mock_smtp_cls):
                _smtp_send("Subject", "<p>html</p>", "plain", "r@example.com")

    mock_server.login.assert_called_once_with("user@example.com", "secret")
    mock_server.send_message.assert_called_once()


@pytest.mark.unit
def test_smtp_send_uses_email_username_as_sender_fallback():
    """_smtp_send falls back to email_username when email_sender is not set."""
    from app.utils.local_auth import _smtp_send

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_sender = None
        mock_settings.email_username = "fallback@example.com"
        mock_settings.email_password = None
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False

        with patch("app.utils.local_auth.socket.gethostbyname", return_value="1.2.3.4"):
            with patch("app.utils.local_auth.smtplib.SMTP", mock_smtp_cls):
                _smtp_send("Subject", "<p>html</p>", "plain", "r@example.com")

    # The message should have been sent (sender was resolved from email_username)
    mock_server.send_message.assert_called_once()


@pytest.mark.unit
def test_smtp_send_default_noreply_sender():
    """_smtp_send falls back to noreply@docuelevate.local when neither sender nor username is set."""
    from app.utils.local_auth import _smtp_send

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.utils.local_auth.settings") as mock_settings:
        mock_settings.email_host = "smtp.example.com"
        mock_settings.email_sender = None
        mock_settings.email_username = None
        mock_settings.email_password = None
        mock_settings.email_port = 587
        mock_settings.email_use_tls = False

        with patch("app.utils.local_auth.socket.gethostbyname", return_value="1.2.3.4"):
            with patch("app.utils.local_auth.smtplib.SMTP", mock_smtp_cls) as smtp_cls:
                _smtp_send("Subject", "<p>html</p>", "plain", "r@example.com")

    # Verify SMTP was instantiated with correct host
    smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
    mock_server.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# Unit tests: send_verification_email and send_password_reset_email
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_send_verification_email_calls_smtp():
    """send_verification_email passes the verify URL in html_body and plain_body."""
    from app.utils.local_auth import send_verification_email

    with patch("app.utils.local_auth._smtp_send") as mock_smtp:
        send_verification_email(
            email="user@example.com",
            username="testuser",
            token="abc123token",
            base_url="https://app.example.com",
        )

    mock_smtp.assert_called_once()
    subject, html_body, plain_body, recipient = mock_smtp.call_args[0]
    assert "Verify" in subject
    assert "https://app.example.com/verify-email?token=abc123token" in html_body
    assert "https://app.example.com/verify-email?token=abc123token" in plain_body
    assert "testuser" in html_body
    assert "testuser" in plain_body
    assert recipient == "user@example.com"


@pytest.mark.unit
def test_send_password_reset_email_calls_smtp():
    """send_password_reset_email passes the reset URL in html_body and plain_body."""
    from app.utils.local_auth import send_password_reset_email

    with patch("app.utils.local_auth._smtp_send") as mock_smtp:
        send_password_reset_email(
            email="user@example.com",
            username="testuser",
            token="resettoken456",
            base_url="https://app.example.com",
        )

    mock_smtp.assert_called_once()
    subject, html_body, plain_body, recipient = mock_smtp.call_args[0]
    assert "Reset" in subject or "reset" in subject.lower()
    assert "https://app.example.com/reset-password?token=resettoken456" in html_body
    assert "https://app.example.com/reset-password?token=resettoken456" in plain_body
    assert "testuser" in html_body
    assert "testuser" in plain_body
    assert recipient == "user@example.com"


# ---------------------------------------------------------------------------
# Unit tests: build_session_user edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_session_user_no_display_name_falls_back_to_username():
    """build_session_user uses username as 'name' when display_name is None."""
    user = MagicMock()
    user.email = "u@example.com"
    user.username = "uname"
    user.display_name = None
    user.is_admin = True

    with patch("app.auth.get_gravatar_url", return_value="https://gravatar.com/test"):
        result = build_session_user(user)

    assert result["name"] == "uname"
    assert result["is_admin"] is True
    assert result["auth_method"] == "local"
