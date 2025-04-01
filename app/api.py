# app/api.py
from fastapi import APIRouter, Request, HTTPException, status, Depends, UploadFile, File
from hashlib import md5
from sqlalchemy.orm import Session
from typing import List
import os

from app.auth import require_login, get_current_user
from app.database import SessionLocal
from app.models import FileRecord
from app.config import settings
from app.tasks.process_document import process_document
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.send_to_all import send_to_all_destinations

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/whoami")
async def whoami(request: Request):
    """
    Returns user info if logged in, else 401.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    email = user.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="User has no email in session")

    # Generate Gravatar URL from email
    email_hash = md5(email.strip().lower().encode()).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"

    return {
        "email": email,
        "picture": gravatar_url
    }

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

# API endpoints
@router.get("/diagnostic/settings")
@require_login
async def diagnostic_settings(current_user: dict = Depends(get_current_user)):
    """
    API endpoint to dump settings to the log and view basic config information
    This endpoint doesn't expose sensitive information like passwords or tokens
    """
    from app.utils.config_validator import dump_all_settings
    # Dump full settings to log for admin to see
    dump_all_settings()
    
    # Return safe subset of settings for API response
    safe_settings = {
        "workdir": settings.workdir,
        "external_hostname": settings.external_hostname,
        "configured_services": {
            "email": bool(getattr(settings, 'email_host', None)),
            "s3": bool(getattr(settings, 's3_bucket_name', None)),
            "dropbox": bool(getattr(settings, 'dropbox_refresh_token', None)),
            "nextcloud": bool(getattr(settings, 'nextcloud_upload_url', None)),
            "sftp": bool(getattr(settings, 'sftp_host', None)),
            "paperless": bool(getattr(settings, 'paperless_host', None)),
            "google_drive": bool(getattr(settings, 'google_drive_credentials_json', None)),
        },
        "imap_enabled": bool(getattr(settings, 'imap1_host', None) or getattr(settings, 'imap2_host', None)),
    }
    
    return {
        "status": "success",
        "settings": safe_settings,
        "message": "Full settings have been dumped to application logs"
    }

@router.post("/process/")
@require_login
def process(file_path: str):
    """API Endpoint to start document processing."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, file_path)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )

    task = process_document.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_dropbox/")
@require_login
def send_to_dropbox(file_path: str):
    """Send a document to Dropbox."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_dropbox.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_paperless/")
@require_login
def send_to_paperless(file_path: str):
    """Send a document to Paperless-ngx."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_paperless.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_nextcloud/")
@require_login
def send_to_nextcloud(file_path: str):
    """Send a document to NextCloud."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_nextcloud.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_google_drive/")
@require_login
def send_to_google_drive(file_path: str):
    """Send a document to Google Drive."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_google_drive.delay(file_path)
    return {"task_id": task.id, "status": "queued"}

@router.post("/send_to_all_destinations/")
@require_login
def send_to_all_destinations_endpoint(file_path: str):
    """Call the aggregator task that sends this file to all configured destinations."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )

    task = send_to_all_destinations.delay(file_path)
    return {"task_id": task.id, "status": "queued", "file_path": file_path}

@router.post("/processall")
@require_login
def process_all_pdfs_in_workdir():
    """Finds all .pdf files in <workdir> and enqueues them for processing."""
    target_dir = settings.workdir
    if not os.path.exists(target_dir):
        raise HTTPException(
            status_code=400, detail=f"Directory {target_dir} does not exist."
        )

    pdf_files = []
    for filename in os.listdir(target_dir):
        if filename.lower().endswith(".pdf"):
            pdf_files.append(filename)

    if not pdf_files:
        return {"message": "No PDF files found in that directory."}

    task_ids = []
    for pdf in pdf_files:
        file_path = os.path.join(target_dir, pdf)
        task = process_document.delay(file_path)
        task_ids.append(task.id)

    return {
        "message": f"Enqueued {len(pdf_files)} PDFs to upload_to_s3",
        "pdf_files": pdf_files,
        "task_ids": task_ids
    }

@router.post("/ui-upload")
@require_login
async def ui_upload(request: Request, file: UploadFile = File(...)):
    """Endpoint to accept a user-uploaded file and enqueue it for processing."""
    import uuid
    import os.path
    
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
    print(f"Saved uploaded file '{safe_filename}' as '{target_filename}'")
    
    task = process_document.delay(target_path)
    return {
        "task_id": task.id, 
        "status": "queued", 
        "original_filename": safe_filename,
        "stored_filename": target_filename
    }

# Note: The api/router.py is now a submodule organization, 
# but we're keeping this file for compatibility until we've fully migrated
