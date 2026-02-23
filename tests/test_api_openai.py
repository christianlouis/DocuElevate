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
        mock_settings.openai_base_url = "https://api.openai.com/v1"

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
    def test_openai_uses_configured_base_url(self, mock_settings, mock_openai_class, client):
        """Test that the client is created with the configured base_url from settings.

        Regression test: previously the endpoint created openai.OpenAI without
        base_url, causing the OpenAI library to read the raw OPENAI_BASE_URL
        env var which may contain literal quote characters (e.g. in Kubernetes).
        Those quotes are URL-encoded by httpx to %22 and produce an
        UnsupportedProtocol error.
        """
        mock_settings.openai_api_key = "sk-test-key"
        mock_settings.openai_base_url = "http://litellm.example.com/v1"

        mock_client = MagicMock()
        mock_models = MagicMock()
        mock_models.data = []
        mock_client.models.list.return_value = mock_models
        mock_openai_class.return_value = mock_client

        client.get("/api/openai/test")

        # The OpenAI client must be constructed with the configured base_url so
        # that Settings' strip_outer_quotes sanitisation takes effect.
        mock_openai_class.assert_called_once_with(
            api_key="sk-test-key",
            base_url="http://litellm.example.com/v1",
        )

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_key_validation_auth_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation with auth error."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-invalid-key"

        mock_client = MagicMock()
        auth_exc = openai_module.AuthenticationError(
            message="Incorrect API key provided",
            response=MagicMock(status_code=401, headers={}),
            body={"error": {"message": "Incorrect API key provided"}},
        )
        mock_client.models.list.side_effect = auth_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("is_auth_error") is True
        assert data.get("error_type") == "authentication_error"

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_key_validation_network_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation with network/connection error."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        conn_exc = openai_module.APIConnectionError(request=MagicMock())
        mock_client.models.list.side_effect = conn_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("is_auth_error") is False
        assert data.get("error_type") == "connection_error"
        assert "connection error" in data["message"].lower()

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_connection_error_with_dns_cause(self, mock_settings, mock_openai_class, client):
        """Test that DNS resolution failures are surfaced in the connection error message."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-test-key"

        dns_err = OSError("[Errno -2] Name or service not known")
        conn_exc = openai_module.APIConnectionError(request=MagicMock())
        conn_exc.__cause__ = dns_err
        mock_client = MagicMock()
        mock_client.models.list.side_effect = conn_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("error_type") == "connection_error"
        # The DNS detail should be propagated to the message
        assert "name or service not known" in data["message"].lower()

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_timeout_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API key validation with timeout error."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        timeout_exc = openai_module.APITimeoutError(request=MagicMock())
        mock_client.models.list.side_effect = timeout_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("is_auth_error") is False
        assert data.get("error_type") == "timeout"
        assert "timed out" in data["message"].lower()

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_status_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API returning an unexpected HTTP status code."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-test-key"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {"x-request-id": "test-req-id"}
        status_exc = openai_module.InternalServerError(
            message="Internal Server Error",
            response=mock_response,
            body={"error": {"message": "Internal Server Error"}},
        )
        mock_client = MagicMock()
        mock_client.models.list.side_effect = status_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("error_type") == "api_status_error"
        assert data.get("http_status") == 500

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_api_rate_limit_error(self, mock_settings, mock_openai_class, client):
        """Test OpenAI API returning a rate-limit error."""
        import openai as openai_module

        mock_settings.openai_api_key = "sk-test-key"

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        rate_exc = openai_module.RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )
        mock_client = MagicMock()
        mock_client.models.list.side_effect = rate_exc
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("error_type") == "rate_limit"
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

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_generic_error_still_detects_auth(self, mock_settings, mock_openai_class, client):
        """Test that generic exception fallback still detects auth-related errors."""
        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Incorrect API key provided")
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("is_auth_error") is True

    @patch("openai.OpenAI")
    @patch("app.api.openai.settings")
    def test_openai_generic_network_error_not_auth(self, mock_settings, mock_openai_class, client):
        """Test that generic network errors are not flagged as auth errors."""
        mock_settings.openai_api_key = "sk-test-key"

        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Network timeout")
        mock_openai_class.return_value = mock_client

        response = client.get("/api/openai/test")
        data = response.json()

        assert data["status"] == "error"
        assert data.get("is_auth_error") is False


@pytest.mark.unit
class TestAiExtractionEndpoint:
    """Tests for POST /api/ai/test-extraction endpoint."""

    @patch("app.api.openai.settings")
    def test_extraction_missing_text_returns_422(self, mock_settings, client):
        """Test that missing text body returns 422 validation error."""
        response = client.post("/api/ai/test-extraction", json={})
        assert response.status_code == 422

    @patch("app.api.openai.settings")
    def test_extraction_empty_text_returns_422(self, mock_settings, client):
        """Test that empty string text returns 422 validation error."""
        response = client.post("/api/ai/test-extraction", json={"text": ""})
        assert response.status_code == 422

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_returns_raw_response_and_parsed_json(self, mock_settings, mock_get_provider, client):
        """Test successful extraction returns raw response, parsed JSON, and tags."""
        import json as json_module

        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        expected_json = {
            "filename": "2024-01-01_Invoice",
            "tags": ["invoice", "payment"],
            "title": "January Invoice",
            "document_type": "Invoice",
        }
        raw = "```json\n" + json_module.dumps(expected_json) + "\n```"

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = raw
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Invoice content here"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["raw_response"] == raw
        assert data["parsed_json"]["filename"] == "2024-01-01_Invoice"
        assert data["tags"] == ["invoice", "payment"]
        assert data["parse_error"] is None
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_handles_invalid_json_in_response(self, mock_settings, mock_get_provider, client):
        """Test that invalid JSON in LLM response is reported via parse_error."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "Sorry, I cannot help with that."
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Some document text"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["parsed_json"] is None
        assert data["tags"] == []
        assert data["parse_error"] is not None

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_provider_config_error(self, mock_settings, mock_get_provider, client):
        """Test that configuration errors (missing keys) are returned as error status."""
        mock_settings.ai_provider = "anthropic"
        mock_settings.ai_model = "claude-3"
        mock_settings.openai_model = "gpt-4o-mini"

        mock_get_provider.side_effect = ValueError("ANTHROPIC_API_KEY must be set")

        response = client.post("/api/ai/test-extraction", json={"text": "Some document text"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert "ANTHROPIC_API_KEY" in data["message"]

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_provider_runtime_error(self, mock_settings, mock_get_provider, client):
        """Test that runtime errors during AI call are returned as error status."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        mock_provider = MagicMock()
        mock_provider.chat_completion.side_effect = Exception("Connection refused")
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Some document text"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert "Connection refused" in data["message"]

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_plain_json_without_code_fences(self, mock_settings, mock_get_provider, client):
        """Test that JSON returned without code fences is still parsed correctly."""
        import json as json_module

        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        expected_json = {"tags": ["contract"], "title": "Service Agreement"}
        raw = json_module.dumps(expected_json)

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = raw
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Contract content"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["tags"] == ["contract"]
        assert data["parse_error"] is None

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_json_found_but_invalid_reports_parse_error(self, mock_settings, mock_get_provider, client):
        """Test JSONDecodeError branch: response contains '{...}' but is not valid JSON."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        # Looks like JSON (has { and }) but is NOT parseable
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "{this is not: valid json!!}"
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Some document text"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["parsed_json"] is None
        assert data["tags"] == []
        assert data["parse_error"] is not None
        assert "raw_response" in data

    @patch("app.api.openai.settings")
    def test_extraction_text_too_long_returns_422(self, mock_settings, client):
        """Test that text exceeding max length returns 422 validation error."""
        from app.api.openai import _MAX_EXTRACTION_TEXT_LEN

        oversized_text = "x" * (_MAX_EXTRACTION_TEXT_LEN + 1)
        response = client.post("/api/ai/test-extraction", json={"text": oversized_text})
        assert response.status_code == 422

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_extraction_response_with_no_tags_key(self, mock_settings, mock_get_provider, client):
        """Test extraction where parsed JSON has no 'tags' key returns empty tags list."""
        import json as json_module

        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        # Valid JSON but no 'tags' key
        payload = {"title": "Report", "document_type": "Report"}
        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = json_module.dumps(payload)
        mock_get_provider.return_value = mock_provider

        response = client.post("/api/ai/test-extraction", json={"text": "Report content"})
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["tags"] == []
        assert data["parsed_json"]["title"] == "Report"
        assert data["parse_error"] is None


@pytest.mark.unit
class TestAiProviderTestEndpoint:
    """Tests for GET /api/ai/test endpoint."""

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_ai_test_success(self, mock_settings, mock_get_provider, client):
        """Test successful AI provider connection."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "ok"
        mock_get_provider.return_value = mock_provider

        response = client.get("/api/ai/test")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "reachable" in data["message"].lower()
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o-mini"
        assert "response_preview" in data

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_ai_test_value_error(self, mock_settings, mock_get_provider, client):
        """Test GET /api/ai/test returns error on provider configuration ValueError."""
        mock_settings.ai_provider = "anthropic"
        mock_settings.ai_model = None
        mock_settings.openai_model = "gpt-4o-mini"

        mock_get_provider.side_effect = ValueError("ANTHROPIC_API_KEY must be set")

        response = client.get("/api/ai/test")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert "ANTHROPIC_API_KEY" in data["message"]
        assert data["provider"] == "anthropic"

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_ai_test_connection_exception(self, mock_settings, mock_get_provider, client):
        """Test GET /api/ai/test returns error on provider runtime exception."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = "gpt-4o-mini"
        mock_settings.openai_model = "gpt-4o-mini"

        mock_provider = MagicMock()
        mock_provider.chat_completion.side_effect = Exception("Connection refused")
        mock_get_provider.return_value = mock_provider

        response = client.get("/api/ai/test")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "error"
        assert "Connection refused" in data["message"]
        assert data["provider"] == "openai"

    @patch("app.utils.ai_provider.get_ai_provider")
    @patch("app.api.openai.settings")
    def test_ai_test_uses_openai_model_fallback(self, mock_settings, mock_get_provider, client):
        """Test that ai_model=None falls back to openai_model."""
        mock_settings.ai_provider = "openai"
        mock_settings.ai_model = None
        mock_settings.openai_model = "gpt-3.5-turbo"

        mock_provider = MagicMock()
        mock_provider.chat_completion.return_value = "ok"
        mock_get_provider.return_value = mock_provider

        response = client.get("/api/ai/test")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert data["model"] == "gpt-3.5-turbo"


@pytest.mark.unit
class TestExceptionChainDetail:
    """Unit tests for the _get_exception_chain_detail helper."""

    def test_single_exception_no_chain(self):
        """Test with a simple exception that has no cause."""
        from app.api.openai import _get_exception_chain_detail

        exc = ValueError("root cause")
        result = _get_exception_chain_detail(exc)
        assert result == "root cause"

    def test_exception_with_cause(self):
        """Test that chained exceptions are surfaced in the message."""
        from app.api.openai import _get_exception_chain_detail

        inner = OSError("DNS resolution failed")
        outer = ConnectionError("Connection failed")
        outer.__cause__ = inner

        result = _get_exception_chain_detail(outer)
        assert "Connection failed" in result
        assert "DNS resolution failed" in result
        assert "caused by" in result

    def test_empty_cause_string_skipped(self):
        """Test that a cause with empty string representation is not appended."""
        from app.api.openai import _get_exception_chain_detail

        inner = Exception("")  # str() returns ""
        outer = RuntimeError("outer error")
        outer.__cause__ = inner

        result = _get_exception_chain_detail(outer)
        # The empty-string cause should be skipped (branch 47->49)
        assert result == "outer error"

    def test_duplicate_cause_string_skipped(self):
        """Test that a cause whose str() is already in parts is not duplicated."""
        from app.api.openai import _get_exception_chain_detail

        outer = RuntimeError("same message")
        inner = RuntimeError("same message")  # same text as outer
        outer.__cause__ = inner

        result = _get_exception_chain_detail(outer)
        # "same message" should appear only once (branch: cause_str already in parts)
        assert result.count("same message") == 1


@pytest.mark.unit
class TestExtractJsonFromText:
    """Unit tests for the _extract_json_from_text helper."""

    def test_json_in_code_fence(self):
        """Test extraction from markdown code fence."""
        from app.api.openai import _extract_json_from_text

        text = '```json\n{"key": "value"}\n```'
        result = _extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_json_in_plain_code_fence(self):
        """Test extraction from plain (non-json) code fence."""
        from app.api.openai import _extract_json_from_text

        text = '```\n{"key": "value"}\n```'
        result = _extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_bare_json_object(self):
        """Test extraction of a bare JSON object without code fence."""
        from app.api.openai import _extract_json_from_text

        text = 'Here is the result: {"title": "Invoice"} done.'
        result = _extract_json_from_text(text)
        assert result == '{"title": "Invoice"}'

    def test_no_json_returns_none(self):
        """Test that text with no JSON object returns None."""
        from app.api.openai import _extract_json_from_text

        result = _extract_json_from_text("No JSON here at all.")
        assert result is None
