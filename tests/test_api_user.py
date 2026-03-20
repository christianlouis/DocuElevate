"""Tests for app/api/user.py module."""

from hashlib import md5
from unittest.mock import MagicMock

import pytest

from app.api.user import whoami_handler


@pytest.mark.unit
class TestWhoamiHandler:
    """Tests for whoami_handler function."""

    @pytest.mark.asyncio
    async def test_returns_user_with_gravatar(self):
        """Test that handler returns user data with gravatar URL when no custom avatar."""
        mock_request = MagicMock()
        email = "test@example.com"
        mock_request.session = {"user": {"id": "1", "email": email, "name": "Test"}}

        # Mock DB: no UserProfile found (no custom avatar)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await whoami_handler(mock_request, mock_db)
        assert result["id"] == "1"
        assert result["name"] == "Test"
        # Should have gravatar URL since no custom avatar
        expected_hash = md5(email.encode(), usedforsecurity=False).hexdigest()
        assert result["picture"] == f"https://www.gravatar.com/avatar/{expected_hash}?d=identicon"

    @pytest.mark.asyncio
    async def test_returns_custom_avatar_when_set(self):
        """Test that handler returns custom avatar URL when profile has avatar_data."""
        mock_request = MagicMock()
        email = "test@example.com"
        mock_request.session = {"user": {"id": "1", "email": email, "name": "Test"}}

        # Mock DB: UserProfile with avatar_data
        mock_profile = MagicMock()
        mock_profile.avatar_data = "data:image/png;base64,abc123"
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = await whoami_handler(mock_request, mock_db)
        assert result["picture"] == "data:image/png;base64,abc123"

    @pytest.mark.asyncio
    async def test_raises_401_when_no_user(self):
        """Test that 401 is raised when no user in session."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session = {}
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await whoami_handler(mock_request, mock_db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_raises_400_when_no_email(self):
        """Test that 400 is raised when user has no email."""
        from fastapi import HTTPException

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "name": "Test"}}
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await whoami_handler(mock_request, mock_db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_falls_back_to_gravatar_on_db_error(self):
        """Test that gravatar is used when DB lookup raises an exception."""
        mock_request = MagicMock()
        email = "test@example.com"
        mock_request.session = {"user": {"id": "1", "email": email, "name": "Test"}}

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        result = await whoami_handler(mock_request, mock_db)
        expected_hash = md5(email.encode(), usedforsecurity=False).hexdigest()
        assert result["picture"] == f"https://www.gravatar.com/avatar/{expected_hash}?d=identicon"


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
