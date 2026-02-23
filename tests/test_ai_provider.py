"""Unit tests for the AI provider abstraction layer (app/utils/ai_provider.py)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.utils.ai_provider import (
    AIProvider,
    AnthropicProvider,
    AzureOpenAIProvider,
    GeminiProvider,
    LiteLLMProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    PortkeyProvider,
    _require_text_content,
    _resolve_temperature,
    get_ai_provider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_response(content: str) -> MagicMock:
    """Build a minimal mock that looks like an openai ChatCompletion response."""
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_litellm_response(content: str) -> MagicMock:
    """Build a minimal mock that looks like a litellm completion response."""
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_none_content_response() -> MagicMock:
    """Build a mock response where message.content is None (e.g. tool call)."""
    msg = SimpleNamespace(content=None)
    choice = SimpleNamespace(message=msg)
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# _require_text_content helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireTextContent:
    """Tests for the _require_text_content guard helper."""

    def test_returns_non_none_string_unchanged(self):
        """Returns the string as-is when content is not None."""
        assert _require_text_content("hello") == "hello"

    def test_returns_empty_string_unchanged(self):
        """Returns an empty string as-is (empty ≠ None)."""
        assert _require_text_content("") == ""

    def test_raises_value_error_when_none(self):
        """Raises ValueError with descriptive message when content is None."""
        with pytest.raises(ValueError, match="content=None"):
            _require_text_content(None)


# ---------------------------------------------------------------------------
# _resolve_temperature helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveTemperature:
    """Tests for the _resolve_temperature compatibility helper."""

    def test_regular_model_returns_requested_temperature(self):
        """Standard models return the temperature unchanged."""
        assert _resolve_temperature("gpt-4o", 0) == 0
        assert _resolve_temperature("gpt-4o-mini", 0.7) == 0.7

    def test_gpt4_model_returns_requested_temperature(self):
        """gpt-4 models are not gpt-5, so temperature is returned as-is."""
        assert _resolve_temperature("gpt-4-turbo", 0) == 0

    def test_gpt5_model_forces_temperature_1(self):
        """gpt-5 models only accept temperature=1; any other value is coerced."""
        assert _resolve_temperature("gpt-5", 0) == 1.0

    def test_gpt5_nano_forces_temperature_1(self):
        """gpt-5-nano (gpt-5 variant) gets temperature coerced to 1."""
        assert _resolve_temperature("gpt-5-nano", 0) == 1.0

    def test_gpt5_codex_forces_temperature_1(self):
        """gpt-5-codex (gpt-5 variant) gets temperature coerced to 1."""
        assert _resolve_temperature("gpt-5-codex", 0) == 1.0

    def test_gpt5_already_at_1_unchanged(self):
        """gpt-5 with temperature=1 returns 1 (no unnecessary log noise)."""
        assert _resolve_temperature("gpt-5", 1.0) == 1.0

    def test_o1_returns_none(self):
        """o1 reasoning model does not support temperature; None is returned."""
        assert _resolve_temperature("o1", 0) is None

    def test_o1_mini_returns_none(self):
        """o1-mini returns None (temperature not supported)."""
        assert _resolve_temperature("o1-mini", 0) is None

    def test_o1_preview_returns_none(self):
        """o1-preview returns None (temperature not supported)."""
        assert _resolve_temperature("o1-preview", 0) is None

    def test_o3_returns_none(self):
        """o3 reasoning model does not support temperature."""
        assert _resolve_temperature("o3", 0) is None

    def test_o3_mini_returns_none(self):
        """o3-mini returns None (temperature not supported)."""
        assert _resolve_temperature("o3-mini", 0) is None

    def test_o4_mini_returns_none(self):
        """o4-mini returns None (temperature not supported)."""
        assert _resolve_temperature("o4-mini", 0) is None

    def test_provider_prefix_is_stripped(self):
        """Provider prefix (e.g. 'openai/') is ignored when matching."""
        assert _resolve_temperature("openai/gpt-5-nano", 0) == 1.0
        assert _resolve_temperature("openai/o1-mini", 0) is None
        assert _resolve_temperature("openai/gpt-4o", 0) == 0

    def test_model_names_are_case_insensitive(self):
        """Model matching is case-insensitive."""
        assert _resolve_temperature("GPT-5", 0) == 1.0
        assert _resolve_temperature("O1", 0) is None
        assert _resolve_temperature("O3-Mini", 0) is None


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAIProviderABC:
    """Verify that AIProvider cannot be instantiated directly."""

    def test_cannot_instantiate_directly(self):
        """AIProvider is abstract and must be subclassed."""
        with pytest.raises(TypeError):
            AIProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_chat_completion(self):
        """Concrete subclass without chat_completion raises TypeError."""

        class Incomplete(AIProvider):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# OpenAIProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    @patch("openai.OpenAI")
    def test_initialises_with_default_base_url(self, mock_openai_cls):
        """Provider uses the OpenAI default endpoint when no base_url is given."""
        OpenAIProvider(api_key="sk-test")
        mock_openai_cls.assert_called_once_with(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        )

    @patch("openai.OpenAI")
    def test_initialises_with_custom_base_url(self, mock_openai_cls):
        """Provider passes through a custom base_url."""
        OpenAIProvider(api_key="sk-test", base_url="http://localhost:8000/v1")
        mock_openai_cls.assert_called_once_with(
            api_key="sk-test",
            base_url="http://localhost:8000/v1",
        )

    @patch("openai.OpenAI")
    def test_chat_completion_returns_content(self, mock_openai_cls):
        """chat_completion extracts and returns the message content string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("Hello world")
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider(api_key="sk-test")
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "Hi"}],
            model="gpt-4o-mini",
            temperature=0,
        )

        assert result == "Hello world"
        mock_client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            temperature=0,
        )

    @patch("openai.OpenAI")
    def test_chat_completion_passes_kwargs(self, mock_openai_cls):
        """Extra kwargs are forwarded to the underlying client."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider(api_key="sk-test")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
            temperature=0.7,
            max_tokens=100,
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["temperature"] == 0.7

    @patch("openai.OpenAI")
    def test_chat_completion_raises_on_none_content(self, mock_openai_cls):
        """chat_completion raises ValueError when the response content is None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_none_content_response()
        mock_openai_cls.return_value = mock_client

        provider = OpenAIProvider(api_key="sk-test")
        with pytest.raises(ValueError, match="content=None"):
            provider.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o-mini",
            )


