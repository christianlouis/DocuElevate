"""Tests for the personal API tokens feature (app/api/api_tokens.py + auth integration)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import ApiToken

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_OWNER = "tokenuser@example.com"
_OTHER_OWNER = "other@example.com"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tok_engine():
    """In-memory SQLite engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def tok_session(tok_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=tok_engine)
    session = Session()
    yield session
    session.close()


def _make_client(tok_engine, owner_id: str = _OWNER) -> TestClient:
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.api.api_tokens import _get_owner_id
    from app.main import app

    Session = sessionmaker(bind=tok_engine)

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

    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    return client


def _make_unauthenticated_client(tok_engine) -> TestClient:
    """Return a TestClient that only overrides ``get_db`` (no auth injection).

    This exercises the real ``_get_owner_id`` → ``get_current_owner_id``
    authentication path.  Any request made with this client that does not
    carry a valid session or Bearer token will receive a 401 from the
    actual auth code, not from a mocked dependency.

    The caller is responsible for clearing overrides via ``_cleanup(app)``
    after the test completes (typically in a ``finally`` block).
    """
    from app.main import app

    Session = sessionmaker(bind=tok_engine)

    def _override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    return client


def _cleanup(app):
    """Remove dependency overrides after test."""
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests – Token CRUD
# ---------------------------------------------------------------------------


class TestTokenCreate:
    """Tests for POST /api/api-tokens/."""

    @pytest.mark.unit
    def test_create_token_returns_full_token(self, tok_engine):
        """Creating a token should return the full plaintext token exactly once."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.post("/api/api-tokens/", json={"name": "Test Token"})
            assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "token" in data
            assert data["token"].startswith("de_")
            assert data["name"] == "Test Token"
            assert data["is_active"] is True
            assert data["token_prefix"] == data["token"][:12]
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_token_stored_as_hash(self, tok_engine, tok_session):
        """The database should only store a PBKDF2-HMAC-SHA256 hash, never the plaintext."""
        from app.api.api_tokens import hash_token
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.post("/api/api-tokens/", json={"name": "Hash Check"})
            token_plaintext = resp.json()["token"]
            expected_hash = hash_token(token_plaintext)

            db_token = tok_session.query(ApiToken).first()
            assert db_token is not None
            assert db_token.token_hash == expected_hash
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_create_token_empty_name_rejected(self, tok_engine):
        """An empty token name should be rejected with 422."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.post("/api/api-tokens/", json={"name": ""})
            assert resp.status_code == 422
        finally:
            _cleanup(app)


class TestTokenList:
    """Tests for GET /api/api-tokens/."""

    @pytest.mark.unit
    def test_list_tokens_empty(self, tok_engine):
        """Listing tokens when none exist should return an empty list."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.get("/api/api-tokens/")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_list_tokens_returns_multiple(self, tok_engine):
        """Listing tokens should return all tokens for the current user."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            client.post("/api/api-tokens/", json={"name": "Token A"})
            client.post("/api/api-tokens/", json={"name": "Token B"})
            resp = client.get("/api/api-tokens/")
            assert resp.status_code == 200
            tokens = resp.json()
            assert len(tokens) == 2
            # Full plaintext should NOT appear in list
            for t in tokens:
                assert "token" not in t
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_list_tokens_isolation(self, tok_engine):
        """Users should only see their own tokens."""
        from app.main import app

        client_a = _make_client(tok_engine, _OWNER)
        try:
            client_a.post("/api/api-tokens/", json={"name": "Owner A Token"})
        finally:
            _cleanup(app)

        client_b = _make_client(tok_engine, _OTHER_OWNER)
        try:
            resp = client_b.get("/api/api-tokens/")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(app)


