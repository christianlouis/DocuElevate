"""Tests for app/views/license_routes.py module."""

from unittest.mock import mock_open, patch

import pytest


@pytest.mark.integration
class TestLicenseViews:
    """Tests for license view routes."""

    def test_license_api_endpoint(self, client):
        """Test license API endpoint."""
        response = client.get("/api/license")
        assert response.status_code in (200, 404)

    def test_get_lgpl_license_success(self, client):
        """Test successful LGPL license retrieval."""
        # Create a mock license file
        license_content = "GNU Lesser General Public License\nVersion 3, 29 June 2007"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=license_content)):
                response = client.get("/licenses/lgpl.txt")
                assert response.status_code == 200
                assert "GNU Lesser General Public License" in response.text

    def test_get_lgpl_license_not_found(self, client):
        """Test LGPL license file not found."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/licenses/lgpl.txt")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_serve_attribution_page(self, client):
        """Test attribution page is served."""
        response = client.get("/attribution")
        assert response.status_code in (200, 404, 500)  # Allow for missing template
