"""
AI provider and OpenAI API endpoints.

Exposes three endpoints:
- GET /api/ai/test             – tests the currently configured AI provider (generic, provider-agnostic)
- GET /api/openai/test         – backward-compatible alias that tests the OpenAI API specifically
- POST /api/ai/test-extraction – runs the metadata-extraction prompt against the configured AI provider
                                 with caller-supplied plaintext and returns the raw response, parsed JSON,
                                 and extracted tags so operators can evaluate model quality.
"""

import json
import logging
import re

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.auth import require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum number of characters accepted for a test-extraction request.
# Keeps individual requests reasonable without blocking any real-world document.
_MAX_EXTRACTION_TEXT_LEN = 50_000


def _get_exception_chain_detail(exc: Exception) -> str:
    """
    Extract a verbose diagnostic message by walking the full exception chain.

    Surfaces DNS resolution failures, TCP connection refused errors, SSL issues,
    and other low-level network problems that are normally hidden behind a generic
    'Connection error.' message.
    """
    parts: list[str] = [str(exc)]

    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    seen: set[int] = {id(exc)}
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        cause_str = str(cause)
        if cause_str and cause_str not in parts:
            parts.append(f"caused by: {type(cause).__name__}: {cause_str}")
        cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)

    return " | ".join(parts)


@router.get("/openai/test")
@require_login
async def test_openai_connection(request: Request):
    """
    Test if the configured OpenAI API key is valid.
    """
    try:
        import openai

        logger.info("Testing OpenAI API key validity")

        # Check if API key is configured
        if not settings.openai_api_key:
            logger.warning("No OpenAI API key configured")
            return {"status": "error", "message": "No OpenAI API key is configured"}

        # Configure the client, explicitly passing base_url so the sanitized
        # value from Settings (strip_outer_quotes) is used instead of the raw
        # OPENAI_BASE_URL env var which may contain literal quote characters.
        client = openai.OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

        # Try to make a simple request to validate the key
        try:
            # Use a models list endpoint as a simple validation
            models = client.models.list()

            # If we got here, the key is valid
            logger.info("OpenAI API key is valid")
            return {
                "status": "success",
                "message": "OpenAI API key is valid",
                "models_available": len(models.data) if hasattr(models, "data") else "Unknown",
            }

        except openai.APITimeoutError as e:
            detail = _get_exception_chain_detail(e)
            logger.error(f"OpenAI API request timed out: {detail}", exc_info=True)
            return {
                "status": "error",
                "message": f"Request timed out: {detail}",
                "is_auth_error": False,
                "error_type": "timeout",
            }

        except openai.APIConnectionError as e:
            detail = _get_exception_chain_detail(e)
            base_url = getattr(getattr(client, "_client", None), "base_url", None)
            base_url_info = f" (base_url: {base_url})" if base_url else ""
            logger.error(
                f"OpenAI API connection error{base_url_info}: {detail}",
                exc_info=True,
            )
            return {
                "status": "error",
                "message": f"Connection error{base_url_info}: {detail}",
                "is_auth_error": False,
                "error_type": "connection_error",
            }

        except openai.AuthenticationError as e:
            logger.error(f"OpenAI authentication error (status {e.status_code}): {e.message}", exc_info=True)
            return {
                "status": "error",
                "message": f"Authentication failed: {e.message}",
                "is_auth_error": True,
                "error_type": "authentication_error",
            }

        except openai.RateLimitError as e:
            logger.warning(f"OpenAI rate limit exceeded (status {e.status_code}): {e.message}")
            return {
                "status": "error",
                "message": f"Rate limit exceeded: {e.message}",
                "is_auth_error": False,
                "error_type": "rate_limit",
            }

        except openai.APIStatusError as e:
            logger.error(
                f"OpenAI API returned HTTP {e.status_code}: {e.message} | "
                f"request_id={e.response.headers.get('x-request-id', 'n/a')}"
            )
            return {
                "status": "error",
                "message": f"API error (HTTP {e.status_code}): {e.message}",
                "is_auth_error": e.status_code == 401,
                "error_type": "api_status_error",
                "http_status": e.status_code,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"OpenAI API key test failed: {error_msg}", exc_info=True)

            # Determine if this is an authentication error
            is_auth_error = "auth" in error_msg.lower() or "api key" in error_msg.lower()

            return {
                "status": "error",
                "message": f"API key validation failed: {error_msg}",
                "is_auth_error": is_auth_error,
            }

    except ImportError:
        logger.exception("OpenAI package not installed")
        return {"status": "error", "message": "OpenAI package not installed"}
    except Exception as e:
        logger.exception("Unexpected error testing OpenAI connection")
        return {"status": "error", "message": f"Unexpected error: {str(e)}"}


@router.get("/ai/test")
@require_login
async def test_ai_provider_connection(request: Request):
    """
    Test the currently configured AI provider connection.

    Uses ``get_ai_provider()`` to instantiate the active provider and sends a
    minimal chat completion to verify that the credentials and endpoint are
    reachable.  Works for all supported providers (OpenAI, Azure, Anthropic,
    Gemini, Ollama, OpenRouter, Portkey, LiteLLM).
    """
    from app.utils.ai_provider import get_ai_provider

    provider_name = settings.ai_provider
    model = settings.ai_model or settings.openai_model

    logger.info(f"Testing AI provider connection: provider={provider_name}, model={model}")

    try:
        provider = get_ai_provider()
        response = provider.chat_completion(
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            model=model,
            temperature=0,
            max_tokens=5,
        )
        logger.info(f"AI provider test successful: provider={provider_name}")
        return {
            "status": "success",
            "message": f"AI provider '{provider_name}' is reachable and responding",
            "provider": provider_name,
            "model": model,
            "response_preview": (response or "")[:50],
        }
    except ValueError as e:
        # Configuration errors (missing keys, unknown provider)
        logger.warning(f"AI provider configuration error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "provider": provider_name,
        }
    except Exception as e:
        detail = _get_exception_chain_detail(e)
        logger.error(f"AI provider test failed for '{provider_name}': {detail}", exc_info=True)
        return {
            "status": "error",
            "message": f"Connection failed: {detail}",
            "provider": provider_name,
        }


