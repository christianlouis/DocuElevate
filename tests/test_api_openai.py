"""Tests for app/api/openai.py module."""

from unittest.mock import MagicMock, patch

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


@pytest.mark.unit
class TestOpenAIConnectionErrors:
    """Test error handling in OpenAI connection test."""

    @patch("app.api.openai.settings")
    def test_openai_no_api_key_configured(self, mock_settings, client):
        """Test OpenAI test endpoint when no API key is configured."""
        mock_settings.openai_api_key = None

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert "openai" in data["message"].lower() and "configured" in data["message"].lower()

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_key_validation_success(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation success."""
        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        mock_models = MagicMock()
        mock_models.data = [{"id": "gpt-4"}, {"id": "gpt-3.5-turbo"}]
        mock_client.models.list.return_value = mock_models
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "success"
        assert "valid" in data["message"].lower()
        assert data["models_available"] == 2

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_key_validation_auth_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation with auth error."""
        mock_settings.openai_api_key = "sk-invalid-key"

        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Incorrect API key")
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert "api key" in data["message"].lower() or "validation failed" in data["message"].lower()
        assert data.get("is_auth_error") is True

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_key_validation_network_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation with network error."""
        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Network timeout")
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        # Not an auth error, so is_auth_error should be False
        assert data.get("is_auth_error") is False

    @patch("app.api.openai.settings")
    def test_openai_import_error(self, mock_settings, client):
        """Test handling when openai package is not installed."""
        mock_settings.openai_api_key = "sk-test-key"

        # Mock ImportError by patching the import at module level
        with patch.dict("sys.modules", {"openai": None}):
            response = client.get("/api/openai/test")
            # The endpoint should still respond, even if openai is missing
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "openai package" in data["message"].lower() or "not installed" in data["message"].lower()

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_models_without_data_attribute(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API when models response doesn't have data attribute."""
        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        mock_models = MagicMock(spec=[])  # No data attribute
        del mock_models.data  # Ensure data attribute doesn't exist
        mock_client.models.list.return_value = mock_models
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "success"
        assert data["models_available"] == "Unknown"

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_unexpected_exception(self, mock_settings, mock_openai_class, client):
        """Test handling of unexpected exceptions."""
        mock_settings.openai_api_key = "sk-test-key"

        # Raise an unexpected exception during OpenAI client creation
        mock_openai_class.side_effect = RuntimeError("Unexpected error")

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert "unexpected error" in data["message"].lower()
