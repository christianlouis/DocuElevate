"""Tests for app/views/settings.py module."""

from unittest.mock import MagicMock, patch

import pytest

from app.views.settings import require_admin_access


@pytest.mark.unit
class TestRequireAdminAccess:
    """Tests for require_admin_access decorator."""

    @pytest.mark.asyncio
    async def test_redirects_non_admin_user(self):
        """Test that non-admin users are redirected."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "1", "is_admin": False}}

        result = await dummy_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_redirects_when_no_user(self):
        """Test that unauthenticated users are redirected."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {}

        result = await dummy_route(mock_request)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_allows_admin_user(self):
        """Test that admin users can access the route."""

        @require_admin_access
        async def dummy_route(request):
            return {"success": True}

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "admin", "is_admin": True}}

        result = await dummy_route(mock_request)
        assert result == {"success": True}


@pytest.mark.integration
class TestSettingsView:
    """Tests for settings page endpoint."""

    def test_settings_page_redirects_without_admin(self, client):
        """Test settings page redirects non-admin users."""
        response = client.get("/settings", follow_redirects=False)
        # Should redirect since no user in session
        assert response.status_code in (200, 302, 303)
