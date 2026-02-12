"""Tests for app/api/settings.py module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.settings import require_admin


@pytest.mark.unit
class TestRequireAdmin:
    """Tests for require_admin dependency."""

    def test_raises_403_when_no_user(self):
        """Test that 403 is raised when no user in session."""
        mock_request = MagicMock()
        mock_request.session = {}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_raises_403_when_not_admin(self):
        """Test that 403 is raised for non-admin user."""
        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_request)
        assert exc_info.value.status_code == 403

    def test_returns_user_when_admin(self):
        """Test that admin user is returned."""
        mock_request = MagicMock()
        user = {"id": "admin", "is_admin": True}
        mock_request.session = {"user": user}

        result = require_admin(mock_request)
        assert result == user
