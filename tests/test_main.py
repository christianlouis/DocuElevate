"""
Tests for app/main.py

Tests FastAPI application initialization, middleware, error handlers,
and lifecycle management.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.unit
class TestAppInitialization:
    """Test application initialization and configuration"""

    def test_session_secret_is_set(self):
        """Test that SESSION_SECRET is configured"""
        import app.main

        # SESSION_SECRET should be set (either from settings or default)
        assert app.main.SESSION_SECRET is not None
        assert len(app.main.SESSION_SECRET) > 0

    def test_app_created_successfully(self):
        """Test that FastAPI app is created successfully"""
        from app.main import app

        assert app is not None
        assert app.title == "DocuElevate"


@pytest.mark.unit
class TestLifespanEvents:
    """Test application lifespan events (startup and shutdown)"""

    @pytest.mark.asyncio
    async def test_lifespan_context_manager_executes(self):
        """Test that lifespan context manager can be executed"""
        with (
            patch("app.database.init_db"),
            patch("app.database.SessionLocal") as mock_session_cls,
            patch("app.utils.config_loader.load_settings_from_db"),
            patch("app.utils.config_validator.dump_all_settings"),
            patch("app.utils.config_validator.check_all_configs", return_value={"email": [], "storage": {}}),
            patch("app.utils.notification.init_apprise"),
            patch("app.utils.notification.notify_startup"),
            patch("app.utils.notification.notify_shutdown"),
        ):
            # Mock database session
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db

            from app.main import app, lifespan

            # Execute the startup and shutdown
            async with lifespan(app):
                pass  # Startup completed

            # Shutdown completed
            mock_db.close.assert_called()

    @pytest.mark.asyncio
    async def test_lifespan_startup_with_config_issues(self):
        """Test that lifespan logs warning when there are config issues"""
        with (
            patch("app.database.init_db"),
            patch("app.database.SessionLocal") as mock_session_cls,
            patch("app.utils.config_loader.load_settings_from_db"),
            patch("app.utils.config_validator.dump_all_settings"),
            patch("app.utils.config_validator.check_all_configs") as mock_check,
            patch("app.utils.notification.init_apprise"),
            patch("app.utils.notification.notify_startup"),
            patch("app.utils.notification.notify_shutdown"),
            patch("logging.warning") as mock_warning,
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db
            # Return config with issues
            mock_check.return_value = {"email": ["Invalid email config"], "storage": {"dropbox": ["Missing token"]}}

            from app.main import app, lifespan

            async with lifespan(app):
                pass

            # Should log warning about config issues
            mock_warning.assert_called()

    @pytest.mark.asyncio
    async def test_lifespan_startup_handles_db_settings_load_failure(self):
        """Test that lifespan handles failures when loading settings from DB"""
        with (
            patch("app.database.init_db"),
            patch("app.database.SessionLocal") as mock_session_cls,
            patch("app.utils.config_loader.load_settings_from_db", side_effect=Exception("DB error")),
            patch("app.utils.config_validator.dump_all_settings"),
            patch("app.utils.config_validator.check_all_configs", return_value={"email": [], "storage": {}}),
            patch("app.utils.notification.init_apprise"),
            patch("app.utils.notification.notify_startup"),
            patch("app.utils.notification.notify_shutdown"),
            patch("logging.error") as mock_error,
        ):
            mock_db = MagicMock()
            mock_session_cls.return_value = mock_db

            from app.main import app, lifespan

            # Should not raise exception, just log error
            async with lifespan(app):
                pass

            mock_error.assert_called()


@pytest.mark.unit
class TestExceptionHandlers:
    """Test custom exception handlers"""

    def test_http_exception_handler_frontend_route_404(self):
        """Test that HTTPException returns HTML for frontend 404 errors"""
        from fastapi import Request

        from app.main import http_exception_handler

        # Create a mock request for a frontend route
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/nonexistent"

        exc = HTTPException(status_code=404, detail="Not found")

        # Call the handler directly
        import asyncio

        response = asyncio.run(http_exception_handler(mock_request, exc))

        assert response.status_code == 404

    def test_http_exception_handler_frontend_route_other_error(self):
        """Test that HTTPException returns HTML for other frontend errors"""
        from fastapi import Request

        from app.main import http_exception_handler

        # Create a mock request for a frontend route
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/some-page"

        exc = HTTPException(status_code=403, detail="Forbidden")

        # Call the handler directly
        import asyncio

        response = asyncio.run(http_exception_handler(mock_request, exc))

        assert response.status_code == 403

    def test_custom_500_handler_api_route(self):
        """Test that 500 error returns JSON for API routes"""
        from fastapi import Request

        from app.main import custom_500_handler

        # Create a mock request for an API route
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/something"

        exc = Exception("Internal error")

        # Call the handler directly
        import asyncio

        response = asyncio.run(custom_500_handler(mock_request, exc))

        assert response.status_code == 500
        # Parse JSON response
        import json

        content = json.loads(response.body.decode())
        assert content["detail"] == "Internal server error"

    def test_custom_500_handler_frontend_route(self):
        """Test that 500 error returns HTML for frontend routes"""
        from fastapi import Request

        from app.main import custom_500_handler

        # Create a mock request for a frontend route
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/dashboard"

        exc = Exception("Internal error")

        # Call the handler directly
        import asyncio

        response = asyncio.run(custom_500_handler(mock_request, exc))

        assert response.status_code == 500


@pytest.mark.unit
class TestTestEndpoint:
    """Test the /test-500 debugging endpoint"""

    def test_test_500_endpoint_raises_error(self):
        """Test that /test-500 endpoint raises RuntimeError"""
        from app.main import test_500

        # The function should raise RuntimeError
        with pytest.raises(RuntimeError, match="Testing forced 500 error"):
            test_500()


@pytest.mark.unit
class TestStaticFileMount:
    """Test static file mounting logic"""

    def test_static_files_mounted_when_directory_exists(self):
        """Test that static files are served when directory exists"""
        import pathlib

        from app.main import app

        # Check if static directory exists
        static_dir = pathlib.Path(__file__).parents[1] / "frontend" / "static"

        if os.path.exists(static_dir):
            # Check if static route is mounted
            assert any("/static" in str(route.path) for route in app.routes)


@pytest.mark.unit
class TestMiddlewareConfiguration:
    """Test middleware configuration"""

    def test_app_has_limiter_state(self):
        """Test that app.state.limiter is configured"""
        from app.main import app

        assert hasattr(app.state, "limiter")
        assert app.state.limiter is not None

    def test_app_has_correct_title(self):
        """Test that FastAPI app has correct title"""
        from app.main import app

        assert app.title == "DocuElevate"
