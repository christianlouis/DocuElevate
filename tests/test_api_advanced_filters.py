"""Tests for advanced filtering on GET /api/files and saved searches CRUD API.

Tests cover:
- Date range filtering (date_from, date_to)
- Storage provider filtering
- Tags filtering (AND logic)
- Combined filters
- Saved searches CRUD (create, list, update, delete)
- Saved searches validation and error handling
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.models import FileProcessingStep, FileRecord

# ---------------------------------------------------------------------------
# Advanced filtering tests for GET /api/files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilesAdvancedFiltering:
    """Tests for advanced filtering on the files list endpoint."""

    def _create_file(self, db_session, **kwargs):
        """Helper to create a FileRecord in the test database."""
        defaults = {
            "filehash": "abc123",
            "original_filename": "test.pdf",
            "local_filename": "/tmp/test.pdf",
            "file_size": 1024,
            "mime_type": "application/pdf",
        }
        defaults.update(kwargs)
        record = FileRecord(**defaults)
        db_session.add(record)
        db_session.commit()
        db_session.refresh(record)
        return record

    def test_filter_by_date_from(self, client: TestClient, db_session):
        """Test filtering files created after a specific date."""
        self._create_file(db_session, original_filename="old.pdf")
        response = client.get("/api/files?date_from=2020-01-01")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data

    def test_filter_by_date_to(self, client: TestClient, db_session):
        """Test filtering files created before a specific date."""
        self._create_file(db_session, original_filename="recent.pdf")
        response = client.get("/api/files?date_to=2099-12-31")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1

    def test_filter_by_date_range(self, client: TestClient, db_session):
        """Test filtering files within a date range."""
        self._create_file(db_session, original_filename="in_range.pdf")
        response = client.get("/api/files?date_from=2020-01-01&date_to=2099-12-31")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1

    def test_filter_invalid_date_from(self, client: TestClient):
        """Test that invalid date_from returns 422."""
        response = client.get("/api/files?date_from=not-a-date")
        assert response.status_code == 422

    def test_filter_invalid_date_to(self, client: TestClient):
        """Test that invalid date_to returns 422."""
        response = client.get("/api/files?date_to=not-a-date")
        assert response.status_code == 422

    def test_filter_by_storage_provider(self, client: TestClient, db_session):
        """Test filtering files by storage provider."""
        file1 = self._create_file(db_session, original_filename="dropbox_file.pdf")
        file2 = self._create_file(db_session, original_filename="other_file.pdf", filehash="def456")

        # Add successful upload step for file1
        step = FileProcessingStep(
            file_id=file1.id,
            step_name="upload_to_dropbox",
            status="success",
        )
        db_session.add(step)
        db_session.commit()

        response = client.get("/api/files?storage_provider=dropbox")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "dropbox_file.pdf"

    def test_filter_by_storage_provider_no_results(self, client: TestClient, db_session):
        """Test storage provider filter with no matching files."""
        self._create_file(db_session)
        response = client.get("/api/files?storage_provider=s3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 0

    def test_filter_by_tags(self, client: TestClient, db_session):
        """Test filtering files by tags in AI metadata."""
        self._create_file(
            db_session,
            original_filename="invoice.pdf",
            ai_metadata=json.dumps({"tags": ["invoice", "amazon"]}),
        )
        self._create_file(
            db_session,
            original_filename="receipt.pdf",
            filehash="def456",
            ai_metadata=json.dumps({"tags": ["receipt", "walmart"]}),
        )

        response = client.get("/api/files?tags=invoice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "invoice.pdf"

    def test_filter_by_multiple_tags_and_logic(self, client: TestClient, db_session):
        """Test filtering with multiple tags using AND logic."""
        self._create_file(
            db_session,
            original_filename="both_tags.pdf",
            ai_metadata=json.dumps({"tags": ["invoice", "amazon"]}),
        )
        self._create_file(
            db_session,
            original_filename="one_tag.pdf",
            filehash="def456",
            ai_metadata=json.dumps({"tags": ["invoice", "walmart"]}),
        )

        response = client.get("/api/files?tags=invoice,amazon")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "both_tags.pdf"

    def test_combined_filters(self, client: TestClient, db_session):
        """Test combining multiple filters together (AND logic)."""
        self._create_file(
            db_session,
            original_filename="target.pdf",
            mime_type="application/pdf",
            ai_metadata=json.dumps({"tags": ["invoice"]}),
        )
        self._create_file(
            db_session,
            original_filename="other.jpg",
            filehash="def456",
            mime_type="image/jpeg",
            ai_metadata=json.dumps({"tags": ["photo"]}),
        )

        response = client.get("/api/files?mime_type=application/pdf&tags=invoice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "target.pdf"

    def test_filter_with_date_and_search(self, client: TestClient, db_session):
        """Test combining date filter with filename search."""
        self._create_file(db_session, original_filename="invoice_2026.pdf")

        response = client.get("/api/files?search=invoice&date_from=2020-01-01")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1

    def test_empty_tags_ignored(self, client: TestClient, db_session):
        """Test that empty tags parameter is ignored."""
        self._create_file(db_session)
        response = client.get("/api/files?tags=")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1


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