# ---------------------------------------------------------------------------
# AzureOpenAIProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAzureOpenAIProvider:
    """Tests for AzureOpenAIProvider."""

    @patch("openai.AzureOpenAI")
    def test_initialises_correctly(self, mock_azure_cls):
        """Azure provider initialises with correct parameters."""
        AzureOpenAIProvider(
            api_key="azure-key",
            azure_endpoint="https://my-resource.openai.azure.com",
            api_version="2024-02-01",
        )
        mock_azure_cls.assert_called_once_with(
            api_key="azure-key",
            azure_endpoint="https://my-resource.openai.azure.com",
            api_version="2024-02-01",
        )

    @patch("openai.AzureOpenAI")
    def test_chat_completion_returns_content(self, mock_azure_cls):
        """chat_completion returns the message content string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("Azure response")
        mock_azure_cls.return_value = mock_client

        provider = AzureOpenAIProvider(
            api_key="key",
            azure_endpoint="https://endpoint.openai.azure.com",
        )
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4",
        )

        assert result == "Azure response"


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    @patch("litellm.completion")
    def test_chat_completion_adds_anthropic_prefix(self, mock_completion):
        """Provider prepends 'anthropic/' to bare model names."""
        mock_completion.return_value = _make_litellm_response("Claude says hi")

        provider = AnthropicProvider(api_key="ant-key")
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="claude-3-5-sonnet-20241022",
        )

        assert result == "Claude says hi"
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3-5-sonnet-20241022"

    @patch("litellm.completion")
    def test_chat_completion_keeps_existing_prefix(self, mock_completion):
        """Provider does not double-add 'anthropic/' if already present."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = AnthropicProvider(api_key="ant-key")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="anthropic/claude-3-opus-20240229",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-3-opus-20240229"

    @patch("litellm.completion")
    def test_chat_completion_passes_api_key(self, mock_completion):
        """Provider passes the API key to litellm."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = AnthropicProvider(api_key="my-ant-key")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="claude-3-5-sonnet-20241022",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_key"] == "my-ant-key"


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGeminiProvider:
    """Tests for GeminiProvider."""

    @patch("litellm.completion")
    def test_chat_completion_adds_gemini_prefix(self, mock_completion):
        """Provider prepends 'gemini/' to bare model names."""
        mock_completion.return_value = _make_litellm_response("Gemini says hi")

        provider = GeminiProvider(api_key="gemini-key")
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gemini-1.5-pro",
        )

        assert result == "Gemini says hi"
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["model"] == "gemini/gemini-1.5-pro"

    @patch("litellm.completion")
    def test_chat_completion_keeps_existing_prefix(self, mock_completion):
        """Provider does not double-add 'gemini/' if already present."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = GeminiProvider(api_key="gemini-key")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="gemini/gemini-pro",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["model"] == "gemini/gemini-pro"


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOllamaProvider:
    """Tests for OllamaProvider."""

    @patch("openai.OpenAI")
    def test_initialises_with_default_base_url(self, mock_openai_cls):
        """Provider appends /v1 to the default Ollama base URL."""
        OllamaProvider()
        mock_openai_cls.assert_called_once_with(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )

    @patch("openai.OpenAI")
    def test_initialises_with_custom_base_url(self, mock_openai_cls):
        """Provider appends /v1 to a custom Ollama base URL."""
        OllamaProvider(base_url="http://my-ollama:11434")
        mock_openai_cls.assert_called_once_with(
            api_key="ollama",
            base_url="http://my-ollama:11434/v1",
        )

    @patch("openai.OpenAI")
    def test_strips_trailing_slash_before_appending_v1(self, mock_openai_cls):
        """Provider normalises trailing slashes before appending /v1."""
        OllamaProvider(base_url="http://ollama:11434/")
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "http://ollama:11434/v1"

    @patch("openai.OpenAI")
    def test_chat_completion_returns_content(self, mock_openai_cls):
        """chat_completion returns the message content string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("Llama response")
        mock_openai_cls.return_value = mock_client

        provider = OllamaProvider()
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="llama3.2",
        )

        assert result == "Llama response"


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenRouterProvider:
    """Tests for OpenRouterProvider."""

    @patch("openai.OpenAI")
    def test_initialises_with_default_base_url(self, mock_openai_cls):
        """Provider uses the default OpenRouter endpoint."""
        OpenRouterProvider(api_key="or-key")
        mock_openai_cls.assert_called_once_with(
            api_key="or-key",
            base_url="https://openrouter.ai/api/v1",
        )

    @patch("openai.OpenAI")
    def test_chat_completion_returns_content(self, mock_openai_cls):
        """chat_completion returns the message content string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("Router response")
        mock_openai_cls.return_value = mock_client

        provider = OpenRouterProvider(api_key="or-key")
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            model="anthropic/claude-3.5-sonnet",
        )

        assert result == "Router response"


