"""
OpenAI API endpoints
"""

import logging

from fastapi import APIRouter, Request

from app.auth import require_login
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


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

        # Configure the client
        client = openai.OpenAI(api_key=settings.openai_api_key)

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
