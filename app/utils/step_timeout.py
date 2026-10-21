"""
Step timeout detection and handling.

Monitors in-progress steps and marks them as failed if they exceed a timeout threshold.
This prevents files from getting stuck in "pending" state when processing crashes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FileProcessingStep

logger = logging.getLogger(__name__)

# Default timeout for a step (in seconds)
DEFAULT_STEP_TIMEOUT = 600  # 10 minutes


def get_step_timeout() -> int:
    """
    Get the step timeout configuration from settings.

    Returns:
        Timeout in seconds (default: 600 seconds / 10 minutes)
    """
    # Could be made configurable via settings in the future
    return getattr(settings, "step_timeout", DEFAULT_STEP_TIMEOUT)


def mark_stalled_steps_as_failed(
    db: Session, timeout_seconds: Optional[int] = None, file_id: Optional[int] = None
) -> int:
    """
    Find and mark any in-progress steps that have exceeded the timeout as failed.

    This function:
    1. Queries for all in-progress steps
    2. Checks if they've been running longer than the timeout
    3. Marks them as failed with a timeout error message
    4. Sets their completed_at timestamp

    Args:
        db: SQLAlchemy session
        timeout_seconds: Timeout duration in seconds (default: from settings)
        file_id: Optional file ID to check only that file's steps

    Returns:
        Number of steps marked as failed
    """
    if timeout_seconds is None:
        timeout_seconds = get_step_timeout()

    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(seconds=timeout_seconds)

    # Query for stalled steps
    query = db.query(FileProcessingStep).filter(
        FileProcessingStep.status == "in_progress",
        FileProcessingStep.started_at <= cutoff_time,  # Started before cutoff
        FileProcessingStep.started_at.isnot(None),  # Has a start time
    )

    if file_id is not None:
        query = query.filter(FileProcessingStep.file_id == file_id)

    # Prevent two beat workers from recovering the same row concurrently.
    # PostgreSQL skips rows already claimed by another worker; databases that
    # do not support row locks keep their normal query behavior.
    query = query.with_for_update(skip_locked=True)

    stalled_steps = query.all()

    if not stalled_steps:
        return 0

    logger.warning(
        f"Found {len(stalled_steps)} stalled step(s) that exceeded {timeout_seconds}s timeout. Marking as failed."
    )

    count = 0
    recovered_steps = []
    for step in stalled_steps:
        step.status = "failure"
        step.completed_at = now
        step.error_message = (
            f"Step timeout after {timeout_seconds} seconds. "
            f"Processing did not complete. Started at {step.started_at}, "
            f"timeout triggered at {now}."
        )
        count += 1
        recovered_steps.append((step.file_id, step.step_name, step.started_at))

    db.commit()

    # A commit can fail after the in-memory objects were changed.  Emit these
    # success records only after the transaction has been durably persisted.
    for recovered_file_id, step_name, started_at in recovered_steps:
        logger.error(
            f"[File {recovered_file_id}] Step '{step_name}' marked as failed due to timeout. "
            f"Started: {started_at}, Timeout at: {now}"
        )

    return count


def check_and_recover_stalled_file(db: Session, file_id: int) -> bool:
    """
    Check if a specific file has stalled steps and recover by marking them as failed.

    Args:
        db: SQLAlchemy session
        file_id: File ID to check

    Returns:
        True if stalled steps were found and marked as failed, False otherwise
    """
    count = mark_stalled_steps_as_failed(db, file_id=file_id)
    return count > 0
