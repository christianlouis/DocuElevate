"""
Tests for app/utils/oauth_helper.py

Tests OAuth token exchange helper functions.
"""

from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException


@pytest.mark.unit
class TestOAuthTokenExchange:
    """Test OAuth token exchange functionality"""

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_success(self, mock_settings, mock_post):
        """Test successful OAuth token exchange"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_123",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        payload = {
            "grant_type": "authorization_code",
            "code": "auth_code_123",
            "client_id": "client_id",
            "client_secret": "client_secret",
        }

        result = exchange_oauth_token(
            provider_name="TestProvider",
            token_url="https://oauth.example.com/token",
            payload=payload,
        )

        # Verify result
        assert result["access_token"] == "access_token_123"
        assert result["refresh_token"] == "refresh_token_123"
        assert result["expires_in"] == 3600

        # Verify request was made correctly
        mock_post.assert_called_once_with("https://oauth.example.com/token", data=payload, timeout=30)

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_with_custom_timeout(self, mock_settings, mock_post):
        """Test token exchange with custom timeout"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
        }
        mock_post.return_value = mock_response

        payload = {"grant_type": "authorization_code"}

        exchange_oauth_token(
            provider_name="TestProvider",
            token_url="https://oauth.example.com/token",
            payload=payload,
            timeout=60,
        )

        # Verify custom timeout was used
        mock_post.assert_called_once_with("https://oauth.example.com/token", data=payload, timeout=60)

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_http_error(self, mock_settings, mock_post):
        """Test handling of HTTP error responses"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid authorization code",
        }
        mock_post.return_value = mock_response

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 400

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_missing_refresh_token(self, mock_settings, mock_post):
        """Test handling when refresh_token is missing from response"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock response without refresh_token
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "access_token_123",
            # Missing refresh_token
        }
        mock_post.return_value = mock_response

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException with 502 status
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 502

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_network_error(self, mock_settings, mock_post):
        """Test handling of network errors"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock network error
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException with 503 status
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 503

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_timeout_error(self, mock_settings, mock_post):
        """Test handling of timeout errors"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock timeout error
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException with 503 status
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 503

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_json_decode_error(self, mock_settings, mock_post):
        """Test handling when error response is not valid JSON"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock error response with invalid JSON
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError("Invalid JSON", "", 0)
        mock_post.return_value = mock_response

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 400

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_unexpected_exception(self, mock_settings, mock_post):
        """Test handling of unexpected exceptions"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        # Mock unexpected exception
        mock_post.side_effect = Exception("Unexpected error")

        payload = {"grant_type": "authorization_code"}

        # Should raise HTTPException with 500 status
        with pytest.raises(HTTPException) as exc_info:
            exchange_oauth_token(
                provider_name="TestProvider",
                token_url="https://oauth.example.com/token",
                payload=payload,
            )

        assert exc_info.value.status_code == 500

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_various_grant_types(self, mock_settings, mock_post):
        """Test token exchange with different grant types"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
        }
        mock_post.return_value = mock_response

        # Test with authorization_code grant
        exchange_oauth_token(
            provider_name="Provider1",
            token_url="https://oauth.example.com/token",
            payload={"grant_type": "authorization_code"},
        )

        # Test with refresh_token grant
        exchange_oauth_token(
            provider_name="Provider2",
            token_url="https://oauth.example.com/token",
            payload={"grant_type": "refresh_token"},
        )

        # Should have been called twice
        assert mock_post.call_count == 2

    @patch("app.utils.oauth_helper.requests.post")
    @patch("app.utils.oauth_helper.settings")
    def test_exchange_oauth_token_multiple_providers(self, mock_settings, mock_post):
        """Test token exchange with different provider names"""
        from app.utils.oauth_helper import exchange_oauth_token

        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token",
            "refresh_token": "refresh",
        }
        mock_post.return_value = mock_response

        providers = ["OneDrive", "GoogleDrive", "Dropbox"]
        payload = {"grant_type": "authorization_code"}

        for provider in providers:
            result = exchange_oauth_token(
                provider_name=provider,
                token_url=f"https://{provider.lower()}.example.com/token",
                payload=payload,
            )
            assert "access_token" in result
            assert "refresh_token" in result

        # Should have been called for each provider
        assert mock_post.call_count == len(providers)
