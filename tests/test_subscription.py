"""Unit tests for the subscription tier utility module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.utils.subscription import (
    DEFAULT_TIER,
    TIER_DEFAULTS,
    TIER_ORDER,
    TIERS,
    QuotaExceeded,
    _months_elapsed,
    check_upload_allowed,
    get_all_tiers,
    get_tier,
    get_user_tier_id,
    get_user_usage,
)

# ---------------------------------------------------------------------------
# Basic catalogue tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_tiers_present():
    """All four tier IDs must exist."""
    for tid in ["free", "starter", "professional", "business"]:
        assert tid in TIERS, f"Missing tier: {tid}"


@pytest.mark.unit
def test_tier_order_is_complete():
    """TIER_ORDER must contain exactly the four expected tiers."""
    assert set(TIER_ORDER) == set(TIERS.keys())
    assert len(TIER_ORDER) == 4


@pytest.mark.unit
def test_default_tier_is_free():
    assert DEFAULT_TIER == "free"


@pytest.mark.unit
def test_get_tier_returns_correct_dict():
    t = get_tier("starter")
    assert t["id"] == "starter"
    assert t["price_monthly"] == 2.99


@pytest.mark.unit
def test_get_tier_fallback_for_unknown():
    """Unknown tier ID should fall back to free."""
    t = get_tier("nonexistent_tier")
    assert t["id"] == "free"


@pytest.mark.unit
def test_get_all_tiers_returns_four():
    tiers = get_all_tiers()
    assert len(tiers) == 4


@pytest.mark.unit
def test_all_tiers_have_required_fields():
    required = [
        "id",
        "name",
        "tagline",
        "price_monthly",
        "price_yearly",
        "trial_days",
        "lifetime_file_limit",
        "daily_upload_limit",
        "monthly_upload_limit",
        "max_storage_destinations",
        "max_ocr_pages_monthly",
        "max_file_size_mb",
        "max_mailboxes",
        "features",
        "cta",
    ]
    for tid, tier in TIERS.items():
        for field in required:
            assert field in tier, f"Tier '{tid}' missing field '{field}'"


@pytest.mark.unit
def test_free_tier_has_lifetime_limit():
    """Free tier must have a non-zero lifetime file limit of 50."""
    assert TIERS["free"]["lifetime_file_limit"] == 50


@pytest.mark.unit
def test_free_tier_ocr_pages():
    """Free tier must have 150 OCR pages."""
    assert TIERS["free"]["max_ocr_pages_monthly"] == 150


@pytest.mark.unit
def test_free_tier_has_no_mailboxes():
    """Free tier must not allow email ingestion mailboxes."""
    assert TIERS["free"]["max_mailboxes"] == 0


@pytest.mark.unit
def test_business_tier_has_highest_limits():
    """Power tier (plan_id 'business') must have the highest limits of all paid tiers."""
    t = TIERS["business"]
    # lifetime: no hard cap (0 = unlimited)
    assert t["lifetime_file_limit"] == 0
    # no daily cap (0 = unlimited)
    assert t["daily_upload_limit"] == 0
    assert t["monthly_upload_limit"] == 300
    assert t["max_ocr_pages_monthly"] == 1500
    # unlimited mailboxes (0 = unlimited)
    assert t["max_mailboxes"] == 0
    # unlimited file size (0 = unlimited)
    assert t["max_file_size_mb"] == 0


@pytest.mark.unit
def test_business_tier_display_name_is_power():
    """The 'business' plan_id must display as 'Power'."""
    assert TIERS["business"]["name"] == "Power"


@pytest.mark.unit
def test_mailbox_limits_increase_by_tier():
    """Mailbox limits must increase across tiers: free=0, starter=1, professional=3, power/business=0(inf)."""
    assert TIERS["free"]["max_mailboxes"] == 0
    assert TIERS["starter"]["max_mailboxes"] == 1
    assert TIERS["professional"]["max_mailboxes"] == 3
    assert TIERS["business"]["max_mailboxes"] == 0  # 0 means unlimited


@pytest.mark.unit
def test_paid_tiers_have_trial_days():
    """All paid tiers must have a 30-day free trial."""
    for tid in ["starter", "professional", "business"]:
        assert TIERS[tid]["trial_days"] == 30, f"Tier '{tid}' missing 30-day trial"


@pytest.mark.unit
def test_free_tier_has_no_trial():
    assert TIERS["free"]["trial_days"] == 0


@pytest.mark.unit
def test_pricing_order():
    """Paid tier prices must increase in order: starter < professional < power."""
    assert TIERS["starter"]["price_monthly"] < TIERS["professional"]["price_monthly"]
    assert TIERS["professional"]["price_monthly"] < TIERS["business"]["price_monthly"]


# ---------------------------------------------------------------------------
# get_user_tier_id tests (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_user_tier_id_returns_default_when_no_owner():
    db = MagicMock()
    assert get_user_tier_id(db, None) == DEFAULT_TIER


@pytest.mark.unit
def test_get_user_tier_id_returns_profile_tier():
    db = MagicMock()
    profile = MagicMock()
    profile.subscription_tier = "professional"
    db.query.return_value.filter.return_value.first.return_value = profile
    assert get_user_tier_id(db, "user@example.com") == "professional"


@pytest.mark.unit
def test_get_user_tier_id_falls_back_to_free_when_no_profile():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert get_user_tier_id(db, "unknown@example.com") == "free"


@pytest.mark.unit
def test_get_user_tier_id_falls_back_when_tier_is_none():
    db = MagicMock()
    profile = MagicMock()
    profile.subscription_tier = None
    db.query.return_value.filter.return_value.first.return_value = profile
    assert get_user_tier_id(db, "user@example.com") == "free"


# ---------------------------------------------------------------------------
# check_upload_allowed tests (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_upload_skipped_without_owner():
    """check_upload_allowed should not raise when owner_id is None."""
    db = MagicMock()
    check_upload_allowed(db, None, "free")  # must not raise


@pytest.mark.unit
def test_check_upload_skipped_without_tier():
    """check_upload_allowed should not raise when tier_id is None."""
    db = MagicMock()
    check_upload_allowed(db, "user@example.com", None)  # must not raise


@pytest.mark.unit
def test_check_upload_raises_when_lifetime_exceeded():
    """Free tier: raise QuotaExceeded at lifetime limit (50) with 0% buffer (exact enforcement)."""
    db = MagicMock()
    # Return None for both SubscriptionPlan lookup and UserProfile lookup
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=50),
    ):
        mock_settings.subscription_overage_percent = 0
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "free")

    assert exc_info.value.limit_type == "lifetime"
    assert exc_info.value.limit_value == 50
    assert exc_info.value.current_value == 50


@pytest.mark.unit
def test_check_upload_passes_below_lifetime_limit():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=10),
    ):
        mock_settings.subscription_overage_percent = 0
        check_upload_allowed(db, "user@example.com", "free")  # must not raise


@pytest.mark.unit
def test_check_upload_raises_when_monthly_exceeded():
    """Starter tier: raise QuotaExceeded when monthly limit (50) is hit (0% buffer)."""
    db = MagicMock()

    # UserProfile mock: no overage, monthly billing, no period_start
    profile_mock = MagicMock()
    profile_mock.allow_overage = False
    profile_mock.subscription_billing_cycle = "monthly"
    profile_mock.subscription_period_start = None
    db.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_month_file_count", return_value=50),
    ):
        mock_settings.subscription_overage_percent = 0
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "starter")

    assert exc_info.value.limit_type == "monthly"


@pytest.mark.unit
def test_check_upload_business_tier_within_limits():
    """Business tier: upload is allowed when count is below the monthly limit."""
    db = MagicMock()
    profile_mock = MagicMock()
    profile_mock.allow_overage = False
    profile_mock.subscription_billing_cycle = "monthly"
    profile_mock.subscription_period_start = None
    db.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_month_file_count", return_value=100),
    ):
        mock_settings.subscription_overage_percent = 0
        check_upload_allowed(db, "user@example.com", "business")  # must not raise


# ---------------------------------------------------------------------------
# Overage buffer tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_overage_percent_allows_buffer():
    """Starter monthly=50, 20% buffer -> enforce at 60. count=55 should pass, count=61 should raise."""
    profile_mock = MagicMock()
    profile_mock.allow_overage = False
    profile_mock.subscription_billing_cycle = "monthly"
    profile_mock.subscription_period_start = None

    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_month_file_count", return_value=55),
    ):
        mock_settings.subscription_overage_percent = 20
        # count=55 < 60 (50*1.20) -> should NOT raise
        check_upload_allowed(db, "user@example.com", "starter")

    # Reset mock for second call
    db2 = MagicMock()
    db2.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_month_file_count", return_value=61),
    ):
        mock_settings.subscription_overage_percent = 20
        # count=61 >= 60 -> should raise
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db2, "user@example.com", "starter")
    assert exc_info.value.limit_type == "monthly"
    assert exc_info.value.limit_value == 50


@pytest.mark.unit
def test_allow_overage_flag_bypasses_monthly_limit():
    """When allow_overage=True on UserProfile, monthly cap is never enforced."""
    db = MagicMock()
    profile_mock = MagicMock()
    profile_mock.allow_overage = True
    profile_mock.subscription_billing_cycle = "monthly"
    profile_mock.subscription_period_start = None
    db.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_month_file_count", return_value=999999),
    ):
        mock_settings.subscription_overage_percent = 0
        # Should NOT raise even with enormous count
        check_upload_allowed(db, "user@example.com", "starter")


@pytest.mark.unit
def test_yearly_carryover_allows_accumulated_budget():
    """Yearly billing carry-over: period_start 2 months ago, monthly=50 (0% buffer).
    Budget = 50 * months_elapsed. used=80 should pass; used at budget+1 should raise.
    """
    db = MagicMock()
    profile_mock = MagicMock()
    profile_mock.allow_overage = False
    profile_mock.subscription_billing_cycle = "yearly"
    now = datetime.now(timezone.utc)
    # period_start is 2 months before current month
    if now.month > 2:
        period_start = now.replace(month=now.month - 2, day=1)
    else:
        period_start = now.replace(year=now.year - 1, month=now.month + 10, day=1)
    profile_mock.subscription_period_start = period_start
    db.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    # months_elapsed with period 2 months ago = 3 (prev-prev, prev, current)
    # budget = 50 * 3 = 150 with 0% buffer
    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_year_file_count", return_value=80),
    ):
        mock_settings.subscription_overage_percent = 0
        # 80 < 150 -> should NOT raise
        check_upload_allowed(db, "user@example.com", "starter")

    # Reset mock for second call
    db2 = MagicMock()
    db2.query.return_value.filter.return_value.first.side_effect = [None, profile_mock]

    with (
        patch("app.utils.subscription.settings") as mock_settings,
        patch("app.utils.subscription.get_lifetime_file_count", return_value=0),
        patch("app.utils.subscription.get_year_file_count", return_value=151),
    ):
        mock_settings.subscription_overage_percent = 0
        # 151 >= 150 -> should raise
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db2, "user@example.com", "starter")
    assert exc_info.value.limit_type == "monthly"


# ---------------------------------------------------------------------------
# _months_elapsed helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_months_elapsed_same_month():
    now = datetime(2025, 6, 15, tzinfo=timezone.utc)
    start = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert _months_elapsed(start, now) == 1


@pytest.mark.unit
def test_months_elapsed_two_months():
    now = datetime(2025, 8, 1, tzinfo=timezone.utc)
    start = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert _months_elapsed(start, now) == 3  # June, July, August = 3


@pytest.mark.unit
def test_months_elapsed_clamped_to_12():
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert _months_elapsed(start, now) == 12


# ---------------------------------------------------------------------------
# get_user_usage (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_user_usage_returns_dict_with_correct_keys():
    db = MagicMock()
    # No profile -> monthly billing, no period_start
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.utils.subscription.get_lifetime_file_count", return_value=10),
        patch("app.utils.subscription.get_today_file_count", return_value=2),
        patch("app.utils.subscription.get_month_file_count", return_value=8),
    ):
        result = get_user_usage(db, "user@example.com")

    assert result == {"lifetime": 10, "today": 2, "month": 8}


@pytest.mark.unit
def test_get_user_usage_includes_year_to_date_for_yearly():
    """Yearly subscriber gets year_to_date key in usage dict."""
    db = MagicMock()
    profile_mock = MagicMock()
    profile_mock.subscription_billing_cycle = "yearly"
    period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile_mock.subscription_period_start = period_start
    db.query.return_value.filter.return_value.first.return_value = profile_mock

    with (
        patch("app.utils.subscription.get_lifetime_file_count", return_value=10),
        patch("app.utils.subscription.get_today_file_count", return_value=2),
        patch("app.utils.subscription.get_month_file_count", return_value=8),
        patch("app.utils.subscription.get_year_file_count", return_value=40),
    ):
        result = get_user_usage(db, "user@example.com")

    assert "year_to_date" in result
    assert result["year_to_date"] == 40


# ---------------------------------------------------------------------------
# TIERS / TIER_DEFAULTS alias
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tiers_is_alias_for_tier_defaults():
    """TIERS must be the same object as TIER_DEFAULTS (backward compat alias)."""
    assert TIERS is TIER_DEFAULTS


# ---------------------------------------------------------------------------
# API: /api/subscriptions/tiers (integration-style, mocked app)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_tiers_api(client):
    """GET /api/subscriptions/tiers must return all four tiers."""
    resp = client.get("/api/subscriptions/tiers")
    assert resp.status_code == 200
    data = resp.json()
    assert "tiers" in data
    assert len(data["tiers"]) == 4
    ids = [t["id"] for t in data["tiers"]]
    assert "free" in ids
    assert "starter" in ids
    assert "professional" in ids
    assert "business" in ids
