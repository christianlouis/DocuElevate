"""Tests for the session management API endpoints (app/api/sessions.py).

Covers:
* _get_owner_id dependency helper (authenticated and unauthenticated paths)
* GET /api/sessions/  – list sessions
* DELETE /api/sessions/{id}  – revoke a single session
* POST /api/sessions/revoke-all  – log off everywhere
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import itsdangerous
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import UserSession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_OWNER = "sessionuser@example.com"
_OTHER_OWNER = "other@example.com"
_SESSION_SECRET = "test_secret_key_for_testing_must_be_at_least_32_characters_long"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_cookie(session_data: dict) -> str:
    """Encode *session_data* as a signed Starlette session cookie value."""
    signer = itsdangerous.TimestampSigner(_SESSION_SECRET)
    data = base64.b64encode(json.dumps(session_data).encode("utf-8"))
    return signer.sign(data).decode("utf-8")


def _make_user_session(
    db,
    user_id: str = _OWNER,
    session_token: str | None = None,
    expires_delta: timedelta = timedelta(days=30),
) -> UserSession:
    """Create and persist a UserSession in *db*."""
    now = datetime.now(timezone.utc)
    token = session_token or secrets.token_urlsafe(32)
    session = UserSession(
        session_token=token,
        user_id=user_id,
        ip_address="127.0.0.1",
        user_agent="TestBrowser/1.0",
        device_info="TestBrowser on Linux",
        created_at=now,
        last_active_at=now,
        expires_at=now + expires_delta,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sess_engine():
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
def sess_db(sess_engine):
    """Database session scoped to one test."""
    Session = sessionmaker(bind=sess_engine)
    session = Session()
    yield session
    session.close()


def _make_client(sess_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.sessions import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=sess_engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def _override_owner():
        return owner_id

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_owner_id] = _override_owner

    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def _make_unauthenticated_client(sess_engine) -> TestClient:
    """Return a TestClient with only the DB overridden (no auth injection)."""
    from app.main import app

    Session = sessionmaker(bind=sess_engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db

    return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


def _cleanup():
    """Remove all dependency overrides from the app."""
    from app.main import app

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests – _get_owner_id helper
# ---------------------------------------------------------------------------


class TestGetOwnerId:
    """Tests for the _get_owner_id dependency helper in app/api/sessions.py."""

    @pytest.mark.unit
    def test_unauthenticated_raises_401(self):
        """_get_owner_id should raise HTTP 401 when the user is not authenticated."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from app.api.sessions import _get_owner_id

        mock_request = MagicMock()
        with patch("app.api.sessions.get_current_owner_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                _get_owner_id(mock_request)
            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Not authenticated"

    @pytest.mark.unit
    def test_authenticated_returns_owner_id(self):
        """_get_owner_id should return the owner_id when the user is authenticated."""
        from unittest.mock import MagicMock

        from app.api.sessions import _get_owner_id

        mock_request = MagicMock()
        with patch("app.api.sessions.get_current_owner_id", return_value=_OWNER):
            result = _get_owner_id(mock_request)
            assert result == _OWNER


# ---------------------------------------------------------------------------
# Tests – GET /api/sessions/
# ---------------------------------------------------------------------------


class TestListSessions:
    """Tests for GET /api/sessions/."""

    @pytest.mark.unit
    def test_list_sessions_empty(self, sess_engine):
        """Returns an empty session list when no sessions exist."""
        client = _make_client(sess_engine)
        try:
            resp = client.get("/api/sessions/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["sessions"] == []
            assert "session_lifetime_days" in data
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_list_sessions_returns_active_sessions(self, sess_engine, sess_db):
        """Returns session details for all active sessions belonging to the user."""
        _make_user_session(sess_db, user_id=_OWNER)
        _make_user_session(sess_db, user_id=_OWNER)
        # A session owned by a different user must not appear.
        _make_user_session(sess_db, user_id=_OTHER_OWNER)

        client = _make_client(sess_engine)
        try:
            resp = client.get("/api/sessions/")
            assert resp.status_code == 200
            sessions = resp.json()["sessions"]
            assert len(sessions) == 2
            for s in sessions:
                assert "id" in s
                assert "device_info" in s
                assert "ip_address" in s
                assert "created_at" in s
                assert "last_active_at" in s
                assert "expires_at" in s
                assert "is_current" in s
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_list_sessions_marks_current_session(self, sess_engine, sess_db):
        """The session whose token matches request.session['_session_token'] is
        marked ``is_current=True``; all others are ``False``."""
        current_token = secrets.token_urlsafe(32)
        current_session = _make_user_session(sess_db, user_id=_OWNER, session_token=current_token)
        other_session = _make_user_session(sess_db, user_id=_OWNER)

        cookie = _make_session_cookie({"_session_token": current_token})

        client = _make_client(sess_engine)
        try:
            resp = client.get("/api/sessions/", cookies={"session": cookie})
            assert resp.status_code == 200
            sessions = resp.json()["sessions"]
            session_map = {s["id"]: s for s in sessions}
            assert session_map[current_session.id]["is_current"] is True
            assert session_map[other_session.id]["is_current"] is False
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_list_sessions_no_current_token(self, sess_engine, sess_db):
        """When no _session_token is present, all sessions have is_current=False."""
        _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            resp = client.get("/api/sessions/")
            assert resp.status_code == 200
            for s in resp.json()["sessions"]:
                assert s["is_current"] is False
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_list_sessions_returns_lifetime_days(self, sess_engine):
        """Response always includes session_lifetime_days."""
        client = _make_client(sess_engine)
        try:
            resp = client.get("/api/sessions/")
            assert resp.status_code == 200
            assert isinstance(resp.json()["session_lifetime_days"], int)
            assert resp.json()["session_lifetime_days"] >= 1
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests – DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------


class TestRevokeSingleSession:
    """Tests for DELETE /api/sessions/{session_id}."""

    @pytest.mark.unit
    def test_revoke_session_success(self, sess_engine, sess_db):
        """Revoking an owned session returns 204 No Content."""
        session = _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            resp = client.delete(f"/api/sessions/{session.id}")
            assert resp.status_code == 204
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_session_not_found(self, sess_engine):
        """Revoking a non-existent session returns 404."""
        client = _make_client(sess_engine)
        try:
            resp = client.delete("/api/sessions/999999")
            assert resp.status_code == 404
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_session_belonging_to_other_user_returns_404(self, sess_engine, sess_db):
        """A user cannot revoke another user's session (returns 404)."""
        other_session = _make_user_session(sess_db, user_id=_OTHER_OWNER)

        client = _make_client(sess_engine, owner_id=_OWNER)
        try:
            resp = client.delete(f"/api/sessions/{other_session.id}")
            assert resp.status_code == 404
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_session_audit_failure_does_not_break_response(self, sess_engine, sess_db):
        """Even if the audit service raises an exception, the response is still 204."""
        session = _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            with patch("app.utils.audit_service.record_event", side_effect=Exception("audit down")):
                resp = client.delete(f"/api/sessions/{session.id}")
            assert resp.status_code == 204
        finally:
            _cleanup()


# ---------------------------------------------------------------------------
# Tests – POST /api/sessions/revoke-all
# ---------------------------------------------------------------------------


class TestRevokeAllSessions:
    """Tests for POST /api/sessions/revoke-all."""

    @pytest.mark.unit
    def test_revoke_all_no_sessions(self, sess_engine):
        """Returns revoked_count=0 when there are no sessions to revoke."""
        client = _make_client(sess_engine)
        try:
            resp = client.post("/api/sessions/revoke-all")
            assert resp.status_code == 200
            data = resp.json()
            assert data["revoked_count"] == 0
            assert "message" in data
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_all_revokes_all_sessions(self, sess_engine, sess_db):
        """All active sessions for the user are revoked."""
        _make_user_session(sess_db, user_id=_OWNER)
        _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            resp = client.post("/api/sessions/revoke-all")
            assert resp.status_code == 200
            data = resp.json()
            assert data["revoked_count"] == 2
            assert "2" in data["message"]
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_all_preserves_current_session(self, sess_engine, sess_db):
        """The session matching the current _session_token is NOT revoked."""
        current_token = secrets.token_urlsafe(32)
        current_session = _make_user_session(sess_db, user_id=_OWNER, session_token=current_token)
        _make_user_session(sess_db, user_id=_OWNER)
        _make_user_session(sess_db, user_id=_OWNER)

        cookie = _make_session_cookie({"_session_token": current_token})

        client = _make_client(sess_engine)
        try:
            resp = client.post("/api/sessions/revoke-all", cookies={"session": cookie})
            assert resp.status_code == 200
            # Only the two non-current sessions should be revoked.
            assert resp.json()["revoked_count"] == 2

            # The current session must still be active in the DB.
            sess_db.refresh(current_session)
            assert current_session.is_revoked is False
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_all_current_session_token_not_in_db(self, sess_engine, sess_db):
        """When the _session_token in the cookie doesn't match any DB row,
        all sessions are revoked (no session is preserved)."""
        _make_user_session(sess_db, user_id=_OWNER)

        # Cookie references a token that does not exist in the DB.
        cookie = _make_session_cookie({"_session_token": "ghost_token_xyz"})

        client = _make_client(sess_engine)
        try:
            resp = client.post("/api/sessions/revoke-all", cookies={"session": cookie})
            assert resp.status_code == 200
            assert resp.json()["revoked_count"] == 1
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_all_audit_failure_does_not_break_response(self, sess_engine, sess_db):
        """Even if the audit service raises, revoke-all still returns 200."""
        _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            with patch("app.utils.audit_service.record_event", side_effect=Exception("audit down")):
                resp = client.post("/api/sessions/revoke-all")
            assert resp.status_code == 200
            assert resp.json()["revoked_count"] == 1
        finally:
            _cleanup()

    @pytest.mark.unit
    def test_revoke_all_message_format(self, sess_engine, sess_db):
        """Response message includes the count and mentions API tokens."""
        _make_user_session(sess_db, user_id=_OWNER)

        client = _make_client(sess_engine)
        try:
            resp = client.post("/api/sessions/revoke-all")
            assert resp.status_code == 200
            msg = resp.json()["message"]
            assert "1" in msg
            assert "API" in msg or "token" in msg.lower()
        finally:
            _cleanup()
