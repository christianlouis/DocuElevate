"""Tests for the full-text search API (app/api/search.py) and Meilisearch
client utilities (app/utils/meilisearch_client.py).
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# app/utils/meilisearch_client tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMeilisearchClientDisabled:
    """Tests when search is disabled or Meilisearch is unavailable."""

    def test_get_client_returns_none_when_disabled(self):
        """get_meilisearch_client returns None when enable_search=False."""
        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=None):
            from app.utils.meilisearch_client import index_document, search_documents

            class _FakeRecord:
                id = 1
                original_filename = "test.pdf"
                mime_type = "application/pdf"
                file_size = 1024
                created_at = None

            result = index_document(_FakeRecord(), "some text", {})
            assert result is False

            result = search_documents("invoice")
            assert result["results"] == []
            assert result["total"] == 0

    def test_search_documents_import_error(self):
        """search_documents returns empty dict when meilisearch not installed."""
        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=None):
            from app.utils.meilisearch_client import search_documents

            result = search_documents("test")
            assert result["results"] == []
            assert result["total"] == 0
            assert result["page"] == 1
            assert result["query"] == "test"

    def test_delete_document_no_client(self):
        """delete_document returns False when client unavailable."""
        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=None):
            from app.utils.meilisearch_client import delete_document

            result = delete_document(99)
            assert result is False


@pytest.mark.unit
class TestMeilisearchIndexDocument:
    """Tests for index_document function."""

    def test_index_document_success(self):
        """index_document returns True when Meilisearch succeeds."""
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_task = MagicMock()
        mock_task.task_uid = 1

        mock_client.get_index.return_value = mock_index
        mock_index.add_documents.return_value = mock_task

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import index_document

            class _FakeRecord:
                id = 1
                original_filename = "invoice.pdf"
                mime_type = "application/pdf"
                file_size = 2048
                created_at = None

            result = index_document(
                _FakeRecord(),
                "This is an invoice for services rendered",
                {
                    "title": "Invoice January 2026",
                    "document_type": "Invoice",
                    "tags": ["invoice", "services"],
                    "absender": "ACME Corp",
                    "language": "en",
                },
            )
            assert result is True
            mock_index.add_documents.assert_called_once()
            call_docs = mock_index.add_documents.call_args[0][0]
            assert len(call_docs) == 1
            doc = call_docs[0]
            assert doc["file_id"] == 1
            assert doc["document_title"] == "Invoice January 2026"
            assert "invoice" in doc["tags"]

    def test_index_document_meilisearch_error(self):
        """index_document returns False on Meilisearch exception."""
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        mock_index.add_documents.side_effect = RuntimeError("Meilisearch down")

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import index_document

            class _FakeRecord:
                id = 2
                original_filename = "test.pdf"
                mime_type = "application/pdf"
                file_size = 512
                created_at = None

            result = index_document(_FakeRecord(), "some text", {})
            assert result is False


@pytest.mark.unit
class TestMeilisearchSearchDocuments:
    """Tests for search_documents function."""

    def _make_mock_client(self, hits=None, total=None):
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        mock_index.search.return_value = {
            "hits": hits or [],
            "estimatedTotalHits": total if total is not None else len(hits or []),
        }
        return mock_client, mock_index

    def test_search_returns_results(self):
        """search_documents returns hits from Meilisearch."""
        hits = [
            {
                "file_id": 42,
                "original_filename": "2026-01-15_Invoice_Amazon.pdf",
                "document_title": "Amazon Invoice",
                "document_type": "Invoice",
                "tags": ["amazon", "invoice"],
                "ocr_text": "Amazon invoice content here",
                "_formatted": {
                    "document_title": "Amazon <mark>Invoice</mark>",
                    "ocr_text": "…Amazon <mark>invoice</mark> content here…",
                },
            }
        ]
        mock_client, mock_index = self._make_mock_client(hits=hits, total=1)

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import search_documents

            result = search_documents("invoice", page=1, per_page=20)

        assert result["total"] == 1
        assert result["pages"] == 1
        assert result["query"] == "invoice"
        assert len(result["results"]) == 1
        # Raw ocr_text should be stripped from result (only _formatted snippet kept)
        assert "ocr_text" not in result["results"][0]
        assert result["results"][0]["file_id"] == 42

    def test_search_with_filters(self):
        """search_documents passes filter expressions to Meilisearch."""
        mock_client, mock_index = self._make_mock_client(hits=[], total=0)

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import search_documents

            search_documents("contract", mime_type="application/pdf", language="de", page=1, per_page=10)

        call_kwargs = mock_index.search.call_args
        search_params = call_kwargs[0][1]
        assert "filter" in search_params
        assert 'mime_type = "application/pdf"' in search_params["filter"]
        assert 'language = "de"' in search_params["filter"]

    def test_search_pagination(self):
        """search_documents applies correct offset for page 2."""
        mock_client, mock_index = self._make_mock_client(hits=[], total=50)

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import search_documents

            result = search_documents("test", page=3, per_page=10)

        call_kwargs = mock_index.search.call_args
        search_params = call_kwargs[0][1]
        assert search_params["offset"] == 20  # (3-1) * 10
        assert search_params["limit"] == 10
        assert result["pages"] == 5

    def test_search_empty_results(self):
        """search_documents returns proper empty structure."""
        mock_client, mock_index = self._make_mock_client(hits=[], total=0)

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import search_documents

            result = search_documents("nothing")

        assert result["results"] == []
        assert result["total"] == 0
        assert result["pages"] == 0

    def test_search_exception_returns_empty(self):
        """search_documents returns empty dict on Meilisearch exception."""
        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.side_effect = RuntimeError("Meilisearch unavailable")

        with patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client):
            from app.utils.meilisearch_client import search_documents

            result = search_documents("invoice")

        assert result["results"] == []
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# Search API endpoint tests (GET /api/search)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSearchAPIEndpoint:
    """Tests for GET /api/search endpoint."""

    def test_search_endpoint_success(self, client):
        """GET /api/search?q=... returns search results."""
        mock_result = {
            "results": [{"file_id": 1, "document_title": "Test Invoice", "document_type": "Invoice"}],
            "total": 1,
            "page": 1,
            "pages": 1,
            "query": "invoice",
        }
        with patch("app.api.search.search_documents", return_value=mock_result):
            response = client.get("/api/search?q=invoice")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["query"] == "invoice"
        assert len(data["results"]) == 1

    def test_search_endpoint_missing_query(self, client):
        """GET /api/search without q returns 422."""
        response = client.get("/api/search")
        assert response.status_code == 422

    def test_search_endpoint_empty_query(self, client):
        """GET /api/search?q= (empty) returns 422 due to min_length=1."""
        response = client.get("/api/search?q=")
        assert response.status_code == 422

    def test_search_endpoint_with_filters(self, client):
        """GET /api/search with optional filters passes them to search_documents."""
        mock_result = {"results": [], "total": 0, "page": 1, "pages": 0, "query": "invoice"}
        with patch("app.api.search.search_documents", return_value=mock_result) as mock_search:
            response = client.get("/api/search?q=invoice&mime_type=application/pdf&language=en&page=2&per_page=10")

        assert response.status_code == 200
        mock_search.assert_called_once_with(
            "invoice",
            mime_type="application/pdf",
            document_type=None,
            language="en",
            date_from=None,
            date_to=None,
            page=2,
            per_page=10,
        )

    def test_search_endpoint_per_page_max(self, client):
        """GET /api/search with per_page > 100 returns 422."""
        response = client.get("/api/search?q=test&per_page=200")
        assert response.status_code == 422

    def test_search_endpoint_pagination_defaults(self, client):
        """GET /api/search uses default page=1 per_page=20."""
        mock_result = {"results": [], "total": 0, "page": 1, "pages": 0, "query": "test"}
        with patch("app.api.search.search_documents", return_value=mock_result) as mock_search:
            response = client.get("/api/search?q=test")

        assert response.status_code == 200
        mock_search.assert_called_once_with(
            "test",
            mime_type=None,
            document_type=None,
            language=None,
            date_from=None,
            date_to=None,
            page=1,
            per_page=20,
        )

    def test_search_endpoint_date_filters(self, client):
        """GET /api/search with date_from and date_to passes them as int."""
        mock_result = {"results": [], "total": 0, "page": 1, "pages": 0, "query": "contract"}
        with patch("app.api.search.search_documents", return_value=mock_result) as mock_search:
            response = client.get("/api/search?q=contract&date_from=1704067200&date_to=1735689600")

        assert response.status_code == 200
        call_kwargs = mock_search.call_args
        assert call_kwargs[1]["date_from"] == 1704067200
        assert call_kwargs[1]["date_to"] == 1735689600
