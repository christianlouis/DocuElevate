"""
Admin API endpoints for managing scheduled batch processing jobs.

All endpoints require admin privileges (checked via session ``is_admin`` flag).

Available routes:
    GET  /api/admin/scheduled-jobs         – list all scheduled jobs
    PATCH /api/admin/scheduled-jobs/{id}   – update schedule / enable-disable
    POST /api/admin/scheduled-jobs/{id}/run-now – trigger a job immediately
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScheduledJob

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/scheduled-jobs", tags=["admin-scheduled-jobs"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Authorisation helper
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin; raises HTTP 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ScheduledJobResponse(BaseModel):
    """Read model for a scheduled job."""

    id: int
    name: str
    display_name: str
    description: str | None
    task_name: str
    enabled: bool
    schedule_type: str
    cron_minute: str
    cron_hour: str
    cron_day_of_week: str
    cron_day_of_month: str
    cron_month_of_year: str
    interval_seconds: int | None
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_detail: str | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ScheduledJobUpdate(BaseModel):
    """Writable fields for a scheduled job update (all optional)."""

    enabled: bool | None = Field(None, description="Whether the job is active")
    schedule_type: str | None = Field(None, pattern="^(cron|interval)$", description="'cron' or 'interval'")
    cron_minute: str | None = Field(None, max_length=50)
    cron_hour: str | None = Field(None, max_length=50)
    cron_day_of_week: str | None = Field(None, max_length=50)
    cron_day_of_month: str | None = Field(None, max_length=50)
    cron_month_of_year: str | None = Field(None, max_length=50)
    interval_seconds: int | None = Field(None, ge=60, description="Interval in seconds (min 60)")


# ---------------------------------------------------------------------------
# Default job definitions – seeded into the DB on first startup
# ---------------------------------------------------------------------------

DEFAULT_JOBS: list[dict[str, Any]] = [
    {
        "name": "process-new-documents",
        "display_name": "Process New Documents",
        "description": (
            "Scans for documents that have been uploaded but never processed "
            "and queues them through the full processing pipeline. "
            "Runs hourly by default."
        ),
        "task_name": "app.tasks.batch_tasks.process_new_documents",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "0",
        "cron_hour": "*/1",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "reprocess-failed-documents",
        "display_name": "Reprocess Failed Documents",
        "description": (
            "Finds documents whose last processing attempt failed and re-queues "
            "them for reprocessing. Only picks up files that are not currently "
            "being processed. Runs every 6 hours by default."
        ),
        "task_name": "app.tasks.batch_tasks.reprocess_failed_documents",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "30",
        "cron_hour": "*/6",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "cleanup-temp-files",
        "display_name": "Clean Up Temporary Files",
        "description": (
            "Removes stale files from the workdir/tmp directory. "
            "Only files older than 24 hours that are not referenced by any active "
            "processing job are deleted. Runs daily at 03:30 UTC by default."
        ),
        "task_name": "app.tasks.batch_tasks.cleanup_temp_files",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "30",
        "cron_hour": "3",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "expire-shared-links",
        "display_name": "Expire Stale Shared Links",
        "description": (
            "Marks shared document links as inactive when their expiry time has passed. "
            "Access is already blocked at request time, but this task keeps the "
            "management UI counts accurate. Runs daily at 01:00 UTC by default."
        ),
        "task_name": "app.tasks.batch_tasks.expire_shared_links",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "0",
        "cron_hour": "1",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "prune-processing-logs",
        "display_name": "Prune Old Processing Logs",
        "description": (
            "Deletes processing log entries and settings audit log entries older than "
            "30 days to prevent unbounded database growth. "
            "Runs weekly on Sunday at 04:00 UTC by default."
        ),
        "task_name": "app.tasks.batch_tasks.prune_processing_logs",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "0",
        "cron_hour": "4",
        "cron_day_of_week": "0",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "prune-old-notifications",
        "display_name": "Prune Old Notifications",
        "description": (
            "Deletes read in-app notifications older than 30 days. "
            "Unread notifications are never deleted. "
            "Runs weekly on Sunday at 04:30 UTC by default."
        ),
        "task_name": "app.tasks.batch_tasks.prune_old_notifications",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "30",
        "cron_hour": "4",
        "cron_day_of_week": "0",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "backfill-missing-metadata",
        "display_name": "Backfill Missing AI Metadata",
        "description": (
            "Re-triggers AI metadata extraction for documents that have extracted "
            "text but no AI metadata yet (e.g., processed before an AI provider "
            "was configured). Processes up to 50 documents per run. "
            "Runs every 6 hours by default."
        ),
        "task_name": "app.tasks.batch_tasks.backfill_missing_metadata",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "0",
        "cron_hour": "*/6",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
    {
        "name": "sync-search-index",
        "display_name": "Sync Search Index",
        "description": (
            "Indexes documents that have OCR text or AI metadata but are missing "
            "from the Meilisearch search index. Useful after enabling search on "
            "an existing installation or after an index rebuild. "
            "Processes up to 100 documents per run. "
            "Runs hourly by default."
        ),
        "task_name": "app.tasks.batch_tasks.sync_search_index",
        "enabled": True,
        "schedule_type": "cron",
        "cron_minute": "15",
        "cron_hour": "*/1",
        "cron_day_of_week": "*",
        "cron_day_of_month": "*",
        "cron_month_of_year": "*",
        "interval_seconds": None,
    },
]


def seed_default_scheduled_jobs(db: Session) -> None:
    """
    Insert the built-in scheduled jobs if they do not already exist.

    Called from the FastAPI lifespan handler so the records are available
    immediately after the first startup.
    """
    for job_data in DEFAULT_JOBS:
        existing = db.query(ScheduledJob).filter(ScheduledJob.name == job_data["name"]).first()
        if existing is None:
            db.add(ScheduledJob(**job_data))
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to seed default scheduled jobs: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ScheduledJobResponse])
def list_scheduled_jobs(request: Request, db: DbSession, _admin: AdminUser) -> list[ScheduledJobResponse]:
    """
    Return all scheduled jobs ordered by display name.

    Requires admin privileges.
    """
    jobs = db.query(ScheduledJob).order_by(ScheduledJob.display_name).all()
    return jobs  # type: ignore[return-value]


@router.patch("/{job_id}", response_model=ScheduledJobResponse)
def update_scheduled_job(
    job_id: int,
    payload: ScheduledJobUpdate,
    request: Request,
    db: DbSession,
    _admin: AdminUser,
) -> ScheduledJobResponse:
    """
    Update schedule configuration or enabled state for a job.

    Only the fields included in the request body are modified.
    Changes to the Celery Beat schedule take effect after the worker restarts.

    Requires admin privileges.
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")

    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    for field, value in update_data.items():
        setattr(job, field, value)

    job.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(job)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to update scheduled job %s: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update scheduled job",
        ) from exc

    logger.info("Admin updated scheduled job %s (id=%s): %s", job.name, job_id, update_data)
    return job  # type: ignore[return-value]


@router.post("/{job_id}/run-now")
def run_scheduled_job_now(
    job_id: int,
    request: Request,
    db: DbSession,
    _admin: AdminUser,
) -> dict[str, Any]:
    """
    Immediately dispatch the Celery task for the given scheduled job.

    The task is sent to the default queue; its result is tracked asynchronously
    via the ``last_run_at`` / ``last_run_status`` fields updated by the task
    itself.

    Requires admin privileges.
    """
    job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")

    from app.celery_app import celery as celery_app

    task = celery_app.send_task(job.task_name)
    logger.info("Admin triggered scheduled job %s (id=%s) manually, task_id=%s", job.name, job_id, task.id)

    return {
        "status": "dispatched",
        "job_id": job_id,
        "job_name": job.name,
        "task_id": task.id,
    }
