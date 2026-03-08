"""Tests for app/views/subscriptions.py module.

Covers:
  GET /pricing          — public marketing pricing page
  GET /subscription     — authenticated user's current plan & usage
"""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Integration tests (via TestClient with shared fixtures)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPricingView:
    """Integration tests for the /pricing route."""

    def test_pricing_page_returns_200(self, client):
        """GET /pricing should return 200."""
        response = client.get("/pricing")
        assert response.status_code == 200

    def test_pricing_page_contains_html(self, client):
        """GET /pricing should return HTML content."""
        response = client.get("/pricing")
        assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()

    def test_pricing_page_contains_tier_info(self, client):
        """GET /pricing should include tier/plan information."""
        response = client.get("/pricing")
        assert response.status_code == 200
        # Pricing page should mention plan names
        content = response.text
        assert "Free" in content or "Starter" in content or "pricing" in content.lower()


@pytest.mark.integration
class TestSubscriptionView:
    """Integration tests for the /subscription route."""

    def test_subscription_page_accessible_when_auth_disabled(self, client):
        """GET /subscription should return 200 when AUTH_ENABLED=False (test default)."""
        response = client.get("/subscription", follow_redirects=False)
        # AUTH_ENABLED=False in tests so require_login is a no-op
        assert response.status_code == 200

    def test_subscription_page_returns_html(self, client):
        """GET /subscription should return HTML content."""
        response = client.get("/subscription")
        assert response.status_code == 200
        assert b"<html" in response.content.lower() or b"<!doctype" in response.content.lower()

    def test_subscription_page_contains_subscription_content(self, client):
        """GET /subscription should include subscription-related content."""
        response = client.get("/subscription")
        assert response.status_code == 200
        content = response.text
        # Page should mention subscription or plan
        assert "subscription" in content.lower() or "plan" in content.lower()


