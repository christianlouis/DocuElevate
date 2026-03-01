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

    def test_search_page_text_quality_options(self, client):
        """GET /search contains text quality filter with expected options."""
        response = client.get("/search")
        assert response.status_code == 200
        text = response.text
        assert 'value="high"' in text
        assert 'value="medium"' in text
        assert 'value="low"' in text
        assert 'value="no_text"' in text
