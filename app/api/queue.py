"""
Queue monitoring API endpoints.

Provides endpoints to query Celery/Redis queue statistics and
database-level processing status for document pipeline visibility.
"""

import logging
from typing import Any

import redis
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import FileProcessingStep, FileRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/queue", tags=["queue"])


def _get_redis_queue_length(redis_client: redis.Redis, queue_name: str) -> int:
    """Get the number of messages in a Redis-backed Celery queue.

    Args:
        redis_client: Connected Redis client instance.
        queue_name: Name of the Celery queue to inspect.

    Returns:
        Number of messages (tasks) waiting in the queue.
    """
    try:
        return redis_client.llen(queue_name)
    except Exception:
        logger.debug(f"Could not read queue length for '{queue_name}'")
        return 0


def _get_celery_inspect_stats() -> dict[str, Any]:
    """Query the Celery inspect API for active, reserved, and scheduled tasks.

    Returns:
        Dictionary with active, reserved, and scheduled task summaries.
    """
    from app.celery_app import celery

    result: dict[str, Any] = {
        "active": [],
        "reserved": [],
        "scheduled": [],
        "workers_online": 0,
    }

    try:
        inspector = celery.control.inspect(timeout=2.0)

        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}

        result["workers_online"] = len(active)

        for _worker, tasks in active.items():
            for task in tasks:
                result["active"].append(
                    {
                        "id": task.get("id", ""),
                        "name": task.get("name", "unknown"),
                        "args": str(task.get("args", []))[:200],
                        "started": task.get("time_start"),
                    }
                )

        for _worker, tasks in reserved.items():
            for task in tasks:
                result["reserved"].append(
                    {
                        "id": task.get("id", ""),
                        "name": task.get("name", "unknown"),
                        "args": str(task.get("args", []))[:200],
                    }
                )

        for _worker, tasks in scheduled.items():
            for task in tasks:
                req = task.get("request", {})
                result["scheduled"].append(
                    {
                        "id": req.get("id", ""),
                        "name": req.get("name", "unknown"),
                        "eta": task.get("eta"),
                    }
                )
    except Exception as exc:
        logger.warning(f"Celery inspect failed (workers may be offline): {exc}")

    return result


def _get_db_processing_summary(db: Session) -> dict[str, Any]:
    """Query the database for a summary of file processing states.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Dictionary with counts of files by processing state.
    """
    try:
        total_files = db.query(func.count(FileRecord.id)).scalar() or 0

        # Count files with at least one in_progress step
        processing_count = (
            db.query(func.count(func.distinct(FileProcessingStep.file_id)))
            .filter(FileProcessingStep.status == "in_progress")
            .scalar()
            or 0
        )

        # Count files with at least one failure and no in_progress
        failed_subq = (
            db.query(FileProcessingStep.file_id).filter(FileProcessingStep.status == "failure").distinct().subquery()
        )
        in_progress_subq = (
            db.query(FileProcessingStep.file_id)
            .filter(FileProcessingStep.status == "in_progress")
            .distinct()
            .subquery()
        )
        failed_count = (
            db.query(func.count(func.distinct(failed_subq.c.file_id)))
            .filter(~failed_subq.c.file_id.in_(db.query(in_progress_subq.c.file_id)))
            .scalar()
            or 0
        )

        # Count files that have steps and all steps are success/skipped
        all_step_files = db.query(FileProcessingStep.file_id).distinct().subquery()
        # Files with any non-terminal step
        non_terminal = (
            db.query(FileProcessingStep.file_id)
            .filter(FileProcessingStep.status.in_(["in_progress", "pending", "failure"]))
            .distinct()
            .subquery()
        )
        completed_count = (
            db.query(func.count(func.distinct(all_step_files.c.file_id)))
            .filter(~all_step_files.c.file_id.in_(db.query(non_terminal.c.file_id)))
            .scalar()
            or 0
        )

        # Files with no processing steps at all
        files_with_steps = db.query(FileProcessingStep.file_id).distinct().subquery()
        pending_count = (
            db.query(func.count(FileRecord.id))
            .filter(~FileRecord.id.in_(db.query(files_with_steps.c.file_id)))
            .filter(FileRecord.is_duplicate.is_(False))
            .scalar()
            or 0
        )

        # Recent files being processed (last 20 in_progress or pending)
        recent_processing = (
            db.query(FileRecord.id, FileRecord.original_filename, FileProcessingStep.step_name)
            .join(FileProcessingStep, FileRecord.id == FileProcessingStep.file_id)
            .filter(FileProcessingStep.status == "in_progress")
            .order_by(FileProcessingStep.updated_at.desc())
            .limit(20)
            .all()
        )

        recent_list = [
            {"file_id": r[0], "filename": r[1] or f"File #{r[0]}", "current_step": r[2]} for r in recent_processing
        ]

        return {
            "total_files": total_files,
            "processing": processing_count,
            "failed": failed_count,
            "completed": completed_count,
            "pending": pending_count,
            "recent_processing": recent_list,
        }
    except Exception as exc:
        logger.error(f"Error querying DB processing summary: {exc}")
        return {
            "total_files": 0,
            "processing": 0,
            "failed": 0,
            "completed": 0,
            "pending": 0,
            "recent_processing": [],
        }


@router.get("/stats")
def get_queue_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Get comprehensive queue and processing statistics.

    Returns queue lengths from Redis, Celery worker inspection data,
    and database-level processing summaries for the document pipeline.

    Returns:
        Dictionary containing redis queue info, celery worker info,
        and database processing summary.
    """
    # 1. Redis queue lengths
    queue_lengths: dict[str, int] = {}
    try:
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        for queue_name in ["document_processor", "default", "celery"]:
            queue_lengths[queue_name] = _get_redis_queue_length(redis_client, queue_name)
        redis_client.close()
    except Exception as exc:
        logger.warning(f"Could not connect to Redis: {exc}")

    total_queued = sum(queue_lengths.values())

    # 2. Celery inspect
    celery_stats = _get_celery_inspect_stats()

    # 3. DB summary
    db_summary = _get_db_processing_summary(db)

    return {
        "queues": queue_lengths,
        "total_queued": total_queued,
        "celery": celery_stats,
        "db_summary": db_summary,
    }


@router.get("/pending-count")
def get_pending_count(db: Session = Depends(get_db)) -> dict[str, int]:
    """Get a lightweight count of queued + in-progress items for the files page banner.

    Returns:
        Dictionary with total_pending count (queued in Redis + processing in DB).
    """
    total_pending = 0

    # Redis queue lengths
    try:
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        for queue_name in ["document_processor", "default", "celery"]:
            total_pending += _get_redis_queue_length(redis_client, queue_name)
        redis_client.close()
    except Exception:
        logger.debug("Could not connect to Redis for pending count")

    # DB in-progress count
    try:
        processing_count = (
            db.query(func.count(func.distinct(FileProcessingStep.file_id)))
            .filter(FileProcessingStep.status == "in_progress")
            .scalar()
            or 0
        )
        total_pending += processing_count
    except Exception:
        logger.debug("Could not query DB for processing count")

    return {"total_pending": total_pending}
