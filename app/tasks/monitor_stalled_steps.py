"""
Periodic task to detect and recover from stalled processing steps.

This task runs periodically (every minute by default) to find any processing steps
that have been stuck in "in_progress" state for too long and mark them as failed.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError

from app.celery_app import celery
from app.database import SessionLocal
from app.utils.step_timeout import mark_stalled_steps_as_failed

logger = logging.getLogger(__name__)

_MAX_DB_ATTEMPTS = 3


def _is_transient_disconnect(error: OperationalError) -> bool:
    """Return whether a database error may succeed on a fresh connection."""
    if getattr(error, "connection_invalidated", False):
        return True
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "bad record mac",
            "connection reset",
            "connection refused",
            "server closed",
            "unexpected eof",
            "ssl connection has been closed",
            "could not receive data",
        )
    )


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
    for attempt in range(1, _MAX_DB_ATTEMPTS + 1):
        try:
            with SessionLocal() as db:
                try:
                    stalled_count = mark_stalled_steps_as_failed(db)
                except Exception:
                    # Keep rollback in the live session context.  If rollback
                    # fails, the original database exception remains primary.
                    try:
                        db.rollback()
                    except Exception:
                        logger.exception("Could not roll back stalled-step monitor session")
                    raise

            # This log is deliberately outside the session context: the
            # utility emits per-step success logs only after its commit too.
            if stalled_count > 0:
                logger.warning(
                    f"[{datetime.now(timezone.utc).isoformat()}] "
                    f"Recovered {stalled_count} stalled step(s). "
                    f"Marked as failed due to timeout."
                )
            else:
                logger.debug(f"[{datetime.now(timezone.utc).isoformat()}] No stalled steps found.")
            return {"recovered": stalled_count}
        except OperationalError as error:
            if not _is_transient_disconnect(error) or attempt == _MAX_DB_ATTEMPTS:
                logger.error("Error in monitor_stalled_steps task: %s", error, exc_info=True)
                raise
            delay = min(2 ** (attempt - 1), 4)
            logger.warning(
                "Transient database disconnect in monitor_stalled_steps; retrying with a fresh session "
                "(attempt %s/%s, delay=%ss)",
                attempt + 1,
                _MAX_DB_ATTEMPTS,
                delay,
            )
            time.sleep(delay)
        except Exception as error:
            logger.error("Error in monitor_stalled_steps task: %s", error, exc_info=True)
            raise
