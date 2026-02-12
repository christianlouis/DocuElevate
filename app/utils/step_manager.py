"""
Utility functions for managing file processing step status.

This module provides functions to initialize, update, and query the status
of file processing steps using the FileProcessingStep model.
"""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import FileProcessingStep, FileRecord

# Define the expected processing steps for a standard file workflow
# The "check_for_duplicates" step is conditionally included based on enable_deduplication setting
BASE_MAIN_PROCESSING_STEPS = [
    "create_file_record",
    "check_text",
    "extract_text",  # Or "process_with_azure_document_intelligence"
    "extract_metadata_with_gpt",
    "embed_metadata_into_pdf",
    "finalize_document_storage",
    "send_to_all_destinations",
]

OPTIONAL_PROCESSING_STEPS = {
    "check_for_duplicates": settings.enable_deduplication,  # Only if deduplication is enabled
}

# Combine steps based on configuration
MAIN_PROCESSING_STEPS = []
if settings.enable_deduplication:
    MAIN_PROCESSING_STEPS.append("check_for_duplicates")
MAIN_PROCESSING_STEPS.extend(BASE_MAIN_PROCESSING_STEPS)


def initialize_file_steps(db: Session, file_id: int, include_uploads: bool = False) -> None:
    """
    Initialize processing steps for a file with 'pending' status.

    Args:
        db: Database session
        file_id: ID of the file
        include_uploads: Whether to include upload destination steps (set after destinations are known)
    """
    # Initialize main processing steps
    for step_name in MAIN_PROCESSING_STEPS:
        step = FileProcessingStep(file_id=file_id, step_name=step_name, status="pending")
        db.add(step)

    db.commit()


def add_upload_steps(db: Session, file_id: int, upload_destinations: List[str]) -> None:
    """
    Add upload destination steps for a file.

    Args:
        db: Database session
        file_id: ID of the file
        upload_destinations: List of upload destination names (e.g., ["dropbox", "s3", "nextcloud"])
    """
    for destination in upload_destinations:
        # Add both queue and upload steps for each destination
        for prefix in ["queue_", "upload_to_"]:
            step_name = f"{prefix}{destination}"
            # Check if step already exists
            existing = (
                db.query(FileProcessingStep)
                .filter(FileProcessingStep.file_id == file_id, FileProcessingStep.step_name == step_name)
                .first()
            )
            if not existing:
                step = FileProcessingStep(file_id=file_id, step_name=step_name, status="pending")
                db.add(step)

    db.commit()


def update_step_status(
    db: Session,
    file_id: int,
    step_name: str,
    status: str,
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> None:
    """
    Update the status of a processing step.

    Args:
        db: Database session
        file_id: ID of the file
        step_name: Name of the processing step
        status: New status ("pending", "in_progress", "success", "failure", "skipped")
        error_message: Error message if status is "failure"
        started_at: When the step started (for "in_progress")
        completed_at: When the step completed (for "success" or "failure")
    """
    step = (
        db.query(FileProcessingStep)
        .filter(FileProcessingStep.file_id == file_id, FileProcessingStep.step_name == step_name)
        .first()
    )

    if not step:
        # Create the step if it doesn't exist
        step = FileProcessingStep(
            file_id=file_id,
            step_name=step_name,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )
        db.add(step)
    else:
        # Update existing step
        step.status = status
        if error_message is not None:
            step.error_message = error_message
        if started_at is not None:
            step.started_at = started_at
        if completed_at is not None:
            step.completed_at = completed_at

    db.commit()


def get_file_step_status(db: Session, file_id: int) -> Dict[str, Dict]:
    """
    Get the current status of all processing steps for a file.

    Args:
        db: Database session
        file_id: ID of the file

    Returns:
        Dictionary mapping step_name to status info:
        {
            "step_name": {
                "status": "success",
                "started_at": datetime,
                "completed_at": datetime,
                "error_message": None
            },
            ...
        }
    """
    steps = db.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_id).all()

    result = {}
    for step in steps:
        result[step.step_name] = {
            "status": step.status,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "error_message": step.error_message,
        }

    return result


