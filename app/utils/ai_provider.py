#!/usr/bin/env python3
"""AI provider abstraction layer for DocuElevate.

This module provides a pluggable abstraction for various AI model providers,
allowing the platform to work with OpenAI, Azure OpenAI, Anthropic Claude,
Google Gemini, Ollama (local LLMs), OpenRouter, and any LiteLLM-compatible
provider without being locked to a single vendor.

Provider selection is controlled by the ``AI_PROVIDER`` environment variable.
See the Configuration Guide for full details on each provider's settings.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI chat completion providers.

    All concrete providers must implement :meth:`chat_completion`, which
    accepts a list of chat messages and returns the model's response as a
    plain string.  The interface intentionally mirrors the OpenAI Chat
    Completions API so that callers need no provider-specific knowledge.
    """

    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        """Get a chat completion from the AI provider.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.
            model: Model name/identifier to use (provider-specific format).
            temperature: Sampling temperature (0–1). Default: 0 (deterministic).
            **kwargs: Additional provider-specific arguments passed through.

        Returns:
            The model's response as a plain string.

        Raises:
            Exception: If the underlying API call fails.
        """


class OpenAIProvider(AIProvider):
    """OpenAI provider using the ``openai`` Python SDK.

    Also works as a drop-in for any OpenAI-compatible API endpoint, including
    LocalAI and LM Studio.  Ollama and OpenRouter have dedicated providers with
    sensible defaults, but this provider works for them too when a custom
    ``base_url`` is supplied.
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None) -> None:
        import openai

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return completion.choices[0].message.content


class AzureOpenAIProvider(AIProvider):
    """Azure OpenAI provider using the ``openai`` Python SDK's Azure client."""

    def __init__(self, api_key: str, azure_endpoint: str, api_version: str = "2024-02-01") -> None:
        import openai

        self._client = openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return completion.choices[0].message.content


class AnthropicProvider(AIProvider):
    """Anthropic Claude provider routed via LiteLLM.

    Requires ``litellm`` to be installed.  Model names should be in Anthropic
    format (e.g. ``claude-3-5-sonnet-20241022``); the ``anthropic/`` prefix is
    added automatically when absent.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        import litellm

        model_name = model if model.startswith("anthropic/") else f"anthropic/{model}"
        response = litellm.completion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            api_key=self._api_key,
            **kwargs,
        )
        return response.choices[0].message.content


class GeminiProvider(AIProvider):
    """Google Gemini provider routed via LiteLLM.

    Requires ``litellm`` to be installed.  Model names should be in Gemini
    format (e.g. ``gemini-1.5-pro``); the ``gemini/`` prefix is added
    automatically when absent.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        import litellm

        model_name = model if model.startswith("gemini/") else f"gemini/{model}"
        response = litellm.completion(
            model=model_name,
            messages=messages,
            temperature=temperature,
            api_key=self._api_key,
            **kwargs,
        )
        return response.choices[0].message.content


class OllamaProvider(AIProvider):
    """Ollama local LLM provider via its OpenAI-compatible REST API.

    Ollama exposes an OpenAI-compatible endpoint at ``/v1``.  Any model
    pulled into your Ollama instance (e.g. ``llama3.2``, ``qwen2.5``,
    ``phi3``) can be used directly by name.

    For CPU-only deployments the recommended models are:

    * ``llama3.2`` (3B) – good balance of speed and quality
    * ``qwen2.5`` (3B/7B) – excellent at structured JSON output
    * ``phi3`` (3.8B) – strong reasoning, fast on CPU

    See https://ollama.com for installation and model management.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        import openai

        self._client = openai.OpenAI(
            api_key="ollama",  # Ollama does not require a real API key
            base_url=f"{base_url.rstrip('/')}/v1",
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return completion.choices[0].message.content


class OpenRouterProvider(AIProvider):
    """OpenRouter AI aggregator (https://openrouter.ai).

    OpenRouter provides access to 100+ models from OpenAI, Anthropic, Google,
    Meta, Mistral, and many others through a single OpenAI-compatible endpoint.
    Model names use the ``provider/model`` format (e.g.
    ``anthropic/claude-3.5-sonnet``, ``google/gemini-pro``).
    """

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1") -> None:
        import openai

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        completion = self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        return completion.choices[0].message.content


class LiteLLMProvider(AIProvider):
    """LiteLLM provider – unified interface for 100+ LLMs.

    LiteLLM (https://litellm.ai) translates calls to a single interface that
    supports OpenAI, Azure, Anthropic, Gemini, Cohere, Ollama, and many more.
    Use the LiteLLM model-string format ``provider/model`` (e.g.
    ``openai/gpt-4o``, ``anthropic/claude-3-5-sonnet-20241022``,
    ``ollama/llama3.2``).

    This provider is useful when you want LiteLLM to handle all routing and
    need features like automatic retries, fallbacks, or cost tracking.
    """

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None) -> None:
        self._api_key = api_key
        self._api_base = api_base

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0,
        **kwargs: Any,
    ) -> str:
        import litellm

        completion_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if self._api_key:
            completion_kwargs["api_key"] = self._api_key
        if self._api_base:
            completion_kwargs["api_base"] = self._api_base
        completion_kwargs.update(kwargs)
        response = litellm.completion(**completion_kwargs)
        return response.choices[0].message.content


def get_ai_provider() -> AIProvider:
    """Factory function that creates and returns the configured AI provider.

    Reads ``settings.ai_provider`` (set via the ``AI_PROVIDER`` environment
    variable) to select the provider implementation.  Provider-specific
    credentials and URLs are read from their corresponding settings fields.

    Returns:
        An :class:`AIProvider` instance ready to serve chat completions.

    Raises:
        ValueError: If the configured provider name is not recognised.
        ValueError: If required credentials for the selected provider are absent.
    """
    from app.config import settings

    provider = settings.ai_provider.lower()
    logger.debug(f"Creating AI provider: {provider}")

    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    elif provider == "azure":
        return AzureOpenAIProvider(
            api_key=settings.openai_api_key,
            azure_endpoint=settings.openai_base_url,
            api_version=settings.azure_openai_api_version,
        )
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set when AI_PROVIDER='anthropic'")
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    elif provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY must be set when AI_PROVIDER='gemini'")
        return GeminiProvider(api_key=settings.gemini_api_key)
    elif provider == "ollama":
        return OllamaProvider(base_url=settings.ollama_base_url)
    elif provider == "openrouter":
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY must be set when AI_PROVIDER='openrouter'")
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
    elif provider == "litellm":
        return LiteLLMProvider(
            api_key=settings.openai_api_key or None,
            api_base=settings.openai_base_url if settings.openai_base_url != "https://api.openai.com/v1" else None,
        )
    else:
        raise ValueError(
            f"Unknown AI provider: '{provider}'. "
            "Supported providers: openai, azure, anthropic, gemini, ollama, openrouter, litellm"
        )