# ---------------------------------------------------------------------------
# Unit tests (call view functions directly with mocked dependencies)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPricingPageUnit:
    """Unit tests for the pricing_page view function."""

    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_pricing_page_calls_get_all_tiers(self, mock_templates, mock_get_all_tiers):
        """pricing_page should call get_all_tiers with the db session."""
        from app.views.subscriptions import pricing_page

        mock_tiers = [{"id": "free"}, {"id": "starter"}]
        mock_get_all_tiers.return_value = mock_tiers
        mock_request = MagicMock()
        mock_db = MagicMock()

        await pricing_page(mock_request, mock_db)

        mock_get_all_tiers.assert_called_once_with(mock_db)

    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_pricing_page_renders_correct_template(self, mock_templates, mock_get_all_tiers):
        """pricing_page should render pricing.html."""
        from app.views.subscriptions import pricing_page

        mock_get_all_tiers.return_value = []
        mock_request = MagicMock()
        mock_db = MagicMock()

        await pricing_page(mock_request, mock_db)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "pricing.html"

    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_pricing_page_passes_tiers_to_template(self, mock_templates, mock_get_all_tiers):
        """pricing_page should pass tiers and tier_order to the template context."""
        from app.views.subscriptions import TIER_ORDER, pricing_page

        mock_tiers = [{"id": "free"}, {"id": "starter"}]
        mock_get_all_tiers.return_value = mock_tiers
        mock_request = MagicMock()
        mock_db = MagicMock()

        await pricing_page(mock_request, mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["tiers"] == mock_tiers
        assert context["tier_order"] == TIER_ORDER
        assert context["request"] is mock_request


@pytest.mark.unit
class TestMySubscriptionPageUnit:
    """Unit tests for the my_subscription_page view function."""

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_no_multi_user_no_owner(self, mock_templates, mock_get_all_tiers, mock_get_tier):
        """When multi_user_enabled=False, should use 'business' tier with no usage."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_tier = {"id": "business"}
        mock_get_tier.return_value = mock_tier

        mock_request = MagicMock()
        mock_request.session = {}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "subscription.html"
        context = call_args[0][1]
        assert context["tier_id"] == "business"
        assert context["usage"] is None
        assert context["pending_tier_id"] is None
        assert context["pending_date"] is None
        assert context["period_start"] is None

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_multi_user_no_owner_id(self, mock_templates, mock_get_all_tiers, mock_get_tier):
        """When multi_user_enabled=True but owner_id is empty, should fall back to else branch."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        # Session has a user but none of the owner_id fields are set
        mock_request.session = {"user": {}}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # Falls through to else branch because owner_id is ""
        assert context["tier_id"] == "business"
        assert context["usage"] is None

    @patch("app.views.subscriptions.apply_pending_subscription_changes")
    @patch("app.views.subscriptions.get_user_usage")
    @patch("app.views.subscriptions.get_user_tier_id")
    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_multi_user_with_profile(
        self,
        mock_templates,
        mock_get_all_tiers,
        mock_get_tier,
        mock_get_tier_id,
        mock_get_usage,
        mock_apply_pending,
    ):
        """When multi_user_enabled=True with owner_id and a profile, should load from DB."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "starter"}
        mock_get_tier_id.return_value = "starter"
        mock_usage = {"lifetime": 10, "monthly": 5}
        mock_get_usage.return_value = mock_usage

        # Create a mock profile with pending subscription fields
        mock_profile = MagicMock()
        mock_profile.subscription_change_pending_tier = "professional"
        mock_profile.subscription_change_pending_date = "2025-12-01"
        mock_profile.subscription_period_start = "2025-01-01"

        mock_request = MagicMock()
        mock_request.session = {"user": {"username": "testuser"}}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            await my_subscription_page(request=mock_request, db=mock_db)

        mock_apply_pending.assert_called_once_with(mock_db, "testuser")
        mock_get_tier_id.assert_called_once_with(mock_db, "testuser")
        mock_get_usage.assert_called_once_with(mock_db, "testuser")

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["tier_id"] == "starter"
        assert context["usage"] == mock_usage
        assert context["pending_tier_id"] == "professional"
        assert context["pending_date"] == "2025-12-01"
        assert context["period_start"] == "2025-01-01"
        assert context["owner_id"] == "testuser"

    @patch("app.views.subscriptions.apply_pending_subscription_changes")
    @patch("app.views.subscriptions.get_user_usage")
    @patch("app.views.subscriptions.get_user_tier_id")
    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_multi_user_no_profile(
        self,
        mock_templates,
        mock_get_all_tiers,
        mock_get_tier,
        mock_get_tier_id,
        mock_get_usage,
        mock_apply_pending,
    ):
        """When multi_user_enabled=True with owner_id but no profile, pending fields should be None."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "free"}
        mock_get_tier_id.return_value = "free"
        mock_get_usage.return_value = {"lifetime": 0, "monthly": 0}

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com"}}
        mock_db = MagicMock()
        # No profile found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["pending_tier_id"] is None
        assert context["pending_date"] is None
        assert context["period_start"] is None
        assert context["owner_id"] == "user@example.com"

    @patch("app.views.subscriptions.apply_pending_subscription_changes")
    @patch("app.views.subscriptions.get_user_usage")
    @patch("app.views.subscriptions.get_user_tier_id")
    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_pending_tier_id_resolves_tier(
        self,
        mock_templates,
        mock_get_all_tiers,
        mock_get_tier,
        mock_get_tier_id,
        mock_get_usage,
        mock_apply_pending,
    ):
        """When pending_tier_id is set, get_tier should be called for it."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier_id.return_value = "starter"
        mock_get_usage.return_value = {}

        mock_current_tier = {"id": "starter"}
        mock_pending_tier = {"id": "professional"}
        # get_tier is called twice: once for current tier, once for pending tier
        mock_get_tier.side_effect = [mock_current_tier, mock_pending_tier]

        mock_profile = MagicMock()
        mock_profile.subscription_change_pending_tier = "professional"
        mock_profile.subscription_change_pending_date = "2025-12-01"
        mock_profile.subscription_period_start = "2025-01-01"

        mock_request = MagicMock()
        mock_request.session = {"user": {"sub": "user-sub-123"}}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["pending_tier"] == mock_pending_tier
        assert context["pending_tier_id"] == "professional"

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_no_pending_tier_id(self, mock_templates, mock_get_all_tiers, mock_get_tier):
        """When pending_tier_id is None, pending_tier should be None."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        mock_request.session = {}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["pending_tier"] is None

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_template_context_has_required_fields(
        self, mock_templates, mock_get_all_tiers, mock_get_tier
    ):
        """subscription.html context must include all required fields."""
        from app.views.subscriptions import TIER_ORDER, my_subscription_page

        mock_get_all_tiers.return_value = [{"id": "free"}]
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        mock_request.session = {}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        assert call_args[0][0] == "subscription.html"
        context = call_args[0][1]
        required_keys = [
            "request",
            "tier",
            "tier_id",
            "usage",
            "all_tiers",
            "multi_user_enabled",
            "owner_id",
            "tier_order",
            "pending_tier_id",
            "pending_tier",
            "pending_date",
            "period_start",
        ]
        for key in required_keys:
            assert key in context, f"Missing context key: {key}"
        assert context["tier_order"] == TIER_ORDER

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_owner_id_resolved_from_username(
        self, mock_templates, mock_get_all_tiers, mock_get_tier
    ):
        """owner_id should be resolved from session user.username first."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        mock_request.session = {"user": {"username": "alice", "email": "alice@example.com", "sub": "sub-1"}}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        # username takes priority
        assert context["owner_id"] == "alice"

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_owner_id_resolved_from_email(
        self, mock_templates, mock_get_all_tiers, mock_get_tier
    ):
        """owner_id should fall back to session user.email when username is absent."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "bob@example.com", "sub": "sub-2"}}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["owner_id"] == "bob@example.com"

    @patch("app.views.subscriptions.get_tier")
    @patch("app.views.subscriptions.get_all_tiers")
    @patch("app.views.subscriptions.templates")
    @pytest.mark.asyncio
    async def test_subscription_page_owner_id_resolved_from_sub(
        self, mock_templates, mock_get_all_tiers, mock_get_tier
    ):
        """owner_id should fall back to session user.sub when username and email are absent."""
        from app.views.subscriptions import my_subscription_page

        mock_get_all_tiers.return_value = []
        mock_get_tier.return_value = {"id": "business"}

        mock_request = MagicMock()
        mock_request.session = {"user": {"sub": "sub-3"}}
        mock_db = MagicMock()

        with patch("app.config.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            await my_subscription_page(request=mock_request, db=mock_db)

        call_args = mock_templates.TemplateResponse.call_args
        context = call_args[0][1]
        assert context["owner_id"] == "sub-3"
