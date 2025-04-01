from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
import os

from app.config import settings
from app.auth import get_current_user, require_login
from app.tasks.process_document import process_document
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.send_to_all import send_to_all_destinations

router = APIRouter()

# Diagnostic endpoints
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

# File processing endpoints
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
async def ui_upload(file: UploadFile = File(...)):
    """Endpoint to accept a user-uploaded file and enqueue it for processing."""
    workdir = "/workdir"
    target_path = os.path.join(workdir, file.filename)
    try:
        with open(target_path, "wb") as f:
            content = await file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {e}"
        )

    task = process_document.delay(target_path)
    return {"task_id": task.id, "status": "queued"}
