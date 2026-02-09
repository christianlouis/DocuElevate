"""Tests for app/api/user.py module."""
import pytest
from hashlib import md5
from unittest.mock import MagicMock

from app.api.user import whoami_handler


@pytest.mark.unit
class TestWhoamiHandler:
    """Tests for whoami_handler function."""

    @pytest.mark.asyncio
    async def test_returns_user_with_gravatar(self):
        """Test that handler returns user data with gravatar URL."""
        mock_request = MagicMock()
        email = "test@example.com"
        mock_request.session = {"user": {"id": "1", "email": email, "name": "Test"}}

        result = await whoami_handler(mock_request)
        assert result["id"] == "1"
        assert result["name"] == "Test"
        # Should have gravatar URL
        expected_hash = md5(email.encode(), usedforsecurity=False).hexdigest()
        assert result["picture"] == f"https://www.gravatar.com/avatar/{expected_hash}?d=identicon"

    @pytest.mark.asyncio
    async def test_raises_401_when_no_user(self):
        """Test that 401 is raised when no user in session."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            await whoami_handler(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_400_when_no_email(self):
        """Test that 400 is raised when user has no email."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "name": "Test"}}

        with pytest.raises(HTTPException) as exc_info:
            await whoami_handler(mock_request)
        assert exc_info.value.status_code == 400


@pytest.mark.integration
class TestWhoamiEndpoints:
    """Tests for whoami API endpoints."""

    def test_whoami_endpoint(self, client):
        """Test /api/whoami endpoint."""
        response = client.get("/api/whoami")
        # Without session user, should return 401
        assert response.status_code == 401

    def test_auth_whoami_endpoint(self, client):
        """Test /api/auth/whoami endpoint."""
        response = client.get("/api/auth/whoami")
        # When auth is disabled, returns 200 with error message (no user in session)
        assert response.status_code == 200
