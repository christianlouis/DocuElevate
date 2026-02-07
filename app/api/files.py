"""
File-related API endpoints
"""
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, func
from typing import Optional, List
import logging
import os
import uuid
import mimetypes

from app.auth import require_login
from app.models import FileRecord, ProcessingLog
from app.config import settings
from app.api.common import get_db
from app.tasks.process_document import process_document
from app.tasks.convert_to_pdf import convert_to_pdf

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/files")
@require_login
def list_files_api(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort field: id, original_filename, file_size, mime_type, created_at, status"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    search: Optional[str] = Query(None, description="Search in filename"),
    mime_type: Optional[str] = Query(None, description="Filter by MIME type"),
    status: Optional[str] = Query(None, description="Filter by processing status")
):
    """
    Returns a paginated JSON list of FileRecord entries with processing status.
    Supports server-side sorting, filtering, and searching.
    
    Query Parameters:
    - page: Page number (default: 1)
    - per_page: Items per page (default: 50, max: 200)
    - sort_by: Field to sort by (default: created_at)
    - sort_order: asc or desc (default: desc)
    - search: Search in filename
    - mime_type: Filter by MIME type
    - status: Filter by processing status (pending, processing, completed, failed)
    
    Example response:
    {
      "files": [...],
      "pagination": {
        "page": 1,
        "per_page": 50,
        "total_items": 150,
        "total_pages": 3
      }
    }
    """
    # Start with base query
    query = db.query(FileRecord)
    
    # Apply search filter
    if search:
        query = query.filter(FileRecord.original_filename.ilike(f"%{search}%"))
    
    # Apply MIME type filter
    if mime_type:
        query = query.filter(FileRecord.mime_type == mime_type)
    
    # Get total count before pagination
    total_items = query.count()
    
    # Apply sorting
    sort_column = {
        "id": FileRecord.id,
        "original_filename": FileRecord.original_filename,
        "file_size": FileRecord.file_size,
        "mime_type": FileRecord.mime_type,
        "created_at": FileRecord.created_at
    }.get(sort_by, FileRecord.created_at)
    
    if sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))
    
    # Apply pagination
    offset = (page - 1) * per_page
    files = query.offset(offset).limit(per_page).all()
    
    # Build result with processing status
    result = []
    for f in files:
        # Get processing status for this file
        processing_status = _get_file_processing_status(db, f.id)
        
        result.append({
            "id": f.id,
            "filehash": f.filehash,
            "original_filename": f.original_filename,
            "local_filename": f.local_filename,
            "file_size": f.file_size,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "processing_status": processing_status
        })
    
    # Filter by status if requested (after computing statuses)
    if status:
        result = [f for f in result if f["processing_status"]["status"] == status]
        total_items = len(result)  # Update total for filtered results
    
    # Calculate pagination info
    total_pages = (total_items + per_page - 1) // per_page
    
    return {
        "files": result,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages
        }
    }


def _get_file_processing_status(db: Session, file_id: int) -> dict:
    """
    Get the processing status for a file by checking its processing logs.
    
    Returns:
        dict with status, last_step, and has_errors
    """
    # Get all logs for this file
    logs = db.query(ProcessingLog).filter(
        ProcessingLog.file_id == file_id
    ).order_by(ProcessingLog.timestamp.desc()).all()
    
    if not logs:
        return {
            "status": "pending",
            "last_step": None,
            "has_errors": False,
            "total_steps": 0
        }
    
    # Check for failures
    has_errors = any(log.status == "failure" for log in logs)
    
    # Check if any in progress
    in_progress = any(log.status == "in_progress" for log in logs)
    
    # Get the latest log
    latest_log = logs[0]
    
    # Determine overall status
    if has_errors:
        status = "failed"
    elif in_progress:
        status = "processing"
    elif latest_log.status == "success":
        status = "completed"
    else:
        status = "pending"
    
    return {
        "status": status,
        "last_step": latest_log.step_name,
        "has_errors": has_errors,
        "total_steps": len(logs)
    }