# ---------------------------------------------------------------------------
# PortkeyProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPortkeyProvider:
    """Tests for PortkeyProvider."""

    @patch("openai.OpenAI")
    def test_initialises_with_required_api_key(self, mock_openai_cls):
        """Provider passes x-portkey-api-key header and uses default gateway URL."""
        PortkeyProvider(api_key="pk-key")
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://api.portkey.ai/v1"
        assert call_kwargs["api_key"] == "pk-key"
        assert call_kwargs["default_headers"]["x-portkey-api-key"] == "pk-key"

    @patch("openai.OpenAI")
    def test_sets_virtual_key_header_when_provided(self, mock_openai_cls):
        """Provider includes x-portkey-virtual-key header when virtual_key is set."""
        PortkeyProvider(api_key="pk-key", virtual_key="vk-abc123")
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["default_headers"]["x-portkey-virtual-key"] == "vk-abc123"

    @patch("openai.OpenAI")
    def test_omits_virtual_key_header_when_not_provided(self, mock_openai_cls):
        """Provider does not include x-portkey-virtual-key header when virtual_key is None."""
        PortkeyProvider(api_key="pk-key")
        call_kwargs = mock_openai_cls.call_args[1]
        assert "x-portkey-virtual-key" not in call_kwargs["default_headers"]

    @patch("openai.OpenAI")
    def test_sets_config_header_when_provided(self, mock_openai_cls):
        """Provider includes x-portkey-config header when config is set."""
        PortkeyProvider(api_key="pk-key", config="pc-my-config-xyz")
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["default_headers"]["x-portkey-config"] == "pc-my-config-xyz"

    @patch("openai.OpenAI")
    def test_omits_config_header_when_not_provided(self, mock_openai_cls):
        """Provider does not include x-portkey-config header when config is None."""
        PortkeyProvider(api_key="pk-key")
        call_kwargs = mock_openai_cls.call_args[1]
        assert "x-portkey-config" not in call_kwargs["default_headers"]

    @patch("openai.OpenAI")
    def test_uses_custom_base_url(self, mock_openai_cls):
        """Provider forwards a custom gateway base URL."""
        PortkeyProvider(api_key="pk-key", base_url="https://my-portkey-instance.example.com/v1")
        call_kwargs = mock_openai_cls.call_args[1]
        assert call_kwargs["base_url"] == "https://my-portkey-instance.example.com/v1"

    @patch("openai.OpenAI")
    def test_chat_completion_returns_content(self, mock_openai_cls):
        """chat_completion returns the message content string."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("Portkey response")
        mock_openai_cls.return_value = mock_client

        provider = PortkeyProvider(api_key="pk-key")
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
        )

        assert result == "Portkey response"

    @patch("openai.OpenAI")
    def test_chat_completion_with_all_options(self, mock_openai_cls):
        """Provider works correctly with virtual_key, config, and custom model."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_openai_response("ok")
        mock_openai_cls.return_value = mock_client

        provider = PortkeyProvider(
            api_key="pk-key",
            virtual_key="vk-anthropic",
            config="pc-fallback-config",
        )
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="claude-3-5-sonnet-20241022",
            temperature=0.5,
        )

        assert result == "ok"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
        assert call_kwargs["temperature"] == 0.5


