"""
File management views for displaying and managing files.
"""

from fastapi import Request, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.views.base import APIRouter, templates, require_login, get_db, logger
from app.utils.file_status import get_files_processing_status
from app.config import settings

router = APIRouter()


@router.get("/files")
@require_login
def files_page(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    search: Optional[str] = Query(None),
    mime_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """
    Return the 'files.html' template with server-side pagination, sorting, and filtering
    """
    try:
        # Import the model here to avoid circular imports
        from app.models import FileRecord, ProcessingLog
        from sqlalchemy import desc, asc, or_

        # Start with base query
        query = db.query(FileRecord)

        # Apply search filter
        if search:
            query = query.filter(FileRecord.original_filename.ilike(f"%{search}%"))

        # Apply MIME type filter
        if mime_type:
            query = query.filter(FileRecord.mime_type == mime_type)

        # Apply status filter (before pagination for correct counts)
        if status:
            # Subquery to get file IDs matching the status
            if status == "pending":
                # Files with no logs
                subq = db.query(ProcessingLog.file_id).distinct()
                query = query.filter(~FileRecord.id.in_(subq))
            elif status == "processing":
                # Files with in_progress logs
                subq = db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "in_progress").distinct()
                query = query.filter(FileRecord.id.in_(subq))
            elif status == "failed":
                # Files with failure logs
                subq = db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "failure").distinct()
                query = query.filter(FileRecord.id.in_(subq))
            elif status == "completed":
                # Files with success logs but no failures or in_progress
                success_files = (
                    db.query(ProcessingLog.file_id).filter(ProcessingLog.status == "success").distinct().subquery()
                )

                failed_files = (
                    db.query(ProcessingLog.file_id)
                    .filter(or_(ProcessingLog.status == "failure", ProcessingLog.status == "in_progress"))
                    .distinct()
                    .subquery()
                )

                query = query.filter(FileRecord.id.in_(db.query(success_files.c.file_id))).filter(
                    ~FileRecord.id.in_(db.query(failed_files.c.file_id))
                )

        # Get total count before pagination
        total_items = query.count()

        # Apply sorting
        sort_column = {
            "id": FileRecord.id,
            "original_filename": FileRecord.original_filename,
            "file_size": FileRecord.file_size,
            "mime_type": FileRecord.mime_type,
            "created_at": FileRecord.created_at,
        }.get(sort_by, FileRecord.created_at)

        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        # Apply pagination
        offset = (page - 1) * per_page
        files = query.offset(offset).limit(per_page).all()

        # Get processing status for all files efficiently (avoids N+1)
        file_ids = [f.id for f in files]
        statuses = get_files_processing_status(db, file_ids)

        # Add status to each file
        files_with_status = []
        for file in files:
            file.processing_status = statuses.get(file.id, {}).get("status", "pending")
            files_with_status.append(file)

        # Calculate pagination info
        total_pages = (total_items + per_page - 1) // per_page

        # Get unique MIME types for filter dropdown
        mime_types = db.query(FileRecord.mime_type).distinct().filter(FileRecord.mime_type.isnot(None)).all()
        mime_types = [mt[0] for mt in mime_types if mt[0]]

        # Debug output
        logger.info(f"Retrieved {len(files_with_status)} files from database (page {page}/{total_pages})")

        return templates.TemplateResponse(
            "files.html",
            {
                "request": request,
                "files": files_with_status,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_items": total_items,
                    "total_pages": total_pages,
                },
                "sort_by": sort_by,
                "sort_order": sort_order,
                "search": search or "",
                "mime_type": mime_type or "",
                "status": status or "",
                "mime_types": mime_types,
            },
        )
    except Exception as e:
        # Log any errors
        logger.error(f"Error retrieving files: {str(e)}")
        # Return error message to template
        return templates.TemplateResponse(
            "files.html",
            {
                "request": request,
                "files": [],
                "pagination": {"page": 1, "per_page": per_page, "total_items": 0, "total_pages": 0},
                "error": str(e),
            },
        )


