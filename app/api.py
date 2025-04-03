# app/api.py
from fastapi import APIRouter, Request, HTTPException, status, Depends, UploadFile, File, Form
from hashlib import md5
from sqlalchemy.orm import Session
from typing import List
import os
import requests
import logging

from app.auth import require_login, get_current_user
from app.database import SessionLocal
from app.models import FileRecord
from app.config import settings
from app.tasks.process_document import process_document
from app.tasks.upload_to_dropbox import upload_to_dropbox
from app.tasks.upload_to_paperless import upload_to_paperless
from app.tasks.upload_to_nextcloud import upload_to_nextcloud
from app.tasks.upload_to_google_drive import upload_to_google_drive
from app.tasks.upload_to_onedrive import upload_to_onedrive
from app.tasks.send_to_all import send_to_all_destinations

# Set up logging
logger = logging.getLogger(__name__)

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

# API endpoints
@router.get("/diagnostic/settings")
@require_login
async def diagnostic_settings(request: Request, current_user: dict = Depends(get_current_user)):
    """
    API endpoint to dump settings to the log and view basic config information
    This endpoint doesn't expose sensitive information like passwords or tokens
    """
    from app.utils.config_validator import dump_all_settings, get_settings_for_display
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
            "uptime_kuma": bool(getattr(settings, 'uptime_kuma_url', None)),
            "auth": bool(getattr(settings, 'authentik_config_url', None)),
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

@router.post("/send_to_onedrive/")
@require_login
def send_to_onedrive_endpoint(file_path: str):
    """Send a document to OneDrive."""
    if not os.path.isabs(file_path):
        file_path = os.path.join(settings.workdir, 'processed', file_path)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=400, detail=f"File {file_path} not found."
        )
    task = upload_to_onedrive.delay(file_path)
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

@router.post("/onedrive/exchange-token")
@require_login
async def exchange_onedrive_token(
    request: Request,
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    code: str = Form(...),
    tenant_id: str = Form(...)
):
    """
    Exchange an authorization code for a refresh token.
    This is done on the server to avoid exposing client secret in the browser.
    """
    try:
        logger.info(f"Starting OneDrive token exchange process with tenant_id: {tenant_id}")
        
        # Prepare the token request
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        logger.info(f"Using token URL: {token_url}")
        
        payload = {
            'client_id': client_id,
            'scope': 'https://graph.microsoft.com/.default offline_access',
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'client_secret': client_secret
        }
        
        # Log request details (excluding secret)
        safe_payload = payload.copy()
        safe_payload['client_secret'] = '[REDACTED]' 
        safe_payload['code'] = f"{code[:5]}...{code[-5:]}" if len(code) > 10 else '[REDACTED]'
        logger.info(f"Token exchange request payload: {safe_payload}")
        
        # Make the token request
        logger.info("Sending POST request to Microsoft for token exchange")
        response = requests.post(token_url, data=payload)
        
        # Check if the request was successful
        logger.info(f"Token exchange response status: {response.status_code}")
        
        if response.status_code != 200:
            # Log the error response for debugging
            try:
                error_json = response.json()
                logger.error(f"Token exchange failed with status {response.status_code}: {error_json}")
                error_detail = error_json
            except Exception as json_err:
                logger.error(f"Failed to parse error response as JSON: {str(json_err)}")
                logger.error(f"Raw response content: {response.content[:500]}")  # Limit log size
                error_detail = {"error": "Unknown error", "raw_content_snippet": str(response.content[:100])}
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {error_detail}"
            )
            
        # Return the token response
        token_data = response.json()
        
        # Validate the token response
        if "refresh_token" not in token_data:
            logger.error(f"Microsoft returned success but no refresh token found in response: {token_data.keys()}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Microsoft OAuth server returned success but no refresh token was included"
            )
        
        # Calculate token length for logging
        refresh_token_length = len(token_data.get("refresh_token", ""))
        access_token_length = len(token_data.get("access_token", ""))
        
        logger.info(f"Successfully exchanged authorization code for OneDrive tokens. "
                   f"Refresh token length: {refresh_token_length}, "
                   f"Access token length: {access_token_length}")
        
        # Return just what's needed by the frontend
        return {
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data.get("expires_in", 3600)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during OneDrive token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exchange token: {str(e)}"
        )

