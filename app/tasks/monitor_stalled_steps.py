"""
Periodic task to detect and recover from stalled processing steps.

This task runs periodically (every minute by default) to find any processing steps
that have been stuck in "in_progress" state for too long and mark them as failed.
"""

import logging
from datetime import datetime

from app.celery_app import celery
from app.database import SessionLocal
from app.utils.step_timeout import mark_stalled_steps_as_failed

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.monitor_stalled_steps.monitor_stalled_steps")
def monitor_stalled_steps():
    """
    Periodic task to detect and mark stalled processing steps as failed.

    This task:
    1. Connects to the database
    2. Finds any in-progress steps that exceeded the timeout
    3. Marks them as failed with a timeout error message
    4. Logs the recovery action

    This helps prevent files from getting stuck in "pending" state when
    processing crashes or hangs without proper error handling.

    Scheduled to run every minute via Celery Beat.
    """
    try:
        with SessionLocal() as db:
            stalled_count = mark_stalled_steps_as_failed(db)

            if stalled_count > 0:
                logger.warning(
                    f"[{datetime.utcnow().isoformat()}] "
                    f"Recovered {stalled_count} stalled step(s). "
                    f"Marked as failed due to timeout."
                )
            else:
                logger.debug(f"[{datetime.utcnow().isoformat()}] " f"No stalled steps found.")

            return {"recovered": stalled_count}

    except Exception as e:
        logger.error(f"Error in monitor_stalled_steps task: {e}", exc_info=True)
        return {"error": str(e), "recovered": 0}
