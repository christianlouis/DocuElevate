"""
Tests for the admin user management API (/api/admin/users).

Covers:
- Authentication enforcement (403 for non-admins)
- List users (empty, with doc-only users, with profile-only users, with both)
- Get single user detail
- Create / update user profile via PUT (upsert)
- Delete user profile
- Pagination and search filtering
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import FileRecord, UserProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def au_engine():
    """In-memory SQLite engine for admin-user tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def au_session(au_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=au_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def au_client(au_engine):
    """TestClient that uses an in-memory DB and overrides _require_admin to allow access."""
    from app.api.admin_users import _require_admin
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=au_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_require_admin():
        return {"email": "admin@test.com", "is_admin": True, "name": "Admin"}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_require_admin
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def au_client_nonadmin(au_engine):
    """TestClient without admin override — _require_admin returns 403."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=au_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _make_file(session, owner_id: str, n: int = 1) -> list[FileRecord]:
    """Insert *n* FileRecord rows for the given owner."""
    records = []
    for i in range(n):
        rec = FileRecord(
            filehash=f"hash-{owner_id}-{i}",
            original_filename=f"doc{i}.pdf",
            local_filename=f"/tmp/{owner_id}_{i}.pdf",
            file_size=1024,
            mime_type="application/pdf",
            is_duplicate=False,
            owner_id=owner_id,
        )
        session.add(rec)
        records.append(rec)
    session.commit()
    return records


def _make_profile(session, user_id: str, **kwargs) -> UserProfile:
    """Insert a UserProfile row."""
    kwargs.setdefault("is_blocked", False)
    profile = UserProfile(user_id=user_id, **kwargs)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------


class TestAdminUsersAuth:
    """Endpoints must be restricted to admin users."""

    @pytest.mark.unit
    def test_require_admin_raises_403_when_no_user(self):
        """_require_admin raises 403 when no user in session."""
        from app.api.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            _require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_raises_403_for_non_admin(self):
        """_require_admin raises 403 for a non-admin user."""
        from app.api.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@test.com", "is_admin": False}}

        with pytest.raises(HTTPException) as exc_info:
            _require_admin(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_admin_returns_user_for_admin(self):
        """_require_admin returns the user dict for an admin."""
        from app.api.admin_users import _require_admin

        mock_request = MagicMock()
        user = {"email": "admin@test.com", "is_admin": True}
        mock_request.session = {"user": user}

        result = _require_admin(mock_request)
        assert result == user

    @pytest.mark.integration
    def test_list_users_requires_admin(self, au_client_nonadmin):
        """GET /api/admin/users/ returns 403 for non-admins."""
        resp = au_client_nonadmin.get("/api/admin/users/")
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_put_user_requires_admin(self, au_client_nonadmin):
        """PUT /api/admin/users/<id> returns 403 for non-admins."""
        resp = au_client_nonadmin.put(
            "/api/admin/users/user@example.com",
            json={"is_blocked": False},
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_delete_user_requires_admin(self, au_client_nonadmin):
        """DELETE /api/admin/users/<id> returns 403 for non-admins."""
        resp = au_client_nonadmin.delete("/api/admin/users/user@example.com")
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_get_user_requires_admin(self, au_client_nonadmin):
        """GET /api/admin/users/<id> returns 403 for non-admins."""
        resp = au_client_nonadmin.get("/api/admin/users/user@example.com")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestListUsers:
    """Tests for GET /api/admin/users/."""

    @pytest.mark.unit
    def test_empty_returns_empty_list(self, au_client):
        """No users → empty list with total=0."""
        resp = au_client.get("/api/admin/users/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["users"] == []
        assert data["total"] == 0

    @pytest.mark.unit
    def test_lists_users_with_docs(self, au_client, au_session):
        """Users who have documents appear in the list."""
        _make_file(au_session, "alice@example.com", 3)
        _make_file(au_session, "bob@example.com", 1)

        resp = au_client.get("/api/admin/users/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        ids = {u["user_id"] for u in data["users"]}
        assert "alice@example.com" in ids
        assert "bob@example.com" in ids

    @pytest.mark.unit
    def test_document_count_correct(self, au_client, au_session):
        """document_count reflects the number of files owned by each user."""
        _make_file(au_session, "carol@example.com", 5)

        resp = au_client.get("/api/admin/users/")
        assert resp.status_code == 200
        carol = next(u for u in resp.json()["users"] if u["user_id"] == "carol@example.com")
        assert carol["document_count"] == 5

    @pytest.mark.unit
    def test_lists_profile_only_users(self, au_client, au_session):
        """Users with a profile but no documents still appear."""
        _make_profile(au_session, "profileonly@example.com", display_name="Profile Only")

        resp = au_client.get("/api/admin/users/")
        assert resp.status_code == 200
        ids = {u["user_id"] for u in resp.json()["users"]}
        assert "profileonly@example.com" in ids

    @pytest.mark.unit
    def test_search_filter(self, au_client, au_session):
        """q= parameter filters by user_id substring."""
        _make_file(au_session, "alice@example.com")
        _make_file(au_session, "bob@example.com")

        resp = au_client.get("/api/admin/users/?q=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["users"][0]["user_id"] == "alice@example.com"

    @pytest.mark.unit
    def test_pagination(self, au_client, au_session):
        """per_page and page parameters paginate results."""
        for i in range(6):
            _make_file(au_session, f"user{i:02d}@example.com")

        resp = au_client.get("/api/admin/users/?page=1&per_page=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["users"]) == 3
        assert data["total"] == 6
        assert data["pages"] == 2

    @pytest.mark.unit
    def test_profile_data_merged(self, au_client, au_session):
        """Profile fields (is_blocked, daily_upload_limit, …) are merged into list items."""
        _make_file(au_session, "managed@example.com")
        _make_profile(
            au_session,
            "managed@example.com",
            display_name="Managed User",
            daily_upload_limit=10,
            is_blocked=True,
        )

        resp = au_client.get("/api/admin/users/")
        assert resp.status_code == 200
        user = next(u for u in resp.json()["users"] if u["user_id"] == "managed@example.com")
        assert user["display_name"] == "Managed User"
        assert user["daily_upload_limit"] == 10
        assert user["is_blocked"] is True


# ---------------------------------------------------------------------------
# Get single user
# ---------------------------------------------------------------------------


class TestGetUser:
    """Tests for GET /api/admin/users/{user_id}."""

    @pytest.mark.unit
    def test_get_user_with_docs(self, au_client, au_session):
        """Returns correct document_count and last_upload."""
        _make_file(au_session, "dana@example.com", 2)

        resp = au_client.get("/api/admin/users/dana@example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "dana@example.com"
        assert data["document_count"] == 2
        assert data["is_blocked"] is False

    @pytest.mark.unit
    def test_get_user_with_profile(self, au_client, au_session):
        """Returns profile data when a profile exists."""
        _make_file(au_session, "evan@example.com")
        _make_profile(au_session, "evan@example.com", notes="VIP user", daily_upload_limit=50)

        resp = au_client.get("/api/admin/users/evan@example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "VIP user"
        assert data["daily_upload_limit"] == 50
        assert data["profile"] is not None

    @pytest.mark.unit
    def test_get_user_no_docs_no_profile_returns_defaults(self, au_client):
        """User with no docs and no profile returns zero counts and defaults."""
        resp = au_client.get("/api/admin/users/unknown@example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] == 0
        assert data["profile"] is None
        assert data["is_blocked"] is False


# ---------------------------------------------------------------------------
# Upsert (PUT) endpoint
# ---------------------------------------------------------------------------


class TestUpsertUserProfile:
    """Tests for PUT /api/admin/users/{user_id}."""

    @pytest.mark.unit
    def test_create_profile(self, au_client, au_session):
        """PUT on a user without a profile creates it."""
        resp = au_client.put(
            "/api/admin/users/newuser@example.com",
            json={"display_name": "New User", "daily_upload_limit": 20, "is_blocked": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "newuser@example.com"
        assert data["display_name"] == "New User"
        assert data["daily_upload_limit"] == 20

        # Persisted in DB
        profile = au_session.query(UserProfile).filter_by(user_id="newuser@example.com").first()
        assert profile is not None
        assert profile.display_name == "New User"

    @pytest.mark.unit
    def test_update_existing_profile(self, au_client, au_session):
        """PUT on an existing profile updates it."""
        _make_profile(au_session, "existing@example.com", display_name="Old Name")

        resp = au_client.put(
            "/api/admin/users/existing@example.com",
            json={"display_name": "New Name", "is_blocked": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["display_name"] == "New Name"
        assert data["is_blocked"] is True

    @pytest.mark.unit
    def test_block_user(self, au_client, au_session):
        """Setting is_blocked=True stores correctly."""
        resp = au_client.put(
            "/api/admin/users/blocked@example.com",
            json={"is_blocked": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_blocked"] is True

    @pytest.mark.unit
    def test_null_upload_limit(self, au_client, au_session):
        """daily_upload_limit can be null (use global default)."""
        resp = au_client.put(
            "/api/admin/users/nulllimit@example.com",
            json={"daily_upload_limit": None, "is_blocked": False},
        )
        assert resp.status_code == 200
        assert resp.json()["daily_upload_limit"] is None

    @pytest.mark.unit
    def test_zero_upload_limit_means_unlimited(self, au_client):
        """daily_upload_limit=0 is a valid value meaning 'unlimited'."""
        resp = au_client.put(
            "/api/admin/users/zerolimit@example.com",
            json={"daily_upload_limit": 0, "is_blocked": False},
        )
        assert resp.status_code == 200
        assert resp.json()["daily_upload_limit"] == 0


# ---------------------------------------------------------------------------
# Delete endpoint
# ---------------------------------------------------------------------------


class TestDeleteUserProfile:
    """Tests for DELETE /api/admin/users/{user_id}."""

    @pytest.mark.unit
    def test_delete_existing_profile(self, au_client, au_session):
        """DELETE removes an existing profile; returns 204."""
        _make_profile(au_session, "todelete@example.com")

        resp = au_client.delete("/api/admin/users/todelete@example.com")
        assert resp.status_code == 204

        remaining = au_session.query(UserProfile).filter_by(user_id="todelete@example.com").first()
        assert remaining is None

    @pytest.mark.unit
    def test_delete_nonexistent_profile_returns_404(self, au_client):
        """DELETE on unknown user_id returns 404."""
        resp = au_client.delete("/api/admin/users/doesnotexist@example.com")
        assert resp.status_code == 404

    @pytest.mark.unit
    def test_delete_profile_does_not_remove_documents(self, au_client, au_session):
        """Deleting a profile must not remove documents owned by that user."""
        _make_file(au_session, "hasfiles@example.com", 3)
        _make_profile(au_session, "hasfiles@example.com")

        resp = au_client.delete("/api/admin/users/hasfiles@example.com")
        assert resp.status_code == 204

        doc_count = au_session.query(FileRecord).filter_by(owner_id="hasfiles@example.com").count()
        assert doc_count == 3


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestUserProfileModel:
    """Unit tests for the UserProfile SQLAlchemy model."""

    @pytest.mark.unit
    def test_user_profile_has_required_columns(self, au_session):
        """UserProfile can be created with minimal required fields."""
        profile = UserProfile(user_id="test@example.com", is_blocked=False)
        au_session.add(profile)
        au_session.commit()
        au_session.refresh(profile)

        assert profile.id is not None
        assert profile.user_id == "test@example.com"
        assert profile.is_blocked is False
        assert profile.display_name is None
        assert profile.daily_upload_limit is None
        assert profile.notes is None

    @pytest.mark.unit
    def test_user_profile_unique_user_id(self, au_session):
        """Two profiles with the same user_id should raise an integrity error."""
        from sqlalchemy.exc import IntegrityError

        au_session.add(UserProfile(user_id="dup@example.com", is_blocked=False))
        au_session.commit()
        au_session.add(UserProfile(user_id="dup@example.com", is_blocked=False))
        with pytest.raises(IntegrityError):
            au_session.commit()
        au_session.rollback()
