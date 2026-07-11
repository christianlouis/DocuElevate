"""Tests for the dedicated search page view (app/views/search.py)."""

import pytest


@pytest.mark.unit
class TestSearchPage:
    """Tests for GET /search view endpoint."""

    def test_search_page_renders(self, client):
        """GET /search returns 200 with search template."""
        response = client.get("/search")
        assert response.status_code == 200
        assert "Document Search" in response.text

    def test_search_page_with_query(self, client):
        """GET /search?q=invoice pre-fills the search input."""
        response = client.get("/search?q=invoice")
        assert response.status_code == 200
        assert 'value="invoice"' in response.text

    def test_search_page_empty_query(self, client):
        """GET /search?q= renders page without error."""
        response = client.get("/search?q=")
        assert response.status_code == 200
        assert "Document Search" in response.text

    def test_search_page_contains_search_elements(self, client):
        """GET /search contains required search UI elements."""
        response = client.get("/search")
        assert response.status_code == 200
        assert 'id="search-input"' in response.text
        assert 'id="search-btn"' in response.text
        assert 'id="search-results"' in response.text
        assert "/api/search" in response.text

    def test_search_page_query_too_long(self, client):
        """GET /search?q=<very long> returns 422 for exceeding max_length."""
        long_query = "a" * 600
        response = client.get(f"/search?q={long_query}")
        assert response.status_code == 422

    def test_search_page_contains_filter_elements(self, client):
        """GET /search contains content-finding filter UI elements."""
        response = client.get("/search")
        assert response.status_code == 200
        assert 'id="filter-document-type"' in response.text
        assert 'id="filter-tags"' in response.text
        assert 'id="filter-sender"' in response.text
        assert 'id="filter-language"' in response.text
        assert 'id="filter-text-quality"' in response.text
        assert 'id="filter-date-from"' in response.text
        assert 'id="filter-date-to"' in response.text

    def test_search_page_contains_saved_searches(self, client):
        """GET /search contains saved searches UI elements."""
        response = client.get("/search")
        assert response.status_code == 200
        assert 'id="saved-searches-list"' in response.text
        assert 'id="save-search-btn"' in response.text
        assert "/api/saved-searches" in response.text

    def test_search_page_saved_searches_support_pinning_and_deep_links(self, client):
        """Saved searches on /search can be pinned and reopened by URL."""
        response = client.get("/search")
        assert response.status_code == 200
        assert "toggleSavedSearchPin" in response.text
        assert "renameSavedSearch" in response.text
        assert "href=\"/search?' + escapeHtml(params.toString())" in response.text
        assert "fa-star" in response.text

    def test_search_page_contains_preview_first_results_ui(self, client):
        """Search results support inline previews without leaving the page."""
        response = client.get("/search")
        assert response.status_code == 200
        assert 'id="search-preview-panel"' in response.text
        assert 'id="search-preview-body"' in response.text
        assert "openSearchPreview" in response.text
        assert "/api/files/' + encodeURIComponent(fileId) + '/preview?version=processed" in response.text
        assert "closeSearchPreview" in response.text
        assert "search-preview-object" in response.text
        assert "addEventListener('error'" in response.text

    def test_search_page_contains_result_quick_actions(self, client):
        """Search result actions expose open, download, tag, route, and export controls."""
        response = client.get("/search")
        assert response.status_code == 200
        text = response.text
        assert "/download?version=processed" in text
        assert "searchByTag" in text
        assert "searchByDocumentType" in text
        assert "ranking_score" in text
        assert "badge-score" in text
        assert "confidence_score" in text
        assert "badge-confidence" in text
        assert "/pipelines?file_id=" in text
        assert "exportSearchResult" in text

    def test_search_page_contains_bulk_action_toolbar(self, client):
        """Search results can be selected for bulk actions."""
        response = client.get("/search")
        assert response.status_code == 200
        text = response.text
        assert 'id="search-bulk-bar"' in text
        assert "search-result-checkbox" in text
        assert "selectVisibleSearchResults" in text
        assert "clearSearchSelection" in text

    def test_search_page_supports_sortable_deep_links(self, client):
        """Sort choice is represented in the UI and restored from URL parameters."""
        response = client.get("/search?sort_by=created_at&sort_order=asc")
        assert response.status_code == 200
        assert 'id="filter-sort-by"' in response.text
        assert "filters.sort_by" in response.text
        assert "filters.sort_order" in response.text

    def test_search_page_bulk_actions_use_existing_file_apis(self, client):
        """Bulk actions from search call existing file operation endpoints."""
        response = client.get("/search")
        assert response.status_code == 200
        text = response.text
        assert "bulkDownloadSearchResults" in text
        assert "bulkExportSearchResults" in text
        assert "bulkTagSearchResults" in text
        assert "bulkRouteSearchResults" in text
        assert "setBulkActionStatus" in text
        assert 'id="bulk-route-pipeline"' in text
        assert "loadBulkRoutePipelines" in text
        assert "bulkReprocessSearchResults" in text
        assert "bulkDeleteSearchResults" in text
        assert "/api/files/bulk-download" in text
        assert "/api/files/bulk-tag" in text
        assert "/api/pipelines" in text
        assert "/api/files/bulk-assign-pipeline" in text
        assert "/api/files/bulk-reprocess" in text
        assert "/api/files/bulk-delete" in text
        assert "Enter the destination pipeline ID" not in text
        assert "This cannot be undone from search results" in text

    def test_search_page_text_quality_options(self, client):
        """GET /search contains text quality filter with expected options."""
        response = client.get("/search")
        assert response.status_code == 200
        text = response.text
        assert 'value="high"' in text
        assert 'value="medium"' in text
        assert 'value="low"' in text
        assert 'value="no_text"' in text
