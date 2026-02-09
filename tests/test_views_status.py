"""Tests for app/views/status.py module."""
import pytest


@pytest.mark.integration
class TestStatusViews:
    """Tests for status view routes."""

    def test_status_dashboard(self, client):
        """Test status dashboard page."""
        response = client.get("/status")
        assert response.status_code == 200

    def test_env_debug_page(self, client):
        """Test env debug page."""
        response = client.get("/env")
        assert response.status_code == 200
