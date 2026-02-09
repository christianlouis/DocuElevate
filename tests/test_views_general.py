"""Tests for app/views/general.py module."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


@pytest.mark.integration
class TestGeneralViews:
    """Tests for general view routes."""

    def test_index_page(self, client):
        """Test the index/home page returns 200 or redirects to setup."""
        response = client.get("/", follow_redirects=False)
        # Should either render or redirect to setup
        assert response.status_code in (200, 303, 307)

    def test_about_page(self, client):
        """Test the about page."""
        response = client.get("/about")
        assert response.status_code == 200

    def test_privacy_page(self, client):
        """Test the privacy page."""
        response = client.get("/privacy")
        assert response.status_code == 200

    def test_imprint_page(self, client):
        """Test the imprint page."""
        response = client.get("/imprint")
        assert response.status_code == 200

    def test_upload_page(self, client):
        """Test the upload page."""
        response = client.get("/upload")
        assert response.status_code == 200

    def test_cookies_page(self, client):
        """Test the cookies page."""
        response = client.get("/cookies")
        assert response.status_code == 200

    def test_terms_page(self, client):
        """Test the terms page."""
        response = client.get("/terms")
        assert response.status_code == 200

    def test_license_page(self, client):
        """Test the license page."""
        response = client.get("/license")
        assert response.status_code == 200

    def test_favicon(self, client):
        """Test the favicon endpoint."""
        response = client.get("/favicon.ico")
        # May be 200 or 404 depending on whether the file exists
        assert response.status_code in (200, 404)

    def test_index_with_setup_complete(self, client):
        """Test index page with setup=complete query param."""
        response = client.get("/?setup=complete", follow_redirects=False)
        assert response.status_code == 200
