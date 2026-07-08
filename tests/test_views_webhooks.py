"""Tests for the admin webhook management view."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.responses import RedirectResponse


@pytest.mark.unit
class TestWebhooksDashboardView:
    """Unit tests for the /admin/webhooks page handler."""

    @pytest.mark.asyncio
    async def test_returns_template_for_admin(self):
        """Admin users can open the webhook management dashboard."""
        from app.views.webhooks import webhooks_dashboard

        request = MagicMock()
        request.session = {"user": {"email": "admin@example.com", "is_admin": True}}
        response = MagicMock()

        with patch("app.views.webhooks.templates") as templates:
            templates.TemplateResponse.return_value = response
            result = await webhooks_dashboard(request)

        assert result is response
        templates.TemplateResponse.assert_called_once()
        template_name, context = templates.TemplateResponse.call_args[0]
        assert template_name == "webhooks_dashboard.html"
        assert context["request"] is request
        assert context["page_title"] == "Webhooks"

    @pytest.mark.asyncio
    async def test_redirects_non_admin_to_home(self):
        """Non-admin users cannot open the webhook management dashboard."""
        from app.views.webhooks import webhooks_dashboard

        request = MagicMock()
        request.session = {"user": {"email": "user@example.com", "is_admin": False}}

        result = await webhooks_dashboard(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"


@pytest.mark.unit
def test_template_contains_endpoint_secret_and_replay_controls():
    """The page exposes endpoint, secret, event, and replay controls."""
    from pathlib import Path

    template = Path("frontend/templates/webhooks_dashboard.html").read_text()

    assert "webhook-url" in template
    assert "webhook-secret" in template
    assert "/api/webhooks/events/" in template
    assert "/api/webhooks/delivery-attempts/" in template
    assert "replay" in template
