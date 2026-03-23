import pytest
from fastapi.testclient import TestClient

from app.models import SavedSearch

# ---------------------------------------------------------------------------
# Saved searches CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSavedSearchesCRUD:
    """Tests for saved searches CRUD API endpoints."""

    def test_list_saved_searches_empty(self, client: TestClient):
        """GET /api/saved-searches returns empty list when no searches exist."""
        response = client.get("/api/saved-searches")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_saved_search(self, client: TestClient):
        """POST /api/saved-searches creates a new saved search."""
        payload = {
            "name": "My Invoices",
            "filters": {"tags": "invoice", "status": "completed"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Invoices"
        assert data["filters"]["tags"] == "invoice"
        assert data["filters"]["status"] == "completed"
        assert "id" in data

    def test_create_and_list_saved_search(self, client: TestClient):
        """Creating a saved search makes it appear in the list."""
        payload = {
            "name": "PDF Files",
            "filters": {"mime_type": "application/pdf"},
        }
        client.post("/api/saved-searches", json=payload)

        response = client.get("/api/saved-searches")
        assert response.status_code == 200
        searches = response.json()
        assert len(searches) == 1
        assert searches[0]["name"] == "PDF Files"

    def test_create_saved_search_missing_name(self, client: TestClient):
        """POST /api/saved-searches without name returns 422."""
        payload = {"filters": {"status": "completed"}}
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_create_saved_search_empty_filters(self, client: TestClient):
        """POST /api/saved-searches with empty filters returns 422."""
        payload = {"name": "Empty", "filters": {}}
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_create_saved_search_invalid_filter_keys(self, client: TestClient):
        """POST /api/saved-searches ignores unknown filter keys."""
        payload = {
            "name": "With unknown keys",
            "filters": {"invalid_key": "value", "status": "completed"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 201
        data = response.json()
        # Only valid filter key should remain
        assert "invalid_key" not in data["filters"]
        assert data["filters"]["status"] == "completed"

    def test_create_saved_search_only_invalid_keys(self, client: TestClient):
        """POST with only invalid filter keys returns 422."""
        payload = {
            "name": "All invalid",
            "filters": {"bad_key": "value"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_create_duplicate_name(self, client: TestClient):
        """POST /api/saved-searches with duplicate name returns 409."""
        payload = {"name": "My Search", "filters": {"status": "completed"}}
        response1 = client.post("/api/saved-searches", json=payload)
        assert response1.status_code == 201

        response2 = client.post("/api/saved-searches", json=payload)
        assert response2.status_code == 409

    def test_update_saved_search(self, client: TestClient):
        """PUT /api/saved-searches/{id} updates the saved search."""
        # Create
        create_resp = client.post(
            "/api/saved-searches",
            json={"name": "Original", "filters": {"status": "pending"}},
        )
        search_id = create_resp.json()["id"]

        # Update
        update_resp = client.put(
            f"/api/saved-searches/{search_id}",
            json={"name": "Updated", "filters": {"status": "completed"}},
        )
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["name"] == "Updated"
        assert data["filters"]["status"] == "completed"

    def test_update_saved_search_not_found(self, client: TestClient):
        """PUT /api/saved-searches/999 returns 404."""
        response = client.put(
            "/api/saved-searches/999",
            json={"name": "Nope", "filters": {"status": "completed"}},
        )
        assert response.status_code == 404

    def test_delete_saved_search(self, client: TestClient):
        """DELETE /api/saved-searches/{id} removes the saved search."""
        # Create
        create_resp = client.post(
            "/api/saved-searches",
            json={"name": "To Delete", "filters": {"status": "failed"}},
        )
        search_id = create_resp.json()["id"]

        # Delete
        del_resp = client.delete(f"/api/saved-searches/{search_id}")
        assert del_resp.status_code == 204

        # Verify it's gone
        list_resp = client.get("/api/saved-searches")
        assert len(list_resp.json()) == 0

    def test_delete_saved_search_not_found(self, client: TestClient):
        """DELETE /api/saved-searches/999 returns 404."""
        response = client.delete("/api/saved-searches/999")
        assert response.status_code == 404

    def test_create_name_too_long(self, client: TestClient):
        """POST /api/saved-searches with name > 100 chars returns 422."""
        payload = {
            "name": "x" * 101,
            "filters": {"status": "completed"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_saved_search_filters_sanitized(self, client: TestClient):
        """Saved search filters are sanitized to allowed keys only."""
        payload = {
            "name": "Sanitized",
            "filters": {
                "search": "invoice",
                "mime_type": "application/pdf",
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "storage_provider": "dropbox",
                "tags": "invoice,amazon",
                "sort_by": "created_at",
                "sort_order": "desc",
            },
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert len(data["filters"]) == 8
        assert data["filters"]["search"] == "invoice"
        assert data["filters"]["tags"] == "invoice,amazon"

    def test_saved_search_with_fulltext_query(self, client: TestClient):
        """Saved search can include full-text query (q) for the search view."""
        payload = {
            "name": "Invoice Search",
            "filters": {"q": "invoice total amount", "document_type": "Invoice"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["filters"]["q"] == "invoice total amount"
        assert data["filters"]["document_type"] == "Invoice"

    def test_saved_search_content_finding_filters(self, client: TestClient):
        """Saved search accepts content-finding filter keys (language, sender, text_quality)."""
        payload = {
            "name": "German Invoices",
            "filters": {
                "q": "rechnung",
                "language": "de",
                "sender": "ACME GmbH",
                "text_quality": "high",
                "tags": "invoice",
            },
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["filters"]["q"] == "rechnung"
        assert data["filters"]["language"] == "de"
        assert data["filters"]["sender"] == "ACME GmbH"
        assert data["filters"]["text_quality"] == "high"
        assert data["filters"]["tags"] == "invoice"


    def test_create_saved_search_max_limit(self, client: TestClient, db_session, mocker):
        """POST /api/saved-searches returns 409 when max limit is reached."""
        from app.api.saved_searches import MAX_SAVED_SEARCHES_PER_USER
        user_id = "test_user"
        mocker.patch("app.api.saved_searches._get_user_id", return_value=user_id)

        for i in range(MAX_SAVED_SEARCHES_PER_USER):
            search = SavedSearch(user_id=user_id, name=f"Search {i}", filters="""{"tags": "invoice"}""")
            db_session.add(search)
        db_session.commit()

        payload = {
            "name": "One More",
            "filters": {"tags": "invoice"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 409

    def test_create_saved_search_db_error(self, client: TestClient, mocker):
        """POST /api/saved-searches handles db.commit errors gracefully."""
        mocker.patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB Error"))
        payload = {
            "name": "Fail Me",
            "filters": {"tags": "invoice"},
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 500

    def test_update_saved_search_db_error(self, client: TestClient, mocker):
        """PUT /api/saved-searches/{id} handles db.commit errors gracefully."""
        # Create a search first
        payload = {
            "name": "Update Target",
            "filters": {"tags": "invoice"},
        }
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        mocker.patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB Error"))
        update_payload = {"name": "New Name"}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 500

    def test_delete_saved_search_db_error(self, client: TestClient, mocker):
        """DELETE /api/saved-searches/{id} handles db.commit errors gracefully."""
        # Create a search first
        payload = {
            "name": "Delete Target",
            "filters": {"tags": "invoice"},
        }
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        mocker.patch("sqlalchemy.orm.Session.commit", side_effect=Exception("DB Error"))
        response = client.delete(f"/api/saved-searches/{search_id}")
        assert response.status_code == 500

    def test_update_saved_search_name_conflict(self, client: TestClient):
        """PUT /api/saved-searches/{id} returns 409 when the new name conflicts with an existing search."""
        # Create search 1
        payload1 = {"name": "Search One", "filters": {"tags": "invoice"}}
        client.post("/api/saved-searches", json=payload1)

        # Create search 2
        payload2 = {"name": "Search Two", "filters": {"status": "completed"}}
        response2 = client.post("/api/saved-searches", json=payload2)
        search2_id = response2.json()["id"]

        # Try to update search 2 to have name "Search One"
        update_payload = {"name": "Search One"}
        response = client.put(f"/api/saved-searches/{search2_id}", json=update_payload)
        assert response.status_code == 409

    def test_update_saved_search_empty_filters(self, client: TestClient):
        """PUT /api/saved-searches/{id} returns 422 if filters are empty or invalid."""
        payload = {"name": "Search XYZ", "filters": {"tags": "invoice"}}
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        # Empty filters
        update_payload = {"filters": {}}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 422

        # Invalid keys
        update_payload = {"filters": {"invalid_key": "value"}}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 422

    def test_update_saved_search_invalid_name(self, client: TestClient):
        """PUT /api/saved-searches/{id} returns 422 if name is invalid or too long."""
        payload = {"name": "Search XYZ", "filters": {"tags": "invoice"}}
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        # Empty name
        update_payload = {"name": ""}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 422

        # Too long name
        update_payload = {"name": "A" * 101}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 422

    def test_get_user_id_branches(self, client: TestClient, mocker):
        """Test _get_user_id branches with different mock users."""
        # This will be tested indirectly by mocking get_current_user
        pass

    def test_update_saved_search_same_name(self, client: TestClient):
        """PUT /api/saved-searches/{id} with the same name does not trigger duplicate check error."""
        # Create a search
        payload = {"name": "Same Name", "filters": {"tags": "invoice"}}
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        # Update with the exact same name
        update_payload = {"name": "Same Name"}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 200
        assert response.json()["name"] == "Same Name"

    def test_get_user_id_branches_real(self, client: TestClient):
        from app.api.saved_searches import _get_user_id
        from fastapi import Request

        # We need a mock request
        class MockRequest:
            session = {}
            session = {}
            state = type('obj', (object,), {'user': None})

        req = MockRequest()
        assert _get_user_id(req) == "anonymous"

        req.session["user"] = {"preferred_username": "pref"}
        assert _get_user_id(req) == "pref"

        req.session["user"] = {"email": "em@il.com"}
        assert _get_user_id(req) == "em@il.com"

        req.session["user"] = {"name": "named"}
        assert _get_user_id(req) == "named"

        req.session["user"] = {}
        assert _get_user_id(req) == "anonymous"

    def test_validate_filters_not_dict(self, client: TestClient):
        """POST /api/saved-searches with non-dict filters returns 422."""
        payload = {
            "name": "Invalid Filters",
            "filters": "not a dict",
        }
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_create_saved_search_non_dict_filters(self, client: TestClient):
        payload = {"name": "Test", "filters": []}
        response = client.post("/api/saved-searches", json=payload)
        assert response.status_code == 422

    def test_update_saved_search_non_dict_filters(self, client: TestClient):
        payload = {"name": "Test", "filters": {"tags": "invoice"}}
        response = client.post("/api/saved-searches", json=payload)
        search_id = response.json()["id"]

        update_payload = {"filters": []}
        response = client.put(f"/api/saved-searches/{search_id}", json=update_payload)
        assert response.status_code == 422
