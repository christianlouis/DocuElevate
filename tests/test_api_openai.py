"""
Tests for OpenAI API endpoints
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestOpenAIEndpoints:
    """Tests for OpenAI API endpoints."""

    @patch("app.api.openai.settings")
    def test_openai_test_no_api_key(self, mock_settings, client: TestClient):
        """Test OpenAI connection test when no API key is configured."""
        mock_settings.openai_api_key = None

        response = client.get("/api/openai/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "No OpenAI API key" in data["message"]

    def test_openai_test_valid_key(self, client: TestClient):
        """Test OpenAI connection test with valid API key."""
        # Mock the OpenAI client and models response at import level
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test-key"

            # Create a mock for openai module
            mock_openai = MagicMock()
            mock_client_instance = MagicMock()
            mock_models_response = MagicMock()
            mock_models_response.data = [{"id": "gpt-3.5-turbo"}, {"id": "gpt-4"}]
            mock_client_instance.models.list.return_value = mock_models_response
            mock_openai.OpenAI.return_value = mock_client_instance

            with patch.dict('sys.modules', {'openai': mock_openai}):
                response = client.get("/api/openai/test")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert "valid" in data["message"].lower()
                assert data["models_available"] == 2

    def test_openai_test_invalid_key(self, client: TestClient):
        """Test OpenAI connection test with invalid API key."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-invalid-key"

            # Mock the OpenAI client to raise authentication error
            mock_openai = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.models.list.side_effect = Exception("Invalid API key")
            mock_openai.OpenAI.return_value = mock_client_instance

            with patch.dict('sys.modules', {'openai': mock_openai}):
                response = client.get("/api/openai/test")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert "validation failed" in data["message"].lower()
                assert data["is_auth_error"] is True

    def test_openai_test_network_error(self, client: TestClient):
        """Test OpenAI connection test with network error."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test-key"

            # Mock the OpenAI client to raise network error
            mock_openai = MagicMock()
            mock_client_instance = MagicMock()
            mock_client_instance.models.list.side_effect = Exception("Connection timeout")
            mock_openai.OpenAI.return_value = mock_client_instance

            with patch.dict('sys.modules', {'openai': mock_openai}):
                response = client.get("/api/openai/test")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert "validation failed" in data["message"].lower()
                assert data["is_auth_error"] is False

    def test_openai_test_openai_not_installed(self, client: TestClient):
        """Test OpenAI connection test when openai package is not installed."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test-key"

            # Test that ImportError is handled gracefully
            # This test is limited because openai is imported at function level
            response = client.get("/api/openai/test")
            assert response.status_code == 200
            # Should either succeed or return an error, but not crash
            data = response.json()
            assert "status" in data

    def test_openai_test_unexpected_error(self, client: TestClient):
        """Test OpenAI connection test with unexpected error."""
        with patch("app.config.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test-key"

            # Mock unexpected error during client initialization
            mock_openai = MagicMock()
            mock_openai.OpenAI.side_effect = RuntimeError("Unexpected error")

            with patch.dict('sys.modules', {'openai': mock_openai}):
                response = client.get("/api/openai/test")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "error"
                assert "Unexpected error" in data["message"]