@router.get("/files/{file_id}")
@require_login
def get_file_details(request: Request, file_id: int, db: Session = Depends(get_db)):
    """
    Get detailed information about a specific file including processing history.
    """
    # Find the file record
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    
    if not file_record:
        raise HTTPException(
            status_code=404,
            detail=f"File record with ID {file_id} not found"
        )
    
    # Get processing logs
    logs = db.query(ProcessingLog).filter(
        ProcessingLog.file_id == file_id
    ).order_by(ProcessingLog.timestamp.desc()).all()
    
    # Build log list
    log_list = []
    for log in logs:
        log_list.append({
            "id": log.id,
            "task_id": log.task_id,
            "step_name": log.step_name,
            "status": log.status,
            "message": log.message,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None
        })
    
    # Get processing status
    processing_status = _get_file_processing_status(db, file_id)
    
    # Check if files exist on disk
    files_on_disk = {
        "original": os.path.exists(file_record.local_filename) if file_record.local_filename else False
    }
    
    return {
        "file": {
            "id": file_record.id,
            "filehash": file_record.filehash,
            "original_filename": file_record.original_filename,
            "local_filename": file_record.local_filename,
            "file_size": file_record.file_size,
            "mime_type": file_record.mime_type,
            "created_at": file_record.created_at.isoformat() if file_record.created_at else None
        },
        "processing_status": processing_status,
        "logs": log_list,
        "files_on_disk": files_on_disk
    }

@router.delete("/files/{file_id}")
@require_login
def delete_file_record(request: Request, file_id: int, db: Session = Depends(get_db)):
    """
    Delete a file record from the database.
    This only removes the database entry, not the actual file.
    """
    # Check if file deletion is allowed
    if not settings.allow_file_delete:
        raise HTTPException(
            status_code=403,
            detail="File deletion is disabled in the configuration"
        )

    try:
        # Find the file record
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        
        if not file_record:
            raise HTTPException(
                status_code=404,
                detail=f"File record with ID {file_id} not found"
            )
        
        # Log the deletion
        logger.info(f"Deleting file record: ID={file_id}, Filename={file_record.original_filename}")
        
        # Delete the record
        db.delete(file_record)
        db.commit()
        
        return {
            "status": "success",
            "message": f"File record {file_id} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting file record {file_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting file record: {str(e)}"
        )

@router.post("/ui-upload")
@require_login
async def ui_upload(request: Request, file: UploadFile = File(...)):
    """Endpoint to accept a user-uploaded file and enqueue it for processing."""
    workdir = settings.workdir
    
    # Extract just the filename without any path components to prevent path traversal
    safe_filename = os.path.basename(file.filename)
    
    # Generate a unique filename with UUID to prevent overwriting and filename conflicts
    unique_id = str(uuid.uuid4())
    # Keep the original extension if present
    if "." in safe_filename:
        file_extension = safe_filename.rsplit(".", 1)[1]
        target_filename = f"{unique_id}.{file_extension}"
    else:
        target_filename = unique_id
    
    # Store both the safe original name and the unique name
    target_path = os.path.join(workdir, target_filename)
    
    try:
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {e}"
        )

    # Log the mapping between original and safe filename
    logger.info(f"Saved uploaded file '{safe_filename}' as '{target_filename}'")
    
    # Check file size
    file_size = os.path.getsize(target_path)
    max_size = 500 * 1024 * 1024  # 500MB
    if file_size > max_size:
        # Remove the file if it's too large
        os.remove(target_path)
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size} bytes (max {max_size} bytes)"
        )
    
    # Same set of allowed file types as in the IMAP task
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
        "application/rtf",
        "text/rtf",
    }
    
    # Image MIME types that need conversion
    IMAGE_MIME_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png', 
        'image/gif', 'image/bmp', 'image/tiff',
        'image/webp', 'image/svg+xml'
    }
    
    # Determine if the file is a PDF or needs conversion
    mime_type, _ = mimetypes.guess_type(target_path)
    file_ext = os.path.splitext(target_path)[1].lower()
    
    # Check if it's a PDF by extension or MIME type
    is_pdf = file_ext == ".pdf" or mime_type == "application/pdf"
    
    if is_pdf:
        # If it's a PDF, process directly
        task = process_document.delay(target_path)
        logger.info(f"Enqueued PDF for processing: {target_path}")
    elif mime_type in IMAGE_MIME_TYPES or any(file_ext.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg']):
        # If it's an image, convert to PDF first
        task = convert_to_pdf.delay(target_path)
        logger.info(f"Enqueued image for PDF conversion: {target_path}")
    elif mime_type in ALLOWED_MIME_TYPES or any(file_ext.endswith(ext) for ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf', '.txt', '.csv']):
        # If it's an office document, convert to PDF first
        task = convert_to_pdf.delay(target_path)
        logger.info(f"Enqueued office document for PDF conversion: {target_path}")
    else:
        # For any other file type, attempt conversion but log a warning
        logger.warning(f"Unsupported MIME type {mime_type} for {target_path}, attempting conversion")
        task = convert_to_pdf.delay(target_path)
    
    return {
        "task_id": task.id, 
        "status": "queued", 
        "original_filename": safe_filename,
        "stored_filename": target_filename
    }
