"""Tests for app/views/admin_users.py module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# _require_admin helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequireAdmin:
    """Unit tests for the _require_admin helper in views/admin_users.py."""

    def test_returns_none_when_no_user_in_session(self):
        """_require_admin returns None when session has no user."""
        from app.views.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {}

        result = _require_admin(mock_request)
        assert result is None

    def test_returns_none_for_non_admin_user(self):
        """_require_admin returns None when user is not an admin."""
        from app.views.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com", "is_admin": False}}

        result = _require_admin(mock_request)
        assert result is None

    def test_logs_warning_for_non_admin(self):
        """_require_admin logs a warning when a non-admin attempts access."""
        from app.views.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com", "is_admin": False}}

        with patch("app.views.admin_users.logger") as mock_logger:
            _require_admin(mock_request)
            mock_logger.warning.assert_called_once()

    def test_logs_warning_when_no_user(self):
        """_require_admin logs a warning when there is no user in the session."""
        from app.views.admin_users import _require_admin

        mock_request = MagicMock()
        mock_request.session = {}

        with patch("app.views.admin_users.logger") as mock_logger:
            _require_admin(mock_request)
            mock_logger.warning.assert_called_once()

    def test_returns_user_for_admin(self):
        """_require_admin returns the user dict when the user is an admin."""
        from app.views.admin_users import _require_admin

        admin_user = {"email": "admin@example.com", "is_admin": True}
        mock_request = MagicMock()
        mock_request.session = {"user": admin_user}

        result = _require_admin(mock_request)
        assert result == admin_user


# ---------------------------------------------------------------------------
# admin_users_page route
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAdminUsersPage:
    """Unit tests for the admin_users_page view handler."""

    @pytest.mark.asyncio
    async def test_redirects_non_admin_to_home(self):
        """admin_users_page redirects to '/' when user is not an admin."""
        from fastapi.responses import RedirectResponse

        from app.views.admin_users import admin_users_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com", "is_admin": False}}

        result = await admin_users_page(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_redirects_when_no_user_in_session(self):
        """admin_users_page redirects to '/' when no user is in the session."""
        from fastapi.responses import RedirectResponse

        from app.views.admin_users import admin_users_page

        mock_request = MagicMock()
        mock_request.session = {}

        result = await admin_users_page(mock_request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_returns_template_for_admin(self):
        """admin_users_page returns the template response for an admin user."""
        from app.views.admin_users import admin_users_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}

        mock_template_response = MagicMock()

        with patch("app.views.admin_users.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = mock_template_response

            result = await admin_users_page(mock_request)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "admin_users.html"
        context = call_args[0][1]
        assert context["request"] is mock_request
        assert "app_version" in context
        assert isinstance(context["app_version"], str)
        assert result is mock_template_response

    @pytest.mark.asyncio
    async def test_raises_500_on_template_error(self):
        """admin_users_page raises HTTPException 500 when template rendering fails."""
        from app.views.admin_users import admin_users_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}

        with patch("app.views.admin_users.templates") as mock_templates:
            mock_templates.TemplateResponse.side_effect = RuntimeError("Template not found")

            with pytest.raises(HTTPException) as exc_info:
                await admin_users_page(mock_request)

        assert exc_info.value.status_code == 500
        assert "Failed to load admin users page" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_logs_error_on_template_failure(self):
        """admin_users_page logs an error when template rendering fails."""
        from app.views.admin_users import admin_users_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}

        with (
            patch("app.views.admin_users.templates") as mock_templates,
            patch("app.views.admin_users.logger") as mock_logger,
        ):
            mock_templates.TemplateResponse.side_effect = RuntimeError("Template not found")

            with pytest.raises(HTTPException):
                await admin_users_page(mock_request)

            mock_logger.error.assert_called_once()
