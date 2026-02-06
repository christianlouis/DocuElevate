#!/usr/bin/env python3
"""
AI service provider status module
"""

from app.config import settings
from app.utils.config_validator.masking import mask_sensitive_value


def get_ai_providers_status():
    """Returns AI service provider statuses"""
    providers = {}

    # OpenAI configuration
    providers["OpenAI"] = {
        "name": "OpenAI",
        "icon": "fa-brands fa-openai",
        "configured": bool(
            getattr(settings, "openai_api_key", None) and str(getattr(settings, "openai_api_key", "")).startswith("sk-")
        ),
        "enabled": True,
        "description": "AI-powered document analysis and metadata extraction",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, "openai_api_key", None)),
            "base_url": getattr(settings, "openai_base_url", "https://api.openai.com/v1"),
            "model": getattr(settings, "openai_model", "gpt-4"),
        },
    }

    # Azure AI configuration
    providers["Azure AI"] = {
        "name": "Azure AI",
        "icon": "fa-solid fa-robot",
        "configured": bool(getattr(settings, "azure_ai_key", None) and getattr(settings, "azure_endpoint", None)),
        "enabled": True,
        "description": "Microsoft Azure Document Intelligence",
        "details": {
            "api_key": mask_sensitive_value(getattr(settings, "azure_ai_key", None)),
            "endpoint": getattr(settings, "azure_endpoint", "Not set"),
            "region": getattr(settings, "azure_region", "Not set"),
        },
    }

    return providers