@router.get("/onedrive/test-token")
@require_login
async def test_onedrive_token(request: Request):
    """
    Test if the configured OneDrive refresh token is valid.
    Provides detailed error information if token is invalid.
    """
    try:
        from app.tasks.upload_to_onedrive import get_onedrive_token
        
        logger.info("Testing OneDrive token validity")
        if not settings.onedrive_refresh_token:
            logger.warning("No OneDrive refresh token configured")
            return {
                "status": "error", 
                "message": "No OneDrive refresh token is configured"
            }
        
        # Check if client ID and client secret are configured
        if not settings.onedrive_client_id or not settings.onedrive_client_secret:
            logger.warning("OneDrive client ID or client secret is missing")
            return {
                "status": "error",
                "message": "OneDrive client ID or client secret is missing",
                "missing_config": True
            }
        
        # Try to get an access token using the configured refresh token
        try:
            access_token = get_onedrive_token()
            
            # If we got here, token is valid
            logger.info("OneDrive token is valid")
            return {
                "status": "success",
                "message": "OneDrive token is valid",
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"OneDrive token test failed: {error_msg}")
            
            # Determine if this is an invalid_grant error (expired token)
            is_expired = "invalid_grant" in error_msg.lower()
            
            return {
                "status": "error",
                "message": f"Token validation failed: {error_msg}",
                "is_expired": is_expired,
                "needs_reauth": True
            }
    
    except Exception as e:
        logger.exception("Unexpected error testing OneDrive token")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }

@router.post("/onedrive/save-settings")
@require_login
async def save_onedrive_settings(
    request: Request,
    client_id: str = Form(None),
    client_secret: str = Form(None),
    refresh_token: str = Form(...),
    tenant_id: str = Form("common"),
    folder_path: str = Form(None)
):
    """
    Save OneDrive settings to the .env file
    """
    try:
        # Get the path to the .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        
        if not os.path.exists(env_path):
            logger.error(f".env file not found at {env_path}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not find .env file to update"
            )
            
        logger.info(f"Updating OneDrive settings in {env_path}")
        
        # Read the current .env file
        with open(env_path, "r") as f:
            env_lines = f.readlines()
            
        # Define settings to update
        onedrive_settings = {
            "ONEDRIVE_REFRESH_TOKEN": refresh_token,
        }
        
        # Only update these if provided
        if client_id:
            onedrive_settings["ONEDRIVE_CLIENT_ID"] = client_id
        if client_secret:
            onedrive_settings["ONEDRIVE_CLIENT_SECRET"] = client_secret
        if tenant_id:
            onedrive_settings["ONEDRIVE_TENANT_ID"] = tenant_id
        if folder_path:
            onedrive_settings["ONEDRIVE_FOLDER_PATH"] = folder_path
            
        # Process each line and update or add settings
        updated = set()
        new_env_lines = []
        for line in env_lines:
            line = line.rstrip()
            is_updated = False
            for key, value in onedrive_settings.items():
                if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                    if line.startswith("# "):  # Uncomment if commented out
                        line = line[2:]
                    new_env_lines.append(f"{key}={value}")
                    updated.add(key)
                    is_updated = True
                    break
            if not is_updated:
                new_env_lines.append(line)
                
        # Add any settings that weren't updated (they weren't in the file)
        for key, value in onedrive_settings.items():
            if key not in updated:
                new_env_lines.append(f"{key}={value}")
                
        # Write the updated .env file
        with open(env_path, "w") as f:
            f.write("\n".join(new_env_lines) + "\n")
            
        # Update the settings in memory
        if refresh_token:
            settings.onedrive_refresh_token = refresh_token
        if client_id:
            settings.onedrive_client_id = client_id
        if client_secret:
            settings.onedrive_client_secret = client_secret
        if tenant_id:
            settings.onedrive_tenant_id = tenant_id
        if folder_path:
            settings.onedrive_folder_path = folder_path
            
        logger.info("Successfully updated OneDrive settings")
        
        return {
            "status": "success",
            "message": "OneDrive settings have been saved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error saving OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save OneDrive settings: {str(e)}"
        )

@router.post("/onedrive/update-settings")
@require_login
async def update_onedrive_settings(
    request: Request,
    client_id: str = Form(None),
    client_secret: str = Form(None),
    refresh_token: str = Form(...),
    tenant_id: str = Form("common"),
    folder_path: str = Form(None)
):
    """
    Update OneDrive settings in memory (without modifying .env file)
    """
    try:
        logger.info("Updating OneDrive settings in memory")
        
        # Update settings in memory
        if refresh_token:
            settings.onedrive_refresh_token = refresh_token
            logger.info("Updated ONEDRIVE_REFRESH_TOKEN in memory")
            
        if client_id:
            settings.onedrive_client_id = client_id
            logger.info("Updated ONEDRIVE_CLIENT_ID in memory")
            
        if client_secret:
            settings.onedrive_client_secret = client_secret
            logger.info("Updated ONEDRIVE_CLIENT_SECRET in memory")
            
        if tenant_id:
            settings.onedrive_tenant_id = tenant_id
            logger.info("Updated ONEDRIVE_TENANT_ID in memory")
            
        if folder_path:
            settings.onedrive_folder_path = folder_path
            logger.info("Updated ONEDRIVE_FOLDER_PATH in memory")
        
        # Test the token to make sure it works
        try:
            from app.tasks.upload_to_onedrive import get_onedrive_token
            access_token = get_onedrive_token()
            logger.info("Successfully tested OneDrive token")
        except Exception as e:
            logger.error(f"Token test failed after updating settings: {str(e)}")
            return {
                "status": "warning",
                "message": "Settings updated but token test failed: " + str(e)
            }
            
        return {
            "status": "success",
            "message": "OneDrive settings have been updated in memory"
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error updating OneDrive settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update OneDrive settings: {str(e)}"
        )

