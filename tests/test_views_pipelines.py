"""Tests for app/views/pipelines.py module.

Covers the pipelines management UI page.
"""

from unittest.mock import patch

import pytest


@pytest.mark.integration
class TestPipelinesView:
    """Integration tests for the /pipelines view route."""

    def test_pipelines_page_returns_200(self, client):
        """GET /pipelines returns HTTP 200."""
        response = client.get("/pipelines")
        assert response.status_code == 200

    def test_pipelines_page_renders_html(self, client):
        """GET /pipelines returns HTML content with a proper html tag."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert b"<html" in response.content.lower()

    def test_pipelines_page_contains_title(self, client):
        """GET /pipelines response contains the page title."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert b"Processing Pipelines" in response.content

    def test_pipelines_page_content_type_is_html(self, client):
        """GET /pipelines response has HTML content-type."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_pipelines_route_is_registered(self, client):
        """GET /pipelines must not return 405 Method Not Allowed."""
        response = client.get("/pipelines", follow_redirects=False)
        assert response.status_code != 405

    def test_pipelines_page_contains_pipeline_diagram_icon(self, client):
        """GET /pipelines page contains the pipeline diagram icon class."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert b"fa-project-diagram" in response.content

    def test_pipelines_page_contains_create_pipeline_button(self, client):
        """GET /pipelines response references pipeline creation button text."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert b"Create Pipeline" in response.content

    def test_pipelines_page_contains_alpine_app_component(self, client):
        """GET /pipelines response includes the Alpine.js pipelinesApp component."""
        response = client.get("/pipelines")
        assert response.status_code == 200
        assert b"pipelinesApp" in response.content


@pytest.mark.unit
class TestPipelinesViewUnit:
    """Unit tests for app/views/pipelines.py."""

    def test_pipelines_page_error_returns_500(self, client):
        """When template rendering raises an exception, GET /pipelines returns HTTP 500."""
        with patch("app.views.pipelines.templates.TemplateResponse", side_effect=Exception("render error")):
            response = client.get("/pipelines")
        assert response.status_code == 500

    def test_pipelines_page_error_returns_html_500(self, client):
        """HTTP 500 response from the non-API /pipelines route returns an HTML page."""
        with patch("app.views.pipelines.templates.TemplateResponse", side_effect=Exception("render error")):
            response = client.get("/pipelines")
        assert response.status_code == 500
        # Non-API routes return HTML, not JSON
        assert "text/html" in response.headers.get("content-type", "")

    def test_pipelines_page_logs_error_on_exception(self, client):
        """When template rendering fails, the error is logged."""
        with (
            patch("app.views.pipelines.templates.TemplateResponse", side_effect=Exception("boom")),
            patch("app.views.pipelines.logger") as mock_logger,
        ):
            client.get("/pipelines")
        mock_logger.error.assert_called_once()
        log_message = mock_logger.error.call_args.args[0]
        assert "Error loading pipelines page" in log_message

    def test_router_has_pipelines_route(self):
        """The pipelines router exposes the /pipelines GET route."""
        from app.views.pipelines import router

        routes = {route.path for route in router.routes}
        assert "/pipelines" in routes

    def test_pipelines_page_passes_app_version_to_template(self, client):
        """The app_version value from settings is forwarded to the template context."""
        from app.config import settings

        response = client.get("/pipelines")
        assert response.status_code == 200
        version_bytes = settings.version.encode()
        assert version_bytes in response.content
