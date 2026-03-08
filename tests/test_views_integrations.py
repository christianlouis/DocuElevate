"""Tests for app/views/integrations.py — the unified integrations dashboard.

Covers the /integrations view route, quota rendering, and unit-level
helpers for subscription-tier limits.
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Integration tests — real HTTP round-trips via the TestClient
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIntegrationsDashboardView:
    """Integration tests for the GET /integrations view route."""

    def test_integrations_page_returns_200(self, client):
        """GET /integrations returns HTTP 200."""
        response = client.get("/integrations")
        assert response.status_code == 200

    def test_integrations_page_renders_html(self, client):
        """GET /integrations returns HTML content with a proper html tag."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"<html" in response.content.lower()

    def test_integrations_page_contains_title(self, client):
        """GET /integrations response contains the page title."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"Integrations" in response.content

    def test_integrations_page_content_type_is_html(self, client):
        """GET /integrations response has HTML content-type."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_integrations_route_is_registered(self, client):
        """GET /integrations must not return 405 Method Not Allowed."""
        response = client.get("/integrations", follow_redirects=False)
        assert response.status_code != 405

    def test_integrations_page_contains_plug_icon(self, client):
        """GET /integrations page contains the integrations plug icon class."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"fa-plug" in response.content

    def test_integrations_page_contains_add_button(self, client):
        """GET /integrations response references an add-integration button."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"Add Integration" in response.content

    def test_integrations_page_contains_alpine_app(self, client):
        """GET /integrations response includes the Alpine.js app component."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"integrationsDashboard" in response.content

    def test_integrations_page_contains_quota_indicators(self, client):
        """GET /integrations page includes quota labels."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"Mailbox Sources" in response.content
        assert b"Storage Destinations" in response.content

    def test_integrations_page_contains_upgrade_plan_link(self, client):
        """GET /integrations page includes an upgrade plan CTA."""
        response = client.get("/integrations")
        assert response.status_code == 200
        assert b"Upgrade Plan" in response.content


# ---------------------------------------------------------------------------
# Unit tests — helpers and edge-cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIntegrationsDashboardUnit:
    """Unit tests for app/views/integrations.py helpers."""

    def test_get_max_destinations_free_tier(self):
        """Free tier returns the configured max or safe default 1."""
        from app.views.integrations import _get_max_destinations

        tier = {"id": "free", "max_storage_destinations": 2}
        assert _get_max_destinations(tier) == 2

    def test_get_max_destinations_free_tier_zero(self):
        """Free tier with max_storage_destinations=0 returns safe default 1."""
        from app.views.integrations import _get_max_destinations

        tier = {"id": "free", "max_storage_destinations": 0}
        assert _get_max_destinations(tier) == 1

    def test_get_max_destinations_paid_unlimited(self):
        """Paid tier with 0 means unlimited (None)."""
        from app.views.integrations import _get_max_destinations

        tier = {"id": "business", "max_storage_destinations": 0}
        assert _get_max_destinations(tier) is None

    def test_get_max_destinations_paid_limited(self):
        """Paid tier with positive value returns that limit."""
        from app.views.integrations import _get_max_destinations

        tier = {"id": "starter", "max_storage_destinations": 5}
        assert _get_max_destinations(tier) == 5

    def test_get_max_sources_free_tier(self):
        """Free tier always returns 0 (no access)."""
        from app.views.integrations import _get_max_sources

        tier = {"id": "free", "max_mailboxes": 0}
        assert _get_max_sources(tier) == 0

    def test_get_max_sources_paid_unlimited(self):
        """Paid tier with max_mailboxes=0 means unlimited (None)."""
        from app.views.integrations import _get_max_sources

        tier = {"id": "business", "max_mailboxes": 0}
        assert _get_max_sources(tier) is None

    def test_get_max_sources_paid_limited(self):
        """Paid tier with positive value returns that limit."""
        from app.views.integrations import _get_max_sources

        tier = {"id": "starter", "max_mailboxes": 3}
        assert _get_max_sources(tier) == 3

    def test_page_error_returns_500(self, client):
        """When template rendering raises an exception, GET /integrations returns HTTP 500."""
        with patch(
            "app.views.integrations.templates.TemplateResponse",
            side_effect=Exception("render error"),
        ):
            response = client.get("/integrations")
        assert response.status_code == 500

    def test_page_error_returns_html_500(self, client):
        """HTTP 500 response from the non-API /integrations route returns an HTML page."""
        with patch(
            "app.views.integrations.templates.TemplateResponse",
            side_effect=Exception("render error"),
        ):
            response = client.get("/integrations")
        assert response.status_code == 500
        assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_page_context_contains_quota_data(self):
        """Verify the view passes quota data to the template context."""
        from app.views.integrations import integrations_dashboard

        mock_request = MagicMock()
        mock_request.session = {"user": {"id": "test-user"}}
        mock_db = MagicMock()

        with (
            patch("app.views.integrations.get_current_owner_id", return_value=None),
            patch("app.views.integrations.templates") as mock_templates,
        ):
            mock_templates.TemplateResponse = MagicMock()
            await integrations_dashboard(request=mock_request, db=mock_db)
            call_args = mock_templates.TemplateResponse.call_args
            ctx = call_args[0][1]
            assert "dest_count" in ctx
            assert "src_count" in ctx
            assert "max_destinations" in ctx
            assert "max_sources" in ctx
            assert "can_add_destination" in ctx
            assert "can_add_source" in ctx
            assert "tier_name" in ctx