@router.get("/onedrive/get-full-config")
@require_login
async def get_onedrive_full_config(request: Request):
    """
    Get the full OneDrive configuration for sharing with worker nodes
    """
    try:
        # Create a configuration object with all OneDrive settings
        config = {
            "client_id": settings.onedrive_client_id or "",
            "client_secret": settings.onedrive_client_secret or "",
            "tenant_id": settings.onedrive_tenant_id or "common",
            "refresh_token": settings.onedrive_refresh_token or "",
            "folder_path": settings.onedrive_folder_path or "Documents/Uploads"
        }
        
        # Generate environment variable format
        env_format = "\n".join([
            f"ONEDRIVE_CLIENT_ID={config['client_id']}",
            f"ONEDRIVE_CLIENT_SECRET={config['client_secret']}",
            f"ONEDRIVE_TENANT_ID={config['tenant_id']}",
            f"ONEDRIVE_REFRESH_TOKEN={config['refresh_token']}",
            f"ONEDRIVE_FOLDER_PATH={config['folder_path']}"
        ])
        
        return {
            "status": "success",
            "config": config,
            "env_format": env_format
        }
    except Exception as e:
        logger.exception("Error getting OneDrive configuration")
        return {
            "status": "error",
            "message": str(e)
        }

@router.post("/dropbox/exchange-token")
@require_login
async def exchange_dropbox_token(
    request: Request,
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    code: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Exchange an authorization code for a refresh token from Dropbox.
    This is done on the server to avoid exposing client secret in the browser.
    """
    try:
        logger.info("Starting Dropbox token exchange process")
        
        # Prepare the token request
        token_url = "https://api.dropboxapi.com/oauth2/token"
        
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        # Log request details (excluding secret)
        safe_payload = payload.copy()
        safe_payload['client_secret'] = '[REDACTED]' 
        safe_payload['code'] = f"{code[:5]}...{code[-5:]}" if len(code) > 10 else '[REDACTED]'
        logger.info(f"Token exchange request payload: {safe_payload}")
        
        # Make the token request
        logger.info("Sending POST request to Dropbox for token exchange")
        response = requests.post(token_url, data=payload)
        
        # Check if the request was successful
        logger.info(f"Token exchange response status: {response.status_code}")
        
        if response.status_code != 200:
            # Log the error response for debugging
            try:
                error_json = response.json()
                logger.error(f"Token exchange failed with status {response.status_code}: {error_json}")
                error_detail = error_json
            except Exception as json_err:
                logger.error(f"Failed to parse error response as JSON: {str(json_err)}")
                logger.error(f"Raw response content: {response.content[:500]}")  # Limit log size
                error_detail = {"error": "Unknown error", "raw_content_snippet": str(response.content[:100])}
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token exchange failed: {error_detail}"
            )
            
        # Return the token response
        token_data = response.json()
        
        # Validate the token response
        if "refresh_token" not in token_data:
            logger.error(f"Dropbox returned success but no refresh token found in response: {token_data.keys()}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Dropbox OAuth server returned success but no refresh token was included"
            )
        
        # Calculate token length for logging
        refresh_token_length = len(token_data.get("refresh_token", ""))
        access_token_length = len(token_data.get("access_token", ""))
        
        logger.info(f"Successfully exchanged authorization code for Dropbox tokens. "
                   f"Refresh token length: {refresh_token_length}, "
                   f"Access token length: {access_token_length}")
        
        # Return just what's needed by the frontend
        return {
            "refresh_token": token_data["refresh_token"],
            "access_token": token_data["access_token"],
            "expires_in": token_data.get("expires_in", 14400)
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as they already have appropriate status codes
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during Dropbox token exchange: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exchange token: {str(e)}"
        )

@router.post("/dropbox/update-settings")
@require_login
async def update_dropbox_settings(
    request: Request,
    app_key: str = Form(None),
    app_secret: str = Form(None),
    refresh_token: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Update Dropbox settings in memory
    """
    try:
        logger.info("Updating Dropbox settings in memory")
        
        # Update settings in memory
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
            logger.info("Updated DROPBOX_REFRESH_TOKEN in memory")
            
        if app_key:
            settings.dropbox_app_key = app_key
            logger.info("Updated DROPBOX_APP_KEY in memory")
            
        if app_secret:
            settings.dropbox_app_secret = app_secret
            logger.info("Updated DROPBOX_APP_SECRET in memory")
            
        if folder_path:
            settings.dropbox_folder = folder_path
            logger.info("Updated DROPBOX_FOLDER in memory")
        
        # Test token validity would be here, but we'll skip it for now
        
        return {
            "status": "success",
            "message": "Dropbox settings have been updated in memory"
        }
        
    except Exception as e:
        logger.exception(f"Unexpected error updating Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Dropbox settings: {str(e)}"
        )

@router.get("/dropbox/test-token")
@require_login
async def test_dropbox_token(request: Request):
    """
    Test if the configured Dropbox refresh token is valid.
    """
    try:
        from app.tasks.upload_to_dropbox import get_dropbox_client
        
        logger.info("Testing Dropbox token validity")
        if not settings.dropbox_refresh_token:
            logger.warning("No Dropbox refresh token configured")
            return {
                "status": "error", 
                "message": "No Dropbox refresh token is configured"
            }
        
        # Check if app key and app secret are configured
        if not settings.dropbox_app_key or not settings.dropbox_app_secret:
            logger.warning("Dropbox app key or app secret is missing")
            return {
                "status": "error",
                "message": "Dropbox app key or app secret is missing",
                "missing_config": True
            }
        
        # Try to get a client using the configured refresh token
        try:
            dbx = get_dropbox_client()
            # Test connection by getting account info
            account = dbx.users_get_current_account()
            logger.info(f"Successfully connected to Dropbox as {account.name.display_name}")
            
            return {
                "status": "success",
                "message": f"Token is valid! Connected as {account.name.display_name}",
                "account": account.name.display_name,
                "email": account.email
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Dropbox token test failed: {error_msg}")
            
            # Determine if this is an authentication error
            is_auth_error = "auth" in error_msg.lower() or "invalid" in error_msg.lower()
            
            return {
                "status": "error",
                "message": f"Token validation failed: {error_msg}",
                "is_auth_error": is_auth_error,
                "needs_reauth": is_auth_error
            }
    
    except Exception as e:
        logger.exception("Unexpected error testing Dropbox token")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}"
        }

