"""
Processing logs API endpoints
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import FileRecord, ProcessingLog
from app.utils.input_validation import validate_task_id

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/logs")
@require_login
def list_processing_logs(
    request: Request,
    db: DbSession,
    file_id: Optional[int] = Query(None, description="Filter by file ID"),
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
):
    """
    Returns a JSON list of ProcessingLog entries.
    Protected by `@require_login`, so only logged-in sessions can access.

    Query Parameters:
    - file_id: Optional filter by file ID
    - task_id: Optional filter by task ID
    - limit: Maximum number of logs to return (default 100, max 1000)

    Example response:
    [
      {
        "id": 1,
        "file_id": 123,
        "task_id": "abc-123-def",
        "step_name": "process_document",
        "status": "success",
        "message": "Processing completed",
        "timestamp": "2025-05-01T12:34:56.789000"
      },
      ...
    ]
    """
    query = db.query(ProcessingLog)

    # Apply filters
    if file_id is not None:
        query = query.filter(ProcessingLog.file_id == file_id)
    if task_id is not None:
        validate_task_id(task_id)
        query = query.filter(ProcessingLog.task_id == task_id)

    # Order by timestamp descending and limit
    logs = query.order_by(desc(ProcessingLog.timestamp)).limit(limit).all()

    # Return a simple list of dicts
    result = []
    for log in logs:
        result.append(
            {
                "id": log.id,
                "file_id": log.file_id,
                "task_id": log.task_id,
                "step_name": log.step_name,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
        )
    return result


@router.get("/logs/file/{file_id}")
@require_login
def get_file_processing_logs(request: Request, file_id: int, db: DbSession):
    """
    Get all processing logs for a specific file.
    Returns logs ordered by timestamp (oldest first to show processing flow).

    Also includes file metadata if the file exists.
    """
    # Check if file exists
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")

    # Get all logs for this file
    logs = db.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).order_by(ProcessingLog.timestamp).all()

    # Build response
    log_list = []
    for log in logs:
        log_list.append(
            {
                "id": log.id,
                "task_id": log.task_id,
                "step_name": log.step_name,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
        )

    return {
        "file": {
            "id": file_record.id,
            "original_filename": file_record.original_filename,
            "file_size": file_record.file_size,
            "mime_type": file_record.mime_type,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
        },
        "logs": log_list,
        "total_logs": len(log_list),
    }


@router.get("/logs/task/{task_id}")
@require_login
def get_task_processing_logs(request: Request, task_id: str, db: DbSession):
    """
    Get all processing logs for a specific task.
    Returns logs ordered by timestamp (oldest first to show processing flow).
    """
    validate_task_id(task_id)
    # Get all logs for this task
    logs = db.query(ProcessingLog).filter(ProcessingLog.task_id == task_id).order_by(ProcessingLog.timestamp).all()

    if not logs:
        raise HTTPException(status_code=404, detail=f"No logs found for task {task_id}")

    # Build response
    log_list = []
    for log in logs:
        log_list.append(
            {
                "id": log.id,
                "file_id": log.file_id,
                "step_name": log.step_name,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            }
        )

    return {"task_id": task_id, "logs": log_list, "total_logs": len(log_list)}
