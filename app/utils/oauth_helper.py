"""
OAuth helper utilities for token exchange operations.
Shared across multiple OAuth providers to reduce code duplication.
"""

import logging
from typing import Any, Dict, Optional

import requests
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

_OAUTH_ERROR_CODES = {
    "invalid_request": "invalid_request",
    "invalid_client": "invalid_client",
    "invalid_grant": "invalid_grant",
    "unauthorized_client": "unauthorized_client",
    "unsupported_grant_type": "unsupported_grant_type",
    "invalid_scope": "invalid_scope",
}


def _safe_oauth_error_code(value: object) -> str:
    """Return a fixed OAuth error label without reflecting provider text."""
    if isinstance(value, str):
        return _OAUTH_ERROR_CODES.get(value, "provider_error")
    return "provider_error"


def exchange_oauth_token(
    provider_name: str, token_url: str, payload: Dict[str, str], timeout: Optional[int] = None
) -> Dict[str, Any]:
    """
    Exchange an authorization code for tokens from an OAuth provider.

    This function handles the common OAuth token exchange flow across multiple providers
    (OneDrive, Google Drive, Dropbox) with proper error handling and secure logging.

    Args:
        provider_name: Name of the OAuth provider (for logging)
        token_url: OAuth token endpoint URL
        payload: Request payload containing client credentials and auth code
        timeout: Request timeout in seconds (defaults to settings.http_request_timeout)

    Returns:
        Dict containing the token response from the provider

    Raises:
        HTTPException: If token exchange fails or response is invalid
    """
    if timeout is None:
        timeout = settings.http_request_timeout

    try:
        logger.info("Starting OAuth token exchange process")

        # Make the token request
        logger.info("Sending OAuth token exchange request")
        response = requests.post(token_url, data=payload, timeout=timeout)

        # Check if the request was successful
        logger.info(f"Token exchange response status: {response.status_code}")

        if response.status_code != 200:
            try:
                error_json = response.json()
                error_code = _safe_oauth_error_code(error_json.get("error") if isinstance(error_json, dict) else None)
                logger.error("OAuth token exchange failed with status %s", response.status_code)
                error_detail = f"Token exchange failed: {error_code}"
            except (ValueError, requests.exceptions.JSONDecodeError):
                logger.error("OAuth token exchange returned an invalid error response")
                error_detail = "Token exchange failed: provider_error"

            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail)

        # Parse the token response
        token_data = response.json()

        # Validate the token response
        if "refresh_token" not in token_data:
            logger.error("OAuth server returned success without a refresh token")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OAuth server returned success but no refresh token was included",
            )

        # Log success with non-sensitive metadata only
        logger.info("Successfully exchanged OAuth authorization code")

        return token_data

    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except requests.exceptions.RequestException:
        logger.error("OAuth token exchange network failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to connect to OAuth service",
        )
    except Exception:
        logger.error("Unexpected OAuth token exchange failure")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to exchange token")