@router.post("/dropbox/save-settings")
@require_login
async def save_dropbox_settings(
    request: Request,
    app_key: str = Form(None),
    app_secret: str = Form(None),
    refresh_token: str = Form(...),
    folder_path: str = Form(None)
):
    """
    Save Dropbox settings to the .env file
    """
    try:
        # Get the path to the .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
        
        if not os.path.exists(env_path):
            logger.error(f".env file not found at {env_path}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not find .env file to update"
            )
            
        logger.info(f"Updating Dropbox settings in {env_path}")
        
        # Read the current .env file
        with open(env_path, "r") as f:
            env_lines = f.readlines()
            
        # Define settings to update
        dropbox_settings = {
            "DROPBOX_REFRESH_TOKEN": refresh_token,
        }
        
        # Only update these if provided
        if app_key:
            dropbox_settings["DROPBOX_APP_KEY"] = app_key
        if app_secret:
            dropbox_settings["DROPBOX_APP_SECRET"] = app_secret
        if folder_path:
            dropbox_settings["DROPBOX_FOLDER"] = folder_path
            
        # Process each line and update or add settings
        updated = set()
        new_env_lines = []
        for line in env_lines:
            line = line.rstrip()
            is_updated = False
            for key, value in dropbox_settings.items():
                if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                    if line.startswith("# "):  # Uncomment if commented out
                        line = line[2:]
                    new_env_lines.append(f"{key}={value}")
                    updated.add(key)
                    is_updated = True
                    break
            if not is_updated:
                new_env_lines.append(line)
                
        # Add any settings that weren't updated (they weren't in the file)
        for key, value in dropbox_settings.items():
            if key not in updated:
                new_env_lines.append(f"{key}={value}")
                
        # Write the updated .env file
        with open(env_path, "w") as f:
            f.write("\n".join(new_env_lines) + "\n")
            
        # Update the settings in memory
        if refresh_token:
            settings.dropbox_refresh_token = refresh_token
        if app_key:
            settings.dropbox_app_key = app_key
        if app_secret:
            settings.dropbox_app_secret = app_secret
        if folder_path:
            settings.dropbox_folder = folder_path
            
        logger.info("Successfully updated Dropbox settings")
        
        return {
            "status": "success",
            "message": "Dropbox settings have been saved"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error saving Dropbox settings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save Dropbox settings: {str(e)}"
        )


