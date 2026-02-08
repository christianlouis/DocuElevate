"""
OAuth helper utilities for token exchange operations.
Shared across multiple OAuth providers to reduce code duplication.
"""

import logging
from typing import Dict, Any
import requests
from fastapi import HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)


def exchange_oauth_token(
    provider_name: str, token_url: str, payload: Dict[str, str], timeout: int = None
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
        logger.info(f"Starting {provider_name} token exchange process")

        # SECURITY: Never log sensitive data - only log non-sensitive metadata
        safe_info = {
            "provider": provider_name,
            "token_url": token_url,
            "grant_type": payload.get("grant_type", "unknown"),
        }
        logger.info(f"Token exchange request: {safe_info}")

        # Make the token request
        logger.info(f"Sending POST request to {provider_name} for token exchange")
        response = requests.post(token_url, data=payload, timeout=timeout)

        # Check if the request was successful
        logger.info(f"Token exchange response status: {response.status_code}")

        if response.status_code != 200:
            # Log the error response for debugging (without sensitive data)
            try:
                error_json = response.json()
                # Extract only error type, not full details which may contain sensitive info
                error_type = error_json.get("error", "unknown_error")
                logger.error(f"Token exchange failed with status {response.status_code}: {error_type}")
                error_detail = {"error": error_type, "error_description": error_json.get("error_description", "")}
            except Exception as json_err:
                logger.error(f"Failed to parse error response as JSON: {str(json_err)}")
                error_detail = {"error": "Unknown error", "status_code": response.status_code}

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Token exchange failed: {error_detail}"
            )

        # Parse the token response
        token_data = response.json()

        # Validate the token response
        if "refresh_token" not in token_data:
            logger.error(f"{provider_name} returned success but no refresh_token found in response")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"{provider_name} OAuth server returned success but no refresh token was included",
            )

        # Log success with non-sensitive metadata only
        logger.info(f"Successfully exchanged authorization code for {provider_name} tokens")

        return token_data

    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except requests.exceptions.RequestException as e:
        logger.exception(f"Network error during {provider_name} token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to connect to {provider_name} OAuth service: {str(e)}",
        )
    except Exception as e:
        logger.exception(f"Unexpected error during {provider_name} token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to exchange token: {str(e)}"
        )
