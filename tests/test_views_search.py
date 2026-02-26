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