class TestTokenRevoke:
    """Tests for DELETE /api/api-tokens/{id}."""

    @pytest.mark.unit
    def test_revoke_token(self, tok_engine):
        """Revoking a token should set is_active=False."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            create_resp = client.post("/api/api-tokens/", json={"name": "To Revoke"})
            token_id = create_resp.json()["id"]

            resp = client.delete(f"/api/api-tokens/{token_id}")
            assert resp.status_code == 200

            list_resp = client.get("/api/api-tokens/")
            revoked = [t for t in list_resp.json() if t["id"] == token_id][0]
            assert revoked["is_active"] is False
            assert revoked["revoked_at"] is not None
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_already_revoked_token(self, tok_engine):
        """Revoking an already-revoked token should return 400."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            create_resp = client.post("/api/api-tokens/", json={"name": "Double Revoke"})
            token_id = create_resp.json()["id"]
            client.delete(f"/api/api-tokens/{token_id}")

            resp = client.delete(f"/api/api-tokens/{token_id}")
            assert resp.status_code == 400
            assert resp.json()["detail"] == "Token is already revoked"
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_nonexistent_token(self, tok_engine):
        """Revoking a token that doesn't exist should return 404."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.delete("/api/api-tokens/99999")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "Token not found"
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_token_unauthenticated(self, tok_engine):
        """Revoking a token without authentication should return 401.

        Uses a client that only overrides ``get_db`` so that the real
        ``_get_owner_id`` → ``get_current_owner_id`` path is exercised.
        Sending no session or Bearer credentials means ``get_current_owner_id``
        returns ``None``, and ``_get_owner_id`` raises a 401.
        """
        from app.main import app

        client = _make_unauthenticated_client(tok_engine)
        try:
            resp = client.delete("/api/api-tokens/1")
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Not authenticated"
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_token_database_error(self, tok_engine, tok_session):
        """Revoking a token should rollback and raise 500 if database commit fails.

        The test verifies two properties:
        1. ``db.rollback()`` is actually called when commit raises (not just that
           the endpoint returns 500).
        2. After the rollback the token remains active in the database.

        To ensure the assertions are meaningful, the patched ``commit`` first
        flushes the session (so the changes *are* staged inside the transaction)
        before raising.  Without a subsequent ``rollback()`` the flushed state
        would still be visible to other sessions, so the ``is_active`` check
        would catch a missing rollback call.
        """
        from unittest.mock import patch

        from sqlalchemy.orm import Session as SASession

        from app.main import app

        client = _make_client(tok_engine)
        try:
            create_resp = client.post("/api/api-tokens/", json={"name": "DB Error Test"})
            token_id = create_resp.json()["id"]

            # Wrap commit: flush first so changes are staged in the transaction,
            # then raise to simulate a commit failure after data has been written.
            def _fail_after_flush(self):
                self.flush()  # stage changes inside the open transaction
                raise Exception("DB Failure")

            # Spy on rollback so we can assert it is called.
            rollback_called = False
            real_rollback = SASession.rollback

            def _spy_rollback(self):
                nonlocal rollback_called
                rollback_called = True
                real_rollback(self)

            with (
                patch.object(SASession, "commit", _fail_after_flush),
                patch.object(SASession, "rollback", _spy_rollback),
            ):
                resp = client.delete(f"/api/api-tokens/{token_id}")
                assert resp.status_code == 500

            # rollback() must have been called to undo the flushed changes.
            assert rollback_called, "db.rollback() was not called after commit failure"

            # After rollback the token must still be active in the database.
            db_token = tok_session.query(ApiToken).filter(ApiToken.id == token_id).first()
            assert db_token.is_active is True
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_token_invalid_id_format(self, tok_engine):
        """Revoking a token with a non-integer ID should return 422 Unprocessable Entity."""
        from app.main import app

        client = _make_client(tok_engine)
        try:
            resp = client.delete("/api/api-tokens/abc")
            assert resp.status_code == 422
        finally:
            _cleanup(app)

    @pytest.mark.unit
    def test_revoke_other_users_token(self, tok_engine):
        """A user should not be able to revoke another user's token."""
        from app.main import app

        # Owner A creates a token
        client_a = _make_client(tok_engine, _OWNER)
        try:
            create_resp = client_a.post("/api/api-tokens/", json={"name": "A's Token"})
            token_id = create_resp.json()["id"]
        finally:
            _cleanup(app)

        # Owner B tries to revoke it
        client_b = _make_client(tok_engine, _OTHER_OWNER)
        try:
            resp = client_b.delete(f"/api/api-tokens/{token_id}")
            assert resp.status_code == 404
        finally:
            _cleanup(app)


# ---------------------------------------------------------------------------
# Tests – Bearer token authentication
# ---------------------------------------------------------------------------


