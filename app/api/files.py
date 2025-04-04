"""
File-related API endpoints
"""
from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from sqlalchemy.orm import Session
import logging
import os
import uuid
import mimetypes

from app.auth import require_login
from app.models import FileRecord
from app.config import settings
from app.api.common import get_db
from app.tasks.process_document import process_document
from app.tasks.convert_to_pdf import convert_to_pdf

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/files")
@require_login
def list_files_api(request: Request, db: Session = Depends(get_db)):
    """
    Returns a JSON list of all FileRecord entries.
    Protected by `@require_login`, so only logged-in sessions can access.
    
    Example response:
    [
      {
        "id": 123,
        "filehash": "abc123...",
        "original_filename": "example.pdf",
        "local_filename": "/workdir/tmp/<uuid>.pdf",
        "file_size": 1048576,
        "mime_type": "application/pdf",
        "created_at": "2025-05-01T12:34:56.789000"
      },
      ...
    ]
    """
    files = db.query(FileRecord).order_by(FileRecord.created_at.desc()).all()
    # Return a simple list of dicts
    result = []
    for f in files:
        result.append({
            "id": f.id,
            "filehash": f.filehash,
            "original_filename": f.original_filename,
            "local_filename": f.local_filename,
            "file_size": f.file_size,
            "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None
        })
    return result

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