@router.get("/files/{file_id}/detail")
@require_login
def file_detail_page(request: Request, file_id: int, db: Session = Depends(get_db)):
    """
    Return the file detail page showing processing history and file information
    """
    try:
        from app.models import FileRecord, ProcessingLog
        import os

        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()

        if not file_record:
            return templates.TemplateResponse(
                "file_detail.html", {"request": request, "file": None, "error": f"File with ID {file_id} not found"}
            )

        # Get processing logs
        logs = (
            db.query(ProcessingLog)
            .filter(ProcessingLog.file_id == file_id)
            .order_by(ProcessingLog.timestamp.asc())
            .all()
        )

        # Check if file exists on disk
        file_exists = os.path.exists(file_record.local_filename) if file_record.local_filename else False

        # Check if processed file exists
        processed_exists = False
        workdir = settings.workdir
        processed_dir = os.path.join(workdir, "processed")
        if os.path.exists(processed_dir):
            base_filename = os.path.splitext(file_record.original_filename)[0]
            potential_paths = [
                os.path.join(processed_dir, f"{file_record.filehash}.pdf"),
                os.path.join(processed_dir, f"{base_filename}_processed.pdf"),
                os.path.join(processed_dir, file_record.original_filename),
            ]
            for path in potential_paths:
                if os.path.exists(path):
                    processed_exists = True
                    break

        # Compute processing flow for visualization
        flow_data = _compute_processing_flow(logs)

        # Compute step-aligned summary
        step_summary = _compute_step_summary(logs)

        return templates.TemplateResponse(
            "file_detail.html",
            {
                "request": request,
                "file": file_record,
                "logs": logs,
                "file_exists": file_exists,
                "processed_exists": processed_exists,
                "flow_data": flow_data,
                "step_summary": step_summary,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving file details: {str(e)}")
        return templates.TemplateResponse("file_detail.html", {"request": request, "file": None, "error": str(e)})


def _compute_processing_flow(logs):
    """
    Compute the processing flow structure from logs for visualization.

    Returns a structured representation of the processing pipeline with branches.
    Detects upload sub-tasks and organizes them as branches under the parent upload stage.
    """
    # Define the main processing stages
    stages = {
        "hash_file": {"label": "File Upload & Hash", "next": ["create_file_record"]},
        "create_file_record": {"label": "Create File Record", "next": ["check_text"]},
        "check_text": {
            "label": "Check Embedded Text",
            "next": ["extract_text", "process_with_azure_document_intelligence"],
        },
        "extract_text": {"label": "Extract Text (Local)", "next": ["extract_metadata_with_gpt"]},
        "process_with_azure_document_intelligence": {
            "label": "OCR Processing (Azure)",
            "next": ["extract_metadata_with_gpt"],
        },
        "extract_metadata_with_gpt": {"label": "Extract Metadata (GPT)", "next": ["embed_metadata_into_pdf"]},
        "embed_metadata_into_pdf": {"label": "Embed Metadata into PDF", "next": ["finalize_document_storage"]},
        "finalize_document_storage": {"label": "Finalize & Queue Distribution", "next": ["send_to_all_destinations"]},
        "send_to_all_destinations": {"label": "Upload to Destinations", "next": [], "has_branches": True},
    }

    # Define upload sub-tasks (branches)
    upload_tasks = {
        "upload_to_dropbox": "Dropbox",
        "upload_to_nextcloud": "Nextcloud",
        "upload_to_paperless": "Paperless-ngx",
        "upload_to_google_drive": "Google Drive",
        "upload_to_onedrive": "OneDrive",
        "upload_to_s3": "S3 Storage",
        "upload_to_webdav": "WebDAV",
        "upload_to_ftp": "FTP Storage",
        "upload_to_sftp": "SFTP Storage",
        "upload_to_email": "Email",
        "queue_dropbox": "Dropbox",
        "queue_nextcloud": "Nextcloud",
        "queue_paperless": "Paperless-ngx",
        "queue_google_drive": "Google Drive",
        "queue_onedrive": "OneDrive",
        "queue_s3": "S3 Storage",
        "queue_webdav": "WebDAV",
        "queue_ftp": "FTP Storage",
        "queue_sftp": "SFTP Storage",
        "queue_email": "Email",
    }

    # Create a map of step names to their log entries
    step_map = {}
    upload_branches = {}

    for log in logs:
        step_name = log.step_name

        # Check if this is an upload sub-task
        if step_name in upload_tasks:
            # Extract the actual upload task name (remove queue_ prefix if present)
            upload_key = step_name.replace("queue_", "upload_to_")
            if upload_key not in upload_branches:
                upload_branches[upload_key] = []
            upload_branches[upload_key].append(
                {"status": log.status, "message": log.message, "timestamp": log.timestamp, "task_id": log.task_id}
            )
        else:
            # Regular processing step
            if step_name not in step_map:
                step_map[step_name] = []
            step_map[step_name].append(
                {"status": log.status, "message": log.message, "timestamp": log.timestamp, "task_id": log.task_id}
            )

    # Build the flow structure
    flow = []
    for stage_key, stage_info in stages.items():
        stage_logs = step_map.get(stage_key, [])

        # Determine overall status for this stage
        if stage_logs:
            latest_log = stage_logs[-1]
            status = latest_log["status"]
            message = latest_log["message"]
            timestamp = latest_log["timestamp"]
            task_id = latest_log["task_id"]
        else:
            status = "not_run"
            message = None
            timestamp = None
            task_id = None

        stage_data = {
            "key": stage_key,
            "label": stage_info["label"],
            "status": status,
            "message": message,
            "timestamp": timestamp,
            "task_id": task_id,
            "can_retry": status == "failure",
            "is_branch_parent": stage_info.get("has_branches", False),
        }

        # If this is the upload stage, add branches
        if stage_info.get("has_branches") and upload_branches:
            branches = []
            for upload_key, upload_logs in upload_branches.items():
                latest_upload = upload_logs[-1]
                upload_name = upload_tasks.get(upload_key, upload_key.replace("upload_to_", "").title())

                branches.append(
                    {
                        "key": upload_key,
                        "label": upload_name,
                        "status": latest_upload["status"],
                        "message": latest_upload["message"],
                        "timestamp": latest_upload["timestamp"],
                        "task_id": latest_upload["task_id"],
                        "can_retry": latest_upload["status"] == "failure",
                    }
                )
            stage_data["branches"] = branches

        flow.append(stage_data)

    return flow


def _compute_step_summary(logs):
    """
    Compute a step-aligned summary from logs showing queued, success, and failure counts.

    Returns a dictionary with main step counts and upload branch counts.
    """
    # Count statuses for main processing steps (not uploads)
    main_steps = [
        "hash_file",
        "create_file_record",
        "check_text",
        "extract_text",
        "process_with_azure_document_intelligence",
        "extract_metadata_with_gpt",
        "embed_metadata_into_pdf",
        "finalize_document_storage",
        "send_to_all_destinations",
    ]

    upload_prefixes = ["upload_to_", "queue_"]

    main_counts = {"queued": 0, "in_progress": 0, "success": 0, "failure": 0}
    upload_counts = {"queued": 0, "in_progress": 0, "success": 0, "failure": 0}

    # Track which steps we've seen
    main_steps_seen = set()
    upload_tasks_seen = {}

    for log in logs:
        step_name = log.step_name
        status = log.status.lower()

        # Normalize status
        if status == "pending":
            status = "queued"

        # Check if it's an upload task
        is_upload = any(step_name.startswith(prefix) for prefix in upload_prefixes)

        if is_upload:
            # Track latest status for each unique upload task
            upload_tasks_seen[step_name] = status
        elif step_name in main_steps:
            # Track latest status for main steps
            main_steps_seen.add(step_name)
            if status in main_counts:
                main_counts[status] += 1

    # Count upload task statuses
    for task_status in upload_tasks_seen.values():
        if task_status in upload_counts:
            upload_counts[task_status] += 1

    return {
        "main": main_counts,
        "uploads": upload_counts,
        "total_main_steps": len(main_steps_seen),
        "total_upload_tasks": len(upload_tasks_seen),
    }