class TestBearerAuth:
    """Tests for API token authentication via Authorization: Bearer header."""

    @pytest.mark.unit
    def test_bearer_resolve_user_with_valid_token(self, tok_engine, tok_session):
        """_resolve_bearer_user should return a user dict for a valid token."""
        from unittest.mock import MagicMock

        # Create a token directly in DB
        from app.api.api_tokens import generate_api_token, hash_token
        from app.auth import _resolve_bearer_user

        plaintext = generate_api_token()
        token_hash = hash_token(plaintext)

        db_token = ApiToken(
            owner_id=_OWNER,
            name="Test Bearer",
            token_hash=token_hash,
            token_prefix=plaintext[:12],
            is_active=True,
        )
        tok_session.add(db_token)
        tok_session.commit()

        # Build a mock request
        mock_request = MagicMock()
        mock_request.headers = {"authorization": f"Bearer {plaintext}"}
        mock_request.client.host = "127.0.0.1"

        user = _resolve_bearer_user(mock_request, tok_session)
        assert user is not None
        assert user["preferred_username"] == _OWNER
        assert user["_api_token_id"] == db_token.id

    @pytest.mark.unit
    def test_bearer_resolve_user_invalid_token(self, tok_engine, tok_session):
        """_resolve_bearer_user should return None for an invalid token."""
        from unittest.mock import MagicMock

        from app.auth import _resolve_bearer_user

        mock_request = MagicMock()
        mock_request.headers = {"authorization": "Bearer de_invalid_token"}
        mock_request.client.host = "127.0.0.1"

        user = _resolve_bearer_user(mock_request, tok_session)
        assert user is None

    @pytest.mark.unit
    def test_bearer_resolve_no_header(self, tok_engine, tok_session):
        """_resolve_bearer_user should return None when no Auth header present."""
        from unittest.mock import MagicMock

        from app.auth import _resolve_bearer_user

        mock_request = MagicMock()
        mock_request.headers = {}

        user = _resolve_bearer_user(mock_request, tok_session)
        assert user is None

    @pytest.mark.unit
    def test_bearer_updates_usage_tracking(self, tok_engine, tok_session):
        """Using a Bearer token should update last_used_at and last_used_ip."""
        from unittest.mock import MagicMock

        from app.api.api_tokens import generate_api_token, hash_token
        from app.auth import _resolve_bearer_user

        plaintext = generate_api_token()
        token_hash = hash_token(plaintext)

        db_token = ApiToken(
            owner_id=_OWNER,
            name="Usage Track",
            token_hash=token_hash,
            token_prefix=plaintext[:12],
            is_active=True,
        )
        tok_session.add(db_token)
        tok_session.commit()

        assert db_token.last_used_at is None
        assert db_token.last_used_ip is None

        mock_request = MagicMock()
        mock_request.headers = {
            "authorization": f"Bearer {plaintext}",
            "x-forwarded-for": "203.0.113.42",
        }
        mock_request.client.host = "10.0.0.1"

        _resolve_bearer_user(mock_request, tok_session)

        tok_session.refresh(db_token)
        assert db_token.last_used_at is not None
        assert db_token.last_used_ip == "203.0.113.42"

    @pytest.mark.unit
    def test_revoked_token_not_resolved(self, tok_engine, tok_session):
        """A revoked token should not resolve to a user."""
        from unittest.mock import MagicMock

        from app.api.api_tokens import generate_api_token, hash_token
        from app.auth import _resolve_bearer_user

        plaintext = generate_api_token()
        token_hash = hash_token(plaintext)

        db_token = ApiToken(
            owner_id=_OWNER,
            name="Revoked Token",
            token_hash=token_hash,
            token_prefix=plaintext[:12],
            is_active=False,  # Already revoked
        )
        tok_session.add(db_token)
        tok_session.commit()

        mock_request = MagicMock()
        mock_request.headers = {"authorization": f"Bearer {plaintext}"}
        mock_request.client.host = "127.0.0.1"

        user = _resolve_bearer_user(mock_request, tok_session)
        assert user is None


# ---------------------------------------------------------------------------
# Tests – Token generation utilities
# ---------------------------------------------------------------------------


class TestTokenUtils:
    """Tests for token generation and hashing utilities."""

    @pytest.mark.unit
    def test_generate_api_token_format(self):
        """Generated tokens should start with 'de_' prefix."""
        from app.api.api_tokens import generate_api_token

        token = generate_api_token()
        assert token.startswith("de_")
        assert len(token) > 20  # Should be reasonably long

    @pytest.mark.unit
    def test_generate_api_token_unique(self):
        """Each generated token should be unique."""
        from app.api.api_tokens import generate_api_token

        tokens = {generate_api_token() for _ in range(100)}
        assert len(tokens) == 100

    @pytest.mark.unit
    def test_hash_token_deterministic(self):
        """Hashing the same token should always produce the same result."""
        from app.api.api_tokens import hash_token

        token = "de_test_token_value"
        assert hash_token(token) == hash_token(token)

    @pytest.mark.unit
    def test_hash_token_output_properties(self):
        """Token hash should be a 64-character lowercase hex digest."""
        from app.api.api_tokens import hash_token

        token = "de_test_token_value"
        h = hash_token(token)
        assert isinstance(h, str)
        assert len(h) == 64
        # All characters should be valid lowercase hex digits.
        int(h, 16)
        assert h == h.lower()
