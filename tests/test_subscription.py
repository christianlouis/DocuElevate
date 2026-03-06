"""Unit tests for the subscription tier utility module."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, date

from app.utils.subscription import (
    TIERS,
    TIER_ORDER,
    DEFAULT_TIER,
    get_tier,
    get_all_tiers,
    get_user_tier_id,
    get_user_usage,
    check_upload_allowed,
    QuotaExceeded,
    get_lifetime_file_count,
    get_today_file_count,
    get_month_file_count,
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
        "id", "name", "tagline", "price_monthly", "price_yearly",
        "trial_days",
        "lifetime_file_limit", "daily_upload_limit", "monthly_upload_limit",
        "max_storage_destinations", "max_ocr_pages_monthly", "max_file_size_mb",
        "max_mailboxes",
        "features", "cta",
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
    """Business tier must have the highest limits of all paid tiers."""
    t = TIERS["business"]
    # lifetime, daily, monthly: no hard cap (0 = unlimited) for lifetime; daily/monthly capped
    assert t["lifetime_file_limit"] == 0
    assert t["daily_upload_limit"] == 30
    assert t["monthly_upload_limit"] == 300
    assert t["max_ocr_pages_monthly"] == 1500
    # unlimited mailboxes
    assert t["max_mailboxes"] == 0


@pytest.mark.unit
def test_mailbox_limits_increase_by_tier():
    """Mailbox limits must increase across tiers: free=0, starter=1, professional=3, business=0(∞)."""
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
    """Paid tier prices must increase in order: starter < professional < business."""
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
    """Free tier: should raise QuotaExceeded when lifetime limit (50) is hit."""
    db = MagicMock()

    with patch("app.utils.subscription.get_lifetime_file_count", return_value=50):
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "free")

    assert exc_info.value.limit_type == "lifetime"
    assert exc_info.value.limit_value == 50
    assert exc_info.value.current_value == 50


@pytest.mark.unit
def test_check_upload_passes_below_lifetime_limit():
    db = MagicMock()
    with patch("app.utils.subscription.get_lifetime_file_count", return_value=10):
        check_upload_allowed(db, "user@example.com", "free")  # must not raise


@pytest.mark.unit
def test_check_upload_raises_when_daily_exceeded():
    """Starter tier: should raise QuotaExceeded when daily limit (5) is hit."""
    db = MagicMock()

    with patch("app.utils.subscription.get_lifetime_file_count", return_value=0), \
         patch("app.utils.subscription.get_today_file_count", return_value=5):
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "starter")

    assert exc_info.value.limit_type == "daily"


@pytest.mark.unit
def test_check_upload_raises_when_monthly_exceeded():
    """Starter tier: should raise QuotaExceeded when monthly limit (50) is hit."""
    db = MagicMock()

    with patch("app.utils.subscription.get_lifetime_file_count", return_value=0), \
         patch("app.utils.subscription.get_today_file_count", return_value=0), \
         patch("app.utils.subscription.get_month_file_count", return_value=50):
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "starter")

    assert exc_info.value.limit_type == "monthly"


@pytest.mark.unit
def test_check_upload_business_tier_within_limits():
    """Business tier: upload is allowed as long as counts are below the capped limits."""
    db = MagicMock()
    # Use counts well below Business limits (30/day, 300/mo)
    with patch("app.utils.subscription.get_lifetime_file_count", return_value=0), \
         patch("app.utils.subscription.get_today_file_count", return_value=10), \
         patch("app.utils.subscription.get_month_file_count", return_value=100):
        check_upload_allowed(db, "user@example.com", "business")  # must not raise


@pytest.mark.unit
def test_check_upload_business_tier_raises_when_daily_exceeded():
    """Business tier: should raise QuotaExceeded when daily limit (30) is hit."""
    db = MagicMock()

    with patch("app.utils.subscription.get_lifetime_file_count", return_value=0), \
         patch("app.utils.subscription.get_today_file_count", return_value=30):
        with pytest.raises(QuotaExceeded) as exc_info:
            check_upload_allowed(db, "user@example.com", "business")

    assert exc_info.value.limit_type == "daily"
    assert exc_info.value.limit_value == 30


# ---------------------------------------------------------------------------
# get_user_usage (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_user_usage_returns_dict_with_correct_keys():
    db = MagicMock()
    with patch("app.utils.subscription.get_lifetime_file_count", return_value=10), \
         patch("app.utils.subscription.get_today_file_count", return_value=2), \
         patch("app.utils.subscription.get_month_file_count", return_value=8):
        result = get_user_usage(db, "user@example.com")

    assert result == {"lifetime": 10, "today": 2, "month": 8}


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