class ExtractionTestRequest(BaseModel):
    """Request body for the AI extraction test endpoint."""

    text: str = Field(..., min_length=1, max_length=_MAX_EXTRACTION_TEXT_LEN, description="Plain-text document content")


def _build_extraction_prompt(text: str) -> str:
    """Return the metadata-extraction prompt used in the standard processing pipeline."""
    return (
        "You are a specialized document analyzer trained to extract structured metadata from documents.\n"
        "Your task is to analyze the given text and return a well-structured JSON object.\n\n"
        "Extract and return the following fields:\n"
        "1. **filename**: Machine-readable filename "
        "(YYYY-MM-DD_DescriptiveTitle, use only letters, numbers, periods, and underscores).\n"
        '2. **empfaenger**: The recipient, or "Unknown" if not found.\n'
        '3. **absender**: The sender, or "Unknown" if not found.\n'
        "4. **correspondent**: The entity or company that issued the document "
        '(shortest possible name, e.g., "Amazon" instead of "Amazon EU SARL, German branch").\n'
        "5. **kommunikationsart**: One of [Behoerdlicher_Brief, Rechnung, Kontoauszug, Vertrag, "
        "Quittung, Privater_Brief, Einladung, Gewerbliche_Korrespondenz, Newsletter, Werbung, Sonstiges].\n"
        "6. **kommunikationskategorie**: One of [Amtliche_Postbehoerdliche_Dokumente, "
        "Finanz_und_Vertragsdokumente, Geschaeftliche_Kommunikation, "
        "Private_Korrespondenz, Sonstige_Informationen].\n"
        "7. **document_type**: Precise classification (e.g., Invoice, Contract, Information, Unknown).\n"
        "8. **tags**: A list of up to 4 relevant thematic keywords.\n"
        '9. **language**: Detected document language (ISO 639-1 code, e.g., "de" or "en").\n'
        "10. **title**: A human-readable title summarizing the document content.\n"
        "11. **confidence_score**: A numeric value (0-100) indicating the confidence level "
        "of the extracted metadata.\n"
        "12. **reference_number**: Extracted invoice/order/reference number if available.\n"
        "13. **monetary_amounts**: A list of key monetary values detected in the document.\n\n"
        "### Important Rules:\n"
        "- **OCR Correction**: Assume the text has been corrected for OCR errors.\n"
        "- **Tagging**: Max 4 tags, avoiding generic or overly specific terms.\n"
        "- **Title**: Concise, no addresses, and contains key identifying features.\n"
        "- **Date Selection**: Use the most relevant date if multiple are found.\n"
        "- **Output Language**: Maintain the document's original language.\n\n"
        f"Extracted text:\n{text}\n\n"
        "Return only valid JSON with no additional commentary.\n"
    )


def _extract_json_from_text(text: str):
    """Try to extract a JSON object from the LLM response text."""
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


@router.post("/ai/test-extraction")
@require_login
async def test_ai_extraction(body: ExtractionTestRequest, request: Request):
    """
    Run the metadata-extraction prompt against the configured AI provider.

    Accepts plain-text document content, sends it through the same prompt used
    by the background processing pipeline, and returns:
    - ``raw_response``:  verbatim LLM output
    - ``parsed_json``:   the extracted JSON object (null when parsing fails)
    - ``tags``:          the ``tags`` list from the parsed JSON (empty list on failure)
    - ``provider`` / ``model``: which provider / model was used
    """
    from app.utils.ai_provider import get_ai_provider

    provider_name = settings.ai_provider
    model = settings.ai_model or settings.openai_model

    logger.info(f"AI extraction test requested: provider={provider_name}, model={model}")

    try:
        provider = get_ai_provider()
        prompt = _build_extraction_prompt(body.text)
        raw_response = provider.chat_completion(
            messages=[
                {"role": "system", "content": "You are an intelligent document classifier."},
                {"role": "user", "content": prompt},
            ],
            model=model,
            temperature=0,
        )
    except ValueError as e:
        logger.warning(f"AI extraction test – configuration error: {e}")
        return {"status": "error", "message": str(e), "provider": provider_name}
    except Exception as e:
        detail = _get_exception_chain_detail(e)
        logger.error(f"AI extraction test failed for provider '{provider_name}': {detail}", exc_info=True)
        return {"status": "error", "message": f"AI call failed: {detail}", "provider": provider_name}

    # Attempt to parse JSON from the response
    parsed_json = None
    tags: list = []
    parse_error = None
    json_text = _extract_json_from_text(raw_response)
    if json_text:
        try:
            parsed_json = json.loads(json_text)
            tags = parsed_json.get("tags", [])
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            logger.warning(f"AI extraction test: JSON parse error: {exc}")
    else:
        parse_error = "No JSON object found in response"

    return {
        "status": "success",
        "provider": provider_name,
        "model": model,
        "raw_response": raw_response,
        "parsed_json": parsed_json,
        "tags": tags,
        "parse_error": parse_error,
    }
