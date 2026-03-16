"""Tests for the saved searches API (app/api/saved_searches.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import SavedSearch

# ---------------------------------------------------------------------------
# Test data constants
# ---------------------------------------------------------------------------

_OWNER = "test_user@example.com"
_OTHER_OWNER = "other_user@example.com"


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def int_engine():
    """In-memory SQLite engine for integration tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def int_session(int_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=int_engine)
    session = Session()
    yield session
    session.close()


def _make_client(int_engine, owner_id: str = _OWNER):
    """Return a TestClient with *owner_id* injected as the authenticated user."""
    from app.main import app
    from unittest.mock import patch

    def override_db():
        Session = sessionmaker(bind=int_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with patch("app.api.saved_searches._get_user_id", return_value=owner_id):
        with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
            yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def int_client(int_engine):
    """TestClient authenticated as _OWNER."""
    yield from _make_client(int_engine, _OWNER)


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSavedSearchesAPI:
    """Tests for Saved Searches endpoints."""

    def test_list_saved_searches_empty(self, int_client):
        """No saved searches returns empty list."""
        resp = int_client.get("/api/saved-searches")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_saved_search(self, int_client):
        """Create a saved search and verify the response."""
        payload = {
            "name": "My Invoices",
            "filters": {
                "tags": "invoice",
                "document_type": "Invoice"
            }
        }
        resp = int_client.post("/api/saved-searches", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Invoices"
        assert data["filters"] == {"tags": "invoice", "document_type": "Invoice"}
        assert "id" in data

    def test_create_saved_search_invalid_filters(self, int_client):
        """Creating with invalid filters returns 422."""
        # Missing filters parameter (or empty after sanitization)
        payload = {
            "name": "My Invoices",
            "filters": {}
        }
        resp = int_client.post("/api/saved-searches", json=payload)
        assert resp.status_code == 422

        # Invalid filters format
        payload2 = {
            "name": "My Invoices",
            "filters": "not_a_dict"
        }
        resp2 = int_client.post("/api/saved-searches", json=payload2)
        assert resp2.status_code == 422

    def test_create_saved_search_duplicate(self, int_client):
        """Creating a duplicate named search returns 409."""
        payload = {
            "name": "Duplicate",
            "filters": {"q": "test"}
        }
        int_client.post("/api/saved-searches", json=payload)
        resp = int_client.post("/api/saved-searches", json=payload)
        assert resp.status_code == 409

    def test_create_saved_search_limit(self, int_client, int_session):
        """Exceeding MAX_SAVED_SEARCHES_PER_USER returns 409."""
        # Create 50 searches using the API to ensure they are visible
        for i in range(50):
            resp = int_client.post("/api/saved-searches", json={"name": f"Search LIMIT {i}", "filters": {"q": "test"}})
            assert resp.status_code == 201

        payload = {
            "name": "One too many",
            "filters": {"q": "test"}
        }
        resp = int_client.post("/api/saved-searches", json=payload)
        assert resp.status_code == 409

    def test_update_saved_search(self, int_client):
        """Update an existing saved search."""
        payload = {
            "name": "Original Name",
            "filters": {"q": "test"}
        }
        created = int_client.post("/api/saved-searches", json=payload).json()
        search_id = created["id"]

        update_payload = {
            "name": "Updated Name",
            "filters": {"tags": "new"}
        }
        resp = int_client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated Name"
        assert data["filters"] == {"tags": "new"}

    def test_update_saved_search_not_found(self, int_client):
        """Updating a non-existent search returns 404."""
        update_payload = {
            "name": "Updated Name"
        }
        resp = int_client.put("/api/saved-searches/999", json=update_payload)
        assert resp.status_code == 404

    def test_update_saved_search_duplicate_name(self, int_client):
        """Updating name to an existing search name returns 409."""
        payload1 = {"name": "Search 1", "filters": {"q": "a"}}
        payload2 = {"name": "Search 2", "filters": {"q": "b"}}
        int_client.post("/api/saved-searches", json=payload1)
        created2 = int_client.post("/api/saved-searches", json=payload2).json()
        search2_id = created2["id"]

        update_payload = {"name": "Search 1"}
        resp = int_client.put(f"/api/saved-searches/{search2_id}", json=update_payload)
        assert resp.status_code == 409

    def test_delete_saved_search(self, int_client, int_session):
        """Delete an existing search."""
        payload = {
            "name": "To be deleted",
            "filters": {"q": "test"}
        }
        created = int_client.post("/api/saved-searches", json=payload).json()
        search_id = created["id"]

        resp = int_client.delete(f"/api/saved-searches/{search_id}")
        assert resp.status_code == 204

        assert int_session.query(SavedSearch).filter(SavedSearch.id == search_id).first() is None

    def test_delete_saved_search_not_found(self, int_client):
        """Deleting a non-existent search returns 404."""
        resp = int_client.delete("/api/saved-searches/999")
        assert resp.status_code == 404

    def test_other_users_searches_isolated(self, int_engine, int_session):
        """Users only see and can only modify their own saved searches."""
        int_session.add(SavedSearch(user_id=_OTHER_OWNER, name="Other Search", filters='{"q": "test"}'))
        int_session.commit()

        client = next(_make_client(int_engine, _OWNER))
        resp = client.get("/api/saved-searches")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

        other_search = int_session.query(SavedSearch).first()
        resp = client.put(f"/api/saved-searches/{other_search.id}", json={"name": "Hacked"})
        assert resp.status_code == 404

        resp = client.delete(f"/api/saved-searches/{other_search.id}")
        assert resp.status_code == 404
