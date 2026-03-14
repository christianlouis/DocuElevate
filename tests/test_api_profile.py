"""Tests for app/api/profile.py — user self-service profile API.

Unit tests call handler functions directly with mock request objects.
Integration tests use a dedicated TestClient with DB override.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import LocalUser, UserProfile

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

# Minimal valid 1×1 PNG image (base64-encoded) used across avatar upload tests
_MINIMAL_VALID_PNG_BASE64 = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/Z+hHgAHggJ/PchI6QAAAABJRU5ErkJggg=="
)
_MINIMAL_VALID_PNG_BYTES = base64.b64decode(_MINIMAL_VALID_PNG_BASE64)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def prof_engine():
    """In-memory SQLite engine scoped to one test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def prof_session(prof_engine):
    """DB session for one profile test."""
    Session = sessionmaker(bind=prof_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def prof_client(prof_engine):
    """TestClient with the in-memory DB injected."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=prof_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGravatarUrl:
    """Tests for the _gravatar_url helper."""

    def test_returns_gravatar_for_valid_email(self):
        from app.api.profile import _gravatar_url

        url = _gravatar_url("Test@Example.COM")
        assert url.startswith("https://www.gravatar.com/avatar/")
        assert url.endswith("?d=identicon")

    def test_fallback_for_none_email(self):
        from app.api.profile import _gravatar_url

        url = _gravatar_url(None)
        assert url.startswith("https://www.gravatar.com/avatar/")
        assert url.endswith("?d=identicon")


@pytest.mark.unit
class TestGetUserId:
    """Tests for the _get_user_id helper."""

    def test_extracts_sub(self):
        from app.api.profile import _get_user_id

        req = MagicMock()
        req.session = {"user": {"sub": "sub-123", "email": "a@b.com"}}
        assert _get_user_id(req) == "sub-123"

    def test_extracts_preferred_username_fallback(self):
        from app.api.profile import _get_user_id

        req = MagicMock()
        req.session = {"user": {"preferred_username": "alice", "email": "a@b.com"}}
        assert _get_user_id(req) == "alice"

    def test_extracts_email_fallback(self):
        from app.api.profile import _get_user_id

        req = MagicMock()
        req.session = {"user": {"email": "a@b.com"}}
        assert _get_user_id(req) == "a@b.com"

    def test_raises_401_when_no_session_user(self):
        from app.api.profile import _get_user_id

        req = MagicMock()
        req.session = {}
        with pytest.raises(HTTPException) as exc:
            _get_user_id(req)
        assert exc.value.status_code == 401

    def test_raises_401_when_no_identifier(self):
        from app.api.profile import _get_user_id

        req = MagicMock()
        req.session = {"user": {"name": "Someone"}}
        with pytest.raises(HTTPException) as exc:
            _get_user_id(req)
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Unit tests — GET /api/profile handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetProfileHandler:
    """Unit tests for the get_profile endpoint handler."""

    @pytest.mark.asyncio
    async def test_returns_profile_from_db(self, prof_session):
        """get_profile reads from DB and returns correct data."""
        from app.api.profile import get_profile

        profile = UserProfile(
            user_id="alice",
            display_name="Alice",
            preferred_language="fr",
            preferred_theme="dark",
        )
        prof_session.add(profile)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "alice", "email": "alice@example.com"}}

        result = await get_profile(req, prof_session)
        assert result.user_id == "alice"
        assert result.display_name == "Alice"
        assert result.preferred_language == "fr"
        assert result.preferred_theme == "dark"
        assert result.avatar_url.startswith("https://www.gravatar.com/avatar/")

    @pytest.mark.asyncio
    async def test_returns_custom_avatar_when_stored(self, prof_session):
        """get_profile returns the data: URI when avatar_data is set."""
        from app.api.profile import get_profile

        profile = UserProfile(
            user_id="bob",
            avatar_data="data:image/png;base64,abc",
        )
        prof_session.add(profile)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "bob", "email": "bob@example.com"}}

        result = await get_profile(req, prof_session)
        assert result.avatar_url == "data:image/png;base64,abc"

    @pytest.mark.asyncio
    async def test_creates_profile_if_missing(self, prof_session):
        """get_profile creates a stub profile row when none exists."""
        from app.api.profile import get_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "newbie", "email": "newbie@example.com"}}

        result = await get_profile(req, prof_session)
        assert result.user_id == "newbie"
        row = prof_session.query(UserProfile).filter_by(user_id="newbie").first()
        assert row is not None


# ---------------------------------------------------------------------------
# Unit tests — PATCH /api/profile handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateProfileHandler:
    """Unit tests for the update_profile endpoint handler."""

    @pytest.mark.asyncio
    async def test_updates_display_name(self, prof_session):
        """update_profile updates display_name."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "carol", "email": "carol@example.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(display_name="Carol Smith")
        result = await update_profile(body, req, resp, prof_session)
        assert result.display_name == "Carol Smith"

    @pytest.mark.asyncio
    async def test_updates_language(self, prof_session):
        """update_profile updates preferred_language."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "dave", "email": "dave@example.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(preferred_language="de")
        result = await update_profile(body, req, resp, prof_session)
        assert result.preferred_language == "de"

    @pytest.mark.asyncio
    async def test_updates_language_syncs_session_and_cookie(self, prof_session):
        """update_profile syncs language to session and cookie."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        session = {"user": {"preferred_username": "dave2", "email": "dave2@example.com"}}
        req = MagicMock()
        req.session = session
        resp = MagicMock()

        body = ProfileUpdateRequest(preferred_language="fr")
        await update_profile(body, req, resp, prof_session)

        assert session["preferred_language"] == "fr"
        resp.set_cookie.assert_called_once()
        cookie_kwargs = resp.set_cookie.call_args
        assert cookie_kwargs.kwargs["key"] == "docuelevate_lang"
        assert cookie_kwargs.kwargs["value"] == "fr"

    @pytest.mark.asyncio
    async def test_updates_theme(self, prof_session):
        """update_profile updates preferred_theme."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "eve", "email": "eve@example.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(preferred_theme="light")
        result = await update_profile(body, req, resp, prof_session)
        assert result.preferred_theme == "light"

    @pytest.mark.asyncio
    async def test_rejects_invalid_language(self, prof_session):
        """update_profile raises 422 for unsupported language code."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "frank", "email": "frank@example.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(preferred_language="xx")
        with pytest.raises(HTTPException) as exc:
            await update_profile(body, req, resp, prof_session)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_invalid_theme(self, prof_session):
        """update_profile raises 422 for invalid theme value."""
        from app.api.profile import ProfileUpdateRequest, update_profile

        req = MagicMock()
        req.session = {"user": {"preferred_username": "grace", "email": "grace@example.com"}}
        resp = MagicMock()

        body = ProfileUpdateRequest(preferred_theme="rainbow")
        with pytest.raises(HTTPException) as exc:
            await update_profile(body, req, resp, prof_session)
        assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# Unit tests — _hydrate_language_from_db (views/base.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHydrateLanguageFromDb:
    """Tests for session hydration of preferred_language from DB."""

    def test_hydrates_language_into_session(self, prof_session):
        """When DB has a preferred_language, it should be set in the session."""
        from app.views.base import _hydrate_language_from_db

        # Create a profile with a preferred_language
        profile = UserProfile(user_id="hydrate_user", preferred_language="fr")
        prof_session.add(profile)
        prof_session.commit()

        req = MagicMock()
        req.session = {}
        session_user = {"preferred_username": "hydrate_user"}

        # Patch SessionLocal to return our test session
        from unittest.mock import patch

        with patch("app.views.base.SessionLocal", return_value=prof_session):
            _hydrate_language_from_db(req, session_user)

        assert req.session.get("preferred_language") == "fr"

    def test_no_hydration_when_no_db_preference(self, prof_session):
        """When DB has no preferred_language, session should remain empty."""
        from app.views.base import _hydrate_language_from_db

        profile = UserProfile(user_id="no_pref_user")
        prof_session.add(profile)
        prof_session.commit()

        req = MagicMock()
        req.session = {}
        session_user = {"preferred_username": "no_pref_user"}

        from unittest.mock import patch

        with patch("app.views.base.SessionLocal", return_value=prof_session):
            _hydrate_language_from_db(req, session_user)

        assert "preferred_language" not in req.session

    def test_no_hydration_when_no_user_id(self, prof_session):
        """When session_user has no identifiable user_id, do nothing."""
        from app.views.base import _hydrate_language_from_db

        req = MagicMock()
        req.session = {}

        from unittest.mock import patch

        with patch("app.views.base.SessionLocal", return_value=prof_session):
            _hydrate_language_from_db(req, {})

        assert "preferred_language" not in req.session


# ---------------------------------------------------------------------------
# Unit tests — POST /api/profile/avatar handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadAvatarHandler:
    """Unit tests for the upload_avatar endpoint handler."""

    @pytest.mark.asyncio
    async def test_stores_base64_data_url(self, prof_session):
        """upload_avatar stores the image as a data: URI."""
        from app.api.profile import upload_avatar

        upload = MagicMock()
        upload.content_type = "image/png"
        upload.size = len(_MINIMAL_VALID_PNG_BYTES)
        upload.read = AsyncMock(return_value=_MINIMAL_VALID_PNG_BYTES)

        req = MagicMock()
        req.session = {"user": {"preferred_username": "avataruser", "email": "av@example.com"}}

        result = await upload_avatar(req, prof_session, upload)
        assert result["avatar_url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_rejects_unsupported_mime(self, prof_session):
        """upload_avatar raises 415 for non-image content types."""
        from app.api.profile import upload_avatar

        upload = MagicMock()
        upload.content_type = "application/pdf"
        upload.size = 4
        upload.read = AsyncMock(return_value=b"%PDF")

        req = MagicMock()
        req.session = {"user": {"preferred_username": "pdfuser", "email": "pdf@example.com"}}

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(req, prof_session, upload)
        assert exc.value.status_code == 415

    @pytest.mark.asyncio
    async def test_rejects_oversized_image(self, prof_session):
        """upload_avatar raises 413 when image exceeds 2 MB."""
        from app.api.profile import upload_avatar

        big_size = 2 * 1024 * 1024 + 1

        upload = MagicMock()
        upload.content_type = "image/png"
        upload.size = big_size  # triggers early size check
        upload.read = AsyncMock(return_value=b"x" * big_size)

        req = MagicMock()
        req.session = {"user": {"preferred_username": "biguser", "email": "big@example.com"}}

        with pytest.raises(HTTPException) as exc:
            await upload_avatar(req, prof_session, upload)
        assert exc.value.status_code == 413


# ---------------------------------------------------------------------------
# Unit tests — DELETE /api/profile/avatar handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteAvatarHandler:
    """Unit tests for the delete_avatar endpoint handler."""

    @pytest.mark.asyncio
    async def test_clears_avatar_data(self, prof_session):
        """delete_avatar removes avatar_data and returns a Gravatar URL."""
        from app.api.profile import delete_avatar

        profile = UserProfile(
            user_id="delavatar",
            avatar_data="data:image/png;base64,abc",
        )
        prof_session.add(profile)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "delavatar", "email": "del@example.com"}}

        result = await delete_avatar(req, prof_session)
        assert result["avatar_url"].startswith("https://www.gravatar.com/avatar/")

        row = prof_session.query(UserProfile).filter_by(user_id="delavatar").first()
        assert row.avatar_data is None


