"""Celery task to apply pending subscription changes that have become due.

Runs daily to ensure that scheduled downgrades are applied on time.
"""

import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.subscription_tasks.apply_pending_subscription_changes_all")
def apply_pending_subscription_changes_all() -> dict[str, int]:
    """Apply all pending subscription changes whose effective date has arrived.

    Iterates over every ``UserProfile`` that has a pending change and calls
    :func:`app.utils.subscription.apply_pending_subscription_changes` for
    each one.

    Returns:
        A dict with ``{"applied": <count>, "checked": <count>}``.
    """
    from app.database import SessionLocal
    from app.models import UserProfile
    from app.utils.subscription import apply_pending_subscription_changes

    db = SessionLocal()
    applied = 0
    checked = 0
    try:
        profiles = (
            db.query(UserProfile)
            .filter(
                UserProfile.subscription_change_pending_tier.isnot(None),
                UserProfile.subscription_change_pending_date.isnot(None),
            )
            .all()
        )
        for profile in profiles:
            checked += 1
            if apply_pending_subscription_changes(db, profile.user_id):
                applied += 1
    except Exception as exc:
        logger.error("Error in apply_pending_subscription_changes_all: %s", exc)
    finally:
        db.close()

    logger.info("apply_pending_subscription_changes_all: checked=%d applied=%d", checked, applied)
    return {"checked": checked, "applied": applied}
