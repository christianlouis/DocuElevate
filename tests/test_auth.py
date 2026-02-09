"""Tests for app/auth.py module."""
import hashlib
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.testclient import TestClient
from fastapi import Request

from app.auth import get_current_user, get_gravatar_url, require_login


@pytest.mark.unit
class TestGetCurrentUser:
    """Tests for get_current_user function."""

    def test_returns_user_from_session(self):
        """Test that get_current_user returns user data from session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {"user": {"id": "test_user", "name": "Test"}}
        result = get_current_user(mock_request)
        assert result == {"id": "test_user", "name": "Test"}

    def test_returns_none_when_no_user(self):
        """Test that get_current_user returns None when no user in session."""
        mock_request = MagicMock(spec=Request)
        mock_request.session = {}
        result = get_current_user(mock_request)
        assert result is None


@pytest.mark.unit
class TestGetGravatarUrl:
    """Tests for get_gravatar_url function."""

    def test_generates_correct_url(self):
        """Test gravatar URL generation with known email."""
        email = "test@example.com"
        expected_hash = hashlib.md5(email.lower().strip().encode("utf-8"), usedforsecurity=False).hexdigest()
        result = get_gravatar_url(email)
        assert result == f"https://www.gravatar.com/avatar/{expected_hash}?d=identicon"

    def test_handles_uppercase_email(self):
        """Test that email is lowercased."""
        result_upper = get_gravatar_url("TEST@EXAMPLE.COM")
        result_lower = get_gravatar_url("test@example.com")
        assert result_upper == result_lower

    def test_handles_whitespace(self):
        """Test that whitespace is stripped."""
        result_spaces = get_gravatar_url("  test@example.com  ")
        result_clean = get_gravatar_url("test@example.com")
        assert result_spaces == result_clean


@pytest.mark.unit
class TestRequireLogin:
    """Tests for require_login decorator."""

    def test_noop_when_auth_disabled(self):
        """Test that require_login is a no-op when AUTH_ENABLED is False."""
        # AUTH_ENABLED is False in test environment
        def my_func():
            return "hello"
        
        decorated = require_login(my_func)
        # When AUTH_ENABLED is False, the decorator returns the function unchanged
        assert decorated is my_func


@pytest.mark.integration
class TestWhoamiEndpoint:
    """Tests for the /api/auth/whoami endpoint."""

    def test_whoami_returns_user_or_error(self, client):
        """Test whoami endpoint without auth (auth disabled)."""
        response = client.get("/api/auth/whoami")
        assert response.status_code == 200
        data = response.json()
        # When auth is disabled and no user in session, returns error dict
        assert "error" in data or "id" in data

    def test_private_endpoint(self, client):
        """Test /private endpoint without auth (auth disabled)."""
        response = client.get("/private")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
