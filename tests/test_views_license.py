"""Tests for app/views/license_routes.py module."""

import pytest


@pytest.mark.integration
class TestLicenseViews:
    """Tests for license view routes."""

    def test_license_api_endpoint(self, client):
        """Test license API endpoint."""
        response = client.get("/api/license")
        assert response.status_code in (200, 404)