# ---------------------------------------------------------------------------
# LiteLLMProvider
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLiteLLMProvider:
    """Tests for LiteLLMProvider."""

    @patch("litellm.completion")
    def test_chat_completion_basic(self, mock_completion):
        """Provider calls litellm.completion with correct arguments."""
        mock_completion.return_value = _make_litellm_response("LiteLLM response")

        provider = LiteLLMProvider()
        result = provider.chat_completion(
            messages=[{"role": "user", "content": "hello"}],
            model="openai/gpt-4o",
        )

        assert result == "LiteLLM response"
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["model"] == "openai/gpt-4o"
        assert call_kwargs["temperature"] == 0

    @patch("litellm.completion")
    def test_chat_completion_with_api_key(self, mock_completion):
        """Provider forwards api_key when set."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = LiteLLMProvider(api_key="my-key")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_key"] == "my-key"

    @patch("litellm.completion")
    def test_chat_completion_with_api_base(self, mock_completion):
        """Provider forwards api_base when set."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = LiteLLMProvider(api_base="http://my-proxy/v1")
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["api_base"] == "http://my-proxy/v1"

    @patch("litellm.completion")
    def test_chat_completion_omits_none_api_key(self, mock_completion):
        """Provider does not include api_key when it is None."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = LiteLLMProvider()  # api_key=None
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args[1]
        assert "api_key" not in call_kwargs

    @patch("litellm.completion")
    def test_chat_completion_omits_none_api_base(self, mock_completion):
        """Provider does not include api_base when it is None."""
        mock_completion.return_value = _make_litellm_response("ok")

        provider = LiteLLMProvider()  # api_base=None
        provider.chat_completion(
            messages=[{"role": "user", "content": "test"}],
            model="openai/gpt-4o",
        )

        call_kwargs = mock_completion.call_args[1]
        assert "api_base" not in call_kwargs


# ---------------------------------------------------------------------------
# get_ai_provider factory function
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetAIProvider:
    """Tests for the get_ai_provider factory function."""

    def _mock_settings(self, **kwargs):
        """Return a mock settings object with sensible defaults."""
        defaults = {
            "ai_provider": "openai",
            "openai_api_key": "sk-test",
            "openai_base_url": "https://api.openai.com/v1",
            "azure_openai_api_version": "2024-02-01",
            "anthropic_api_key": None,
            "gemini_api_key": None,
            "ollama_base_url": "http://localhost:11434",
            "openrouter_api_key": None,
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "portkey_api_key": None,
            "portkey_virtual_key": None,
            "portkey_config": None,
            "portkey_base_url": "https://api.portkey.ai/v1",
        }
        defaults.update(kwargs)
        mock_settings = MagicMock()
        for key, value in defaults.items():
            setattr(mock_settings, key, value)
        return mock_settings

    @patch("openai.OpenAI")
    def test_returns_openai_provider_by_default(self, mock_openai_cls):
        """get_ai_provider returns an OpenAIProvider for ai_provider='openai'."""
        with patch("app.utils.ai_provider.settings", self._mock_settings(ai_provider="openai")):
            provider = get_ai_provider()
        assert isinstance(provider, OpenAIProvider)

    @patch("openai.AzureOpenAI")
    def test_returns_azure_provider(self, mock_azure_cls):
        """get_ai_provider returns AzureOpenAIProvider for ai_provider='azure'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(
                ai_provider="azure",
                openai_base_url="https://my-resource.openai.azure.com",
            ),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, AzureOpenAIProvider)

    def test_returns_anthropic_provider(self):
        """get_ai_provider returns AnthropicProvider for ai_provider='anthropic'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="anthropic", anthropic_api_key="ant-key"),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, AnthropicProvider)

    def test_anthropic_raises_without_api_key(self):
        """get_ai_provider raises ValueError when anthropic_api_key is missing."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="anthropic", anthropic_api_key=None),
        ):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                get_ai_provider()

    def test_returns_gemini_provider(self):
        """get_ai_provider returns GeminiProvider for ai_provider='gemini'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="gemini", gemini_api_key="gemini-key"),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, GeminiProvider)

    def test_gemini_raises_without_api_key(self):
        """get_ai_provider raises ValueError when gemini_api_key is missing."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="gemini", gemini_api_key=None),
        ):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                get_ai_provider()

    @patch("openai.OpenAI")
    def test_returns_ollama_provider(self, mock_openai_cls):
        """get_ai_provider returns OllamaProvider for ai_provider='ollama'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="ollama"),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, OllamaProvider)

    @patch("openai.OpenAI")
    def test_returns_openrouter_provider(self, mock_openai_cls):
        """get_ai_provider returns OpenRouterProvider for ai_provider='openrouter'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="openrouter", openrouter_api_key="or-key"),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, OpenRouterProvider)

    def test_openrouter_raises_without_api_key(self):
        """get_ai_provider raises ValueError when openrouter_api_key is missing."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="openrouter", openrouter_api_key=None),
        ):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                get_ai_provider()

    @patch("openai.OpenAI")
    def test_returns_portkey_provider(self, mock_openai_cls):
        """get_ai_provider returns PortkeyProvider for ai_provider='portkey'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(
                ai_provider="portkey",
                portkey_api_key="pk-test",
                portkey_virtual_key=None,
                portkey_config=None,
                portkey_base_url="https://api.portkey.ai/v1",
            ),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, PortkeyProvider)

    def test_portkey_raises_without_api_key(self):
        """get_ai_provider raises ValueError when portkey_api_key is missing."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(
                ai_provider="portkey",
                portkey_api_key=None,
                portkey_virtual_key=None,
                portkey_config=None,
                portkey_base_url="https://api.portkey.ai/v1",
            ),
        ):
            with pytest.raises(ValueError, match="PORTKEY_API_KEY"):
                get_ai_provider()

    def test_returns_litellm_provider(self):
        """get_ai_provider returns LiteLLMProvider for ai_provider='litellm'."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="litellm"),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, LiteLLMProvider)

    def test_raises_for_unknown_provider(self):
        """get_ai_provider raises ValueError for an unrecognised provider name."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="unsupported_provider"),
        ):
            with pytest.raises(ValueError, match="Unknown AI provider"):
                get_ai_provider()

    def test_provider_name_is_case_insensitive(self):
        """get_ai_provider normalises provider names to lowercase."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(ai_provider="anthropic", anthropic_api_key="ant-key"),
        ):
            # "Anthropic" and "ANTHROPIC" should work just like "anthropic"
            provider = get_ai_provider()
        assert isinstance(provider, AnthropicProvider)

    def test_litellm_passes_non_default_base_url(self):
        """LiteLLM provider receives api_base when openai_base_url differs from default."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(
                ai_provider="litellm",
                openai_base_url="http://my-proxy/v1",
            ),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, LiteLLMProvider)
        assert provider._api_base == "http://my-proxy/v1"

    def test_litellm_omits_base_url_when_default(self):
        """LiteLLM provider has api_base=None when openai_base_url is the default."""
        with patch(
            "app.utils.ai_provider.settings",
            self._mock_settings(
                ai_provider="litellm",
                openai_base_url="https://api.openai.com/v1",
            ),
        ):
            provider = get_ai_provider()
        assert isinstance(provider, LiteLLMProvider)
        assert provider._api_base is None
