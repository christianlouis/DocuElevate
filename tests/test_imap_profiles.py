"""Tests for app/api/imap_profiles.py and app/utils/allowed_types category helpers."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import ImapIngestionProfile
from app.utils.allowed_types import (
    ALL_CATEGORIES,
    DEFAULT_CATEGORIES,
    FILE_TYPE_CATEGORIES,
    get_allowed_types_for_categories,
)

# ---------------------------------------------------------------------------
# Integration test constants
# ---------------------------------------------------------------------------

_OWNER = "profile_user@example.com"
_OTHER = "other_user@example.com"


# ---------------------------------------------------------------------------
# Shared integration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def profile_engine():
    """In-memory SQLite engine for IMAP profile tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def profile_session(profile_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=profile_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def profile_client(profile_engine):
    """TestClient authenticated as _OWNER with DB overridden."""
    from app.api.imap_profiles import _get_owner_id
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=profile_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_owner():
        return _OWNER

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_get_owner_id] = override_owner
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(profile_engine):
    """TestClient without authentication (DB still overridden)."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=profile_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _make_profile(
    session,
    owner: str | None = _OWNER,
    name: str = "Test Profile",
    categories_json: str = '["pdf","office"]',
    is_builtin: bool = False,
) -> ImapIngestionProfile:
    """Create an ImapIngestionProfile row in the database."""
    prof = ImapIngestionProfile(
        name=name,
        description="A test profile",
        owner_id=owner,
        allowed_categories=categories_json,
        is_builtin=is_builtin,
    )
    session.add(prof)
    session.commit()
    session.refresh(prof)
    return prof


@pytest.mark.unit
class TestFileTypeCategories:
    """Tests for FILE_TYPE_CATEGORIES and get_allowed_types_for_categories."""

    def test_all_category_keys_present(self):
        """Test that the six expected categories exist."""
        assert set(FILE_TYPE_CATEGORIES.keys()) == {"pdf", "office", "opendocument", "text", "web", "images"}

    def test_each_category_has_required_fields(self):
        """Test that every category entry has label, description, mime_types, extensions."""
        for key, info in FILE_TYPE_CATEGORIES.items():
            assert "label" in info, f"Category '{key}' missing 'label'"
            assert "description" in info, f"Category '{key}' missing 'description'"
            assert "mime_types" in info, f"Category '{key}' missing 'mime_types'"
            assert "extensions" in info, f"Category '{key}' missing 'extensions'"

    def test_pdf_category_contains_pdf_mime(self):
        """Test that the pdf category includes application/pdf."""
        assert "application/pdf" in FILE_TYPE_CATEGORIES["pdf"]["mime_types"]
        assert ".pdf" in FILE_TYPE_CATEGORIES["pdf"]["extensions"]

    def test_images_category_contains_jpeg(self):
        """Test that the images category includes image/jpeg."""
        assert "image/jpeg" in FILE_TYPE_CATEGORIES["images"]["mime_types"]
        assert ".jpg" in FILE_TYPE_CATEGORIES["images"]["extensions"]
        assert ".png" in FILE_TYPE_CATEGORIES["images"]["extensions"]

    def test_get_allowed_types_for_default_categories(self):
        """Test that DEFAULT_CATEGORIES excludes image MIME types."""
        mime_types, extensions = get_allowed_types_for_categories(DEFAULT_CATEGORIES)
        assert "application/pdf" in mime_types
        assert "application/msword" in mime_types
        # images should NOT be in the default
        assert "image/jpeg" not in mime_types
        assert ".jpg" not in extensions

    def test_get_allowed_types_for_all_categories(self):
        """Test that ALL_CATEGORIES includes image MIME types."""
        mime_types, extensions = get_allowed_types_for_categories(ALL_CATEGORIES)
        assert "image/jpeg" in mime_types
        assert ".jpg" in extensions
        assert "application/pdf" in mime_types

    def test_get_allowed_types_returns_frozensets(self):
        """Test that returned sets are frozensets."""
        mime_types, extensions = get_allowed_types_for_categories(["pdf"])
        assert isinstance(mime_types, frozenset)
        assert isinstance(extensions, frozenset)

    def test_get_allowed_types_unknown_category_ignored(self):
        """Test that unknown category keys are silently ignored."""
        mime_types, extensions = get_allowed_types_for_categories(["pdf", "nonexistent_category"])
        assert "application/pdf" in mime_types  # 'pdf' still works
        # No crash for unknown key

    def test_get_allowed_types_empty_list(self):
        """Test empty category list returns empty sets."""
        mime_types, extensions = get_allowed_types_for_categories([])
        assert mime_types == frozenset()
        assert extensions == frozenset()

    def test_default_categories_excludes_images(self):
        """Test that DEFAULT_CATEGORIES does not include 'images'."""
        assert "images" not in DEFAULT_CATEGORIES

    def test_all_categories_includes_images(self):
        """Test that ALL_CATEGORIES includes 'images'."""
        assert "images" in ALL_CATEGORIES

    def test_all_categories_is_superset_of_default(self):
        """Test that ALL_CATEGORIES contains all DEFAULT_CATEGORIES."""
        for cat in DEFAULT_CATEGORIES:
            assert cat in ALL_CATEGORIES


@pytest.mark.unit
class TestImapProfilesApiLogic:
    """Tests for ingestion profile validation helpers."""

    def test_validate_categories_accepts_valid_keys(self):
        """Test that valid category keys pass validation."""
        from app.api.imap_profiles import _validate_categories

        result = _validate_categories(["pdf", "office", "images"])
        assert set(result) == {"pdf", "office", "images"}

    def test_validate_categories_rejects_unknown_key(self):
        """Test that unknown category keys raise 422."""
        from fastapi import HTTPException

        from app.api.imap_profiles import _validate_categories

        with pytest.raises(HTTPException) as exc_info:
            _validate_categories(["pdf", "nonexistent"])
        assert exc_info.value.status_code == 422
        assert "nonexistent" in str(exc_info.value.detail)

    def test_validate_categories_deduplicates(self):
        """Test that duplicate category keys are de-duplicated while preserving order."""
        from app.api.imap_profiles import _validate_categories

        result = _validate_categories(["pdf", "pdf", "office", "pdf"])
        assert result == ["pdf", "office"]

    def test_to_response_serializes_profile(self, tmp_path):
        """Test _to_response produces expected dict shape."""
        from unittest.mock import MagicMock

        from app.api.imap_profiles import _to_response

        profile = MagicMock()
        profile.id = 42
        profile.name = "My Profile"
        profile.description = "Test description"
        profile.owner_id = "user@example.com"
        profile.allowed_categories = '["pdf","office"]'
        profile.is_builtin = False
        profile.created_at = None
        profile.updated_at = None

        result = _to_response(profile)
        assert result["id"] == 42
        assert result["name"] == "My Profile"
        assert result["allowed_categories"] == ["pdf", "office"]
        assert len(result["categories_detail"]) == 2
        assert result["categories_detail"][0]["key"] == "pdf"
        assert result["is_builtin"] is False

    def test_to_response_handles_invalid_categories_json(self):
        """Test _to_response gracefully handles invalid JSON in allowed_categories."""
        from unittest.mock import MagicMock

        from app.api.imap_profiles import _to_response

        profile = MagicMock()
        profile.id = 1
        profile.name = "Broken"
        profile.description = None
        profile.owner_id = None
        profile.allowed_categories = "this is not valid json {"
        profile.is_builtin = True
        profile.created_at = None
        profile.updated_at = None

        result = _to_response(profile)
        assert result["allowed_categories"] == []

    def test_get_owner_id_returns_owner_when_authenticated(self):
        """Test that _get_owner_id returns the owner_id when get_current_owner_id succeeds."""
        from unittest.mock import MagicMock, patch

        from app.api.imap_profiles import _get_owner_id

        request = MagicMock()
        with patch("app.api.imap_profiles.get_current_owner_id", return_value="user@example.com"):
            result = _get_owner_id(request)
        assert result == "user@example.com"


# ---------------------------------------------------------------------------
# Integration tests – list categories endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListCategories:
    """Tests for GET /api/imap-profiles/categories."""

    def test_list_categories_returns_all(self, profile_client):
        """Authenticated request returns all available file-type categories."""
        resp = profile_client.get("/api/imap-profiles/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        keys = {item["key"] for item in data}
        assert keys == set(FILE_TYPE_CATEGORIES.keys())
        for item in data:
            assert "key" in item
            assert "label" in item
            assert "description" in item

    def test_list_categories_unauthenticated(self, anon_client):
        """Unauthenticated request returns 401."""
        resp = anon_client.get("/api/imap-profiles/categories")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – list profiles endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListProfiles:
    """Tests for GET /api/imap-profiles/."""

    def test_list_empty(self, profile_client, profile_session):
        """Listing profiles when none exist returns an empty list."""
        resp = profile_client.get("/api/imap-profiles/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_includes_own_profiles(self, profile_client, profile_session):
        """Returns profiles owned by the current user."""
        _make_profile(profile_session, owner=_OWNER, name="My Profile")
        resp = profile_client.get("/api/imap-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["name"] == "My Profile" for p in data)

    def test_list_includes_global_profiles(self, profile_client, profile_session):
        """Returns system-global profiles (owner_id=None)."""
        _make_profile(profile_session, owner=None, name="Global Profile", is_builtin=True)
        resp = profile_client.get("/api/imap-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        assert any(p["name"] == "Global Profile" for p in data)

    def test_list_excludes_other_users_profiles(self, profile_client, profile_session):
        """Profiles owned by other users are not returned."""
        _make_profile(profile_session, owner=_OTHER, name="Other Profile")
        resp = profile_client.get("/api/imap-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        assert not any(p["name"] == "Other Profile" for p in data)

    def test_list_unauthenticated(self, anon_client):
        """Unauthenticated request returns 401."""
        resp = anon_client.get("/api/imap-profiles/")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – create profile endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateProfile:
    """Tests for POST /api/imap-profiles/."""

    def test_create_success(self, profile_client, profile_session):
        """Creating a valid profile returns 201 with the new profile data."""
        payload = {"name": "New Profile", "description": "desc", "allowed_categories": ["pdf", "office"]}
        resp = profile_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Profile"
        assert data["description"] == "desc"
        assert data["allowed_categories"] == ["pdf", "office"]
        assert data["is_builtin"] is False
        assert data["owner_id"] == _OWNER
        assert "id" in data

    def test_create_deduplicates_categories(self, profile_client):
        """Duplicate categories in the request are de-duplicated."""
        payload = {"name": "Dedup Profile", "allowed_categories": ["pdf", "pdf", "office"]}
        resp = profile_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 201
        assert resp.json()["allowed_categories"] == ["pdf", "office"]

    def test_create_invalid_category_returns_422(self, profile_client):
        """Unknown category keys cause a 422 response."""
        payload = {"name": "Bad Profile", "allowed_categories": ["pdf", "nonexistent"]}
        resp = profile_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 422

    def test_create_missing_name_returns_422(self, profile_client):
        """Missing required 'name' field causes a 422 response."""
        payload = {"allowed_categories": ["pdf"]}
        resp = profile_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 422

    def test_create_empty_categories_returns_422(self, profile_client):
        """An empty allowed_categories list causes a 422 response."""
        payload = {"name": "Empty Cats", "allowed_categories": []}
        resp = profile_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 422

    def test_create_unauthenticated(self, anon_client):
        """Unauthenticated request returns 401."""
        payload = {"name": "X", "allowed_categories": ["pdf"]}
        resp = anon_client.post("/api/imap-profiles/", json=payload)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – get single profile endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetProfile:
    """Tests for GET /api/imap-profiles/{id}."""

    def test_get_own_profile(self, profile_client, profile_session):
        """Owner can retrieve their own profile."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = profile_client.get(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == prof.id
        assert data["name"] == prof.name

    def test_get_global_profile(self, profile_client, profile_session):
        """Any authenticated user can retrieve a global (owner_id=None) profile."""
        prof = _make_profile(profile_session, owner=None, name="Builtin", is_builtin=True)
        resp = profile_client.get(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Builtin"

    def test_get_not_found(self, profile_client):
        """Requesting a non-existent profile returns 404."""
        resp = profile_client.get("/api/imap-profiles/99999")
        assert resp.status_code == 404

    def test_get_other_user_profile_returns_404(self, profile_client, profile_session):
        """Accessing another user's private profile returns 404."""
        prof = _make_profile(profile_session, owner=_OTHER, name="Private")
        resp = profile_client.get(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 404

    def test_get_unauthenticated(self, anon_client, profile_session):
        """Unauthenticated request returns 401."""
        prof = _make_profile(profile_session, owner=None, is_builtin=True)
        resp = anon_client.get(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – update profile endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUpdateProfile:
    """Tests for PUT /api/imap-profiles/{id}."""

    def test_update_name(self, profile_client, profile_session):
        """Updating the name of an owned profile returns the updated profile."""
        prof = _make_profile(profile_session, owner=_OWNER, name="Old Name")
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_update_categories(self, profile_client, profile_session):
        """Updating allowed_categories replaces the previous value."""
        prof = _make_profile(profile_session, owner=_OWNER, categories_json='["pdf"]')
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"allowed_categories": ["office", "text"]})
        assert resp.status_code == 200
        assert resp.json()["allowed_categories"] == ["office", "text"]

    def test_update_description(self, profile_client, profile_session):
        """Setting description via model_fields_set path updates it."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"description": "Updated desc"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated desc"

    def test_update_builtin_returns_403(self, profile_client, profile_session):
        """Attempting to update a built-in profile returns 403."""
        prof = _make_profile(profile_session, owner=None, is_builtin=True)
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"name": "Renamed"})
        assert resp.status_code == 403

    def test_update_not_found(self, profile_client):
        """Updating a non-existent profile returns 404."""
        resp = profile_client.put("/api/imap-profiles/99999", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_other_user_profile_returns_404(self, profile_client, profile_session):
        """Updating another user's profile returns 404."""
        prof = _make_profile(profile_session, owner=_OTHER)
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"name": "X"})
        assert resp.status_code == 404

    def test_update_invalid_category_returns_422(self, profile_client, profile_session):
        """Updating with an invalid category key returns 422."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = profile_client.put(f"/api/imap-profiles/{prof.id}", json={"allowed_categories": ["badcat"]})
        assert resp.status_code == 422

    def test_update_unauthenticated(self, anon_client, profile_session):
        """Unauthenticated request returns 401."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = anon_client.put(f"/api/imap-profiles/{prof.id}", json={"name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – delete profile endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteProfile:
    """Tests for DELETE /api/imap-profiles/{id}."""

    def test_delete_success(self, profile_client, profile_session):
        """Deleting an owned profile returns 204 and removes the row."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = profile_client.delete(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 204
        # Verify it is gone
        get_resp = profile_client.get(f"/api/imap-profiles/{prof.id}")
        assert get_resp.status_code == 404

    def test_delete_builtin_returns_403(self, profile_client, profile_session):
        """Attempting to delete a built-in profile returns 403."""
        prof = _make_profile(profile_session, owner=None, is_builtin=True)
        resp = profile_client.delete(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 403

    def test_delete_not_found(self, profile_client):
        """Deleting a non-existent profile returns 404."""
        resp = profile_client.delete("/api/imap-profiles/99999")
        assert resp.status_code == 404

    def test_delete_other_user_profile_returns_404(self, profile_client, profile_session):
        """Deleting another user's private profile returns 404."""
        prof = _make_profile(profile_session, owner=_OTHER)
        resp = profile_client.delete(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 404

    def test_delete_unauthenticated(self, anon_client, profile_session):
        """Unauthenticated request returns 401."""
        prof = _make_profile(profile_session, owner=_OWNER)
        resp = anon_client.delete(f"/api/imap-profiles/{prof.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Integration tests – DB error rollback paths
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDbErrorRollback:
    """Tests for exception-handling / rollback paths in create, update, and delete."""

    def _make_failing_client(self, profile_engine, profile_session, *, fail_on: str = "commit"):
        """Return a TestClient whose DB session raises RuntimeError on commit/delete."""
        from app.api.imap_profiles import _get_owner_id
        from app.main import app

        Session = sessionmaker(bind=profile_engine)

        def override_db():
            session = Session()

            def raise_error(*args, **kwargs):
                raise RuntimeError("Simulated DB failure")

            setattr(session, fail_on, raise_error)
            try:
                yield session
            finally:
                session.close()

        def override_owner():
            return _OWNER

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[_get_owner_id] = override_owner
        return TestClient(app, base_url="http://localhost", raise_server_exceptions=False)

    def test_create_db_error_returns_500(self, profile_engine, profile_session):
        """A DB error during create triggers rollback and returns 500."""
        client = self._make_failing_client(profile_engine, profile_session)
        try:
            resp = client.post("/api/imap-profiles/", json={"name": "X", "allowed_categories": ["pdf"]})
        finally:
            from app.main import app

            app.dependency_overrides.clear()
        assert resp.status_code == 500

    def test_update_db_error_returns_500(self, profile_engine, profile_session):
        """A DB error during update triggers rollback and returns 500."""
        prof = _make_profile(profile_session, owner=_OWNER)
        client = self._make_failing_client(profile_engine, profile_session)
        try:
            resp = client.put(f"/api/imap-profiles/{prof.id}", json={"name": "New"})
        finally:
            from app.main import app

            app.dependency_overrides.clear()
        assert resp.status_code == 500

    def test_delete_db_error_returns_500(self, profile_engine, profile_session):
        """A DB error during delete triggers rollback and returns 500."""
        prof = _make_profile(profile_session, owner=_OWNER)
        client = self._make_failing_client(profile_engine, profile_session, fail_on="delete")
        try:
            resp = client.delete(f"/api/imap-profiles/{prof.id}")
        finally:
            from app.main import app

            app.dependency_overrides.clear()
        assert resp.status_code == 500