def get_file_overall_status(db: Session, file_id: int) -> Dict:
    """
    Get the overall processing status for a file based on its steps.

    Only considers "real" processing steps that represent user-facing status.
    Ignores diagnostic/internal steps like poll_task, upload_file, etc.

    Args:
        db: Database session
        file_id: ID of the file

    Returns:
        Dictionary with overall status info:
        {
            "status": "completed",  # "pending", "processing", "completed", "failed"
            "has_errors": False,
            "total_steps": 10,
            "completed_steps": 8,
            "failed_steps": 0,
            "in_progress_steps": 2
        }
    """
    # If file is marked as duplicate, return duplicate status immediately
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).one_or_none()
    if file_record and file_record.is_duplicate:
        return {
            "status": "duplicate",
            "has_errors": False,
            "total_steps": 0,
            "completed_steps": 0,
            "failed_steps": 0,
            "in_progress_steps": 0,
            "skipped_steps": 0,
        }

    # Define which steps are "real" status-determining steps
    # Only high-level logical steps, not implementation sub-steps
    REAL_MAIN_STEPS = {
        "create_file_record",
        "check_text",
        "extract_text",
        "process_with_azure_document_intelligence",
        "extract_metadata_with_gpt",
        "embed_metadata_into_pdf",
        "finalize_document_storage",
        "send_to_all_destinations",
    }

    # Add check_for_duplicates if deduplication is enabled
    if settings.enable_deduplication:
        REAL_MAIN_STEPS.add("check_for_duplicates")

    all_steps = db.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_id).all()

    # Filter to only real steps
    steps = [
        s
        for s in all_steps
        if s.step_name in REAL_MAIN_STEPS or s.step_name.startswith("queue_") or s.step_name.startswith("upload_to_")
    ]

    if not steps:
        return {
            "status": "pending",
            "has_errors": False,
            "total_steps": 0,
            "completed_steps": 0,
            "failed_steps": 0,
            "in_progress_steps": 0,
        }

    total_steps = len(steps)
    completed_steps = sum(1 for s in steps if s.status == "success")
    failed_steps = sum(1 for s in steps if s.status == "failure")
    in_progress_steps = sum(1 for s in steps if s.status == "in_progress")
    skipped_steps = sum(1 for s in steps if s.status == "skipped")

    has_errors = failed_steps > 0

    # Determine overall status
    if has_errors:
        status = "failed"
    elif in_progress_steps > 0:
        status = "processing"
    elif completed_steps + skipped_steps == total_steps:
        status = "completed"
    else:
        status = "pending"

    return {
        "status": status,
        "has_errors": has_errors,
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "in_progress_steps": in_progress_steps,
        "skipped_steps": skipped_steps,
    }


def get_step_summary(db: Session, file_id: int) -> Dict:
    """
    Get a summary of main steps vs upload steps with status counts.

    Only counts "real" processing steps that represent user-facing status.
    Ignores diagnostic/internal steps like poll_task, upload_file, etc.

    Args:
        db: Database session
        file_id: ID of the file

    Returns:
        Dictionary with step counts:
        {
            "main": {"queued": 0, "in_progress": 1, "success": 7, "failure": 0, "skipped": 0},
            "uploads": {"queued": 2, "in_progress": 0, "success": 4, "failure": 0, "skipped": 0},
            "total_main_steps": 8,
            "total_upload_tasks": 6
        }
    """
    # Define which steps are "real" status-determining steps
    # Only high-level logical steps, not implementation sub-steps
    REAL_MAIN_STEPS = {
        "create_file_record",
        "check_text",
        "extract_text",
        "process_with_azure_document_intelligence",
        "extract_metadata_with_gpt",
        "embed_metadata_into_pdf",
        "finalize_document_storage",
        "send_to_all_destinations",
    }

    # Add check_for_duplicates if deduplication is enabled
    if settings.enable_deduplication:
        REAL_MAIN_STEPS.add("check_for_duplicates")

    steps = db.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_id).all()

    main_counts = {"queued": 0, "in_progress": 0, "success": 0, "failure": 0, "skipped": 0}
    upload_counts = {"queued": 0, "in_progress": 0, "success": 0, "failure": 0, "skipped": 0}

    main_steps_count = 0
    upload_steps_count = 0

    for step in steps:
        # Normalize status
        status = step.status.lower()
        if status == "pending":
            status = "queued"

        # Check if it's an upload task (only count actual upload_to_* steps, not queue_* steps)
        is_upload = step.step_name.startswith("upload_to_")

        # Only count "real" steps
        is_real_step = step.step_name in REAL_MAIN_STEPS or is_upload or step.step_name.startswith("queue_")

        if not is_real_step:
            # Skip diagnostic/internal steps like poll_task, upload_file, set_custom_fields, etc.
            continue

        if is_upload:
            if status in upload_counts:
                upload_counts[status] += 1
            upload_steps_count += 1
        elif step.step_name in REAL_MAIN_STEPS:
            if status in main_counts:
                main_counts[status] += 1
            main_steps_count += 1

    return {
        "main": main_counts,
        "uploads": upload_counts,
        "total_main_steps": main_steps_count,
        "total_upload_tasks": upload_steps_count,
    }
