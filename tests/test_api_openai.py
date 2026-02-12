"""Tests for app/api/openai.py module."""

import pytest


@pytest.mark.integration
class TestOpenAIEndpoints:
    """Tests for OpenAI API endpoints."""

    def test_test_openai_connection(self, client):
        """Test the OpenAI connection test endpoint."""
        response = client.get("/api/openai/test")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_openai_test_returns_status(self, client):
        """Test that OpenAI test returns appropriate status."""
        response = client.get("/api/openai/test")
        data = response.json()
        # Should be success or error depending on API key validity
        assert data["status"] in ("success", "error")