# ---------------------------------------------------------------------------
# Unit tests — POST /api/profile/change-password handler
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestChangePasswordHandler:
    """Unit tests for the change_password endpoint handler."""

    @pytest.mark.asyncio
    async def test_rejects_non_local_user(self, prof_session):
        """change_password raises 403 for OAuth-only accounts."""
        from app.api.profile import ChangePasswordRequest, change_password

        req = MagicMock()
        req.session = {"user": {"preferred_username": "oauthonly", "email": "oauth@example.com"}}

        body = ChangePasswordRequest(
            current_password="old",
            new_password="newpassword1",
            new_password_confirm="newpassword1",
        )
        with pytest.raises(HTTPException) as exc:
            await change_password(body, req, prof_session)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_wrong_current_password(self, prof_session):
        """change_password raises 403 when current password is wrong."""
        from app.api.profile import ChangePasswordRequest, change_password
        from app.utils.local_auth import hash_password

        local_user = LocalUser(
            email="local@example.com",
            username="localwrong",
            hashed_password=hash_password("correctpassword"),
            is_active=True,
        )
        prof_session.add(local_user)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "localwrong", "email": "local@example.com"}}

        body = ChangePasswordRequest(
            current_password="wrongpassword",
            new_password="newpassword1",
            new_password_confirm="newpassword1",
        )
        with pytest.raises(HTTPException) as exc:
            await change_password(body, req, prof_session)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_password_mismatch(self, prof_session):
        """change_password raises 422 when new passwords do not match."""
        from app.api.profile import ChangePasswordRequest, change_password
        from app.utils.local_auth import hash_password

        local_user = LocalUser(
            email="mismatch@example.com",
            username="mismatchpw",
            hashed_password=hash_password("currentpw"),
            is_active=True,
        )
        prof_session.add(local_user)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "mismatchpw", "email": "mismatch@example.com"}}

        body = ChangePasswordRequest(
            current_password="currentpw",
            new_password="newpassword1",
            new_password_confirm="differentpassword",
        )
        with pytest.raises(HTTPException) as exc:
            await change_password(body, req, prof_session)
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_changes_password_successfully(self, prof_session):
        """change_password updates hashed_password for correct input."""
        from app.api.profile import ChangePasswordRequest, change_password
        from app.utils.local_auth import hash_password, verify_password

        local_user = LocalUser(
            email="success@example.com",
            username="successpw",
            hashed_password=hash_password("oldpassword"),
            is_active=True,
        )
        prof_session.add(local_user)
        prof_session.commit()

        req = MagicMock()
        req.session = {"user": {"preferred_username": "successpw", "email": "success@example.com"}}

        body = ChangePasswordRequest(
            current_password="oldpassword",
            new_password="newpassword1",
            new_password_confirm="newpassword1",
        )
        result = await change_password(body, req, prof_session)
        assert "successfully" in result["detail"].lower()

        updated_user = prof_session.query(LocalUser).filter_by(username="successpw").first()
        assert verify_password("newpassword1", updated_user.hashed_password)


# ---------------------------------------------------------------------------
# Integration tests — HTTP endpoint registration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestProfileEndpoints:
    """Verify profile endpoints are registered and reachable."""

    def test_get_profile_without_session_returns_401(self, prof_client):
        """GET /api/profile returns 401 when no user in session."""
        response = prof_client.get("/api/profile")
        assert response.status_code == 401

    def test_patch_profile_without_session_returns_401(self, prof_client):
        """PATCH /api/profile returns 401 when no user in session."""
        response = prof_client.patch("/api/profile", json={"display_name": "Test"})
        assert response.status_code == 401

    def test_profile_page_accessible(self, prof_client):
        """GET /profile page renders successfully (auth disabled in tests)."""
        response = prof_client.get("/profile", follow_redirects=False)
        # AUTH_ENABLED=False in tests so no redirect; page should render
        assert response.status_code in (200, 302)
