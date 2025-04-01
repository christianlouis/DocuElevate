"""
app/tasks/upload_to_google_drive.py
"""

import os
import json
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery

logger = logging.getLogger(__name__)

def get_google_drive_service():
    """
    Authenticate with Google Drive API using service account credentials
    and return an authorized service object.
    """
    try:
        # Load service account credentials from settings
        if not settings.google_drive_credentials_json:
            logger.error("Google Drive credentials not configured")
            return None
            
        credentials_dict = json.loads(settings.google_drive_credentials_json)
        credentials = Credentials.from_service_account_info(
            credentials_dict, 
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        # Delegate to user if specified
        if settings.google_drive_delegate_to:
            credentials = credentials.with_subject(settings.google_drive_delegate_to)
            
        # Build and return the service
        service = build('drive', 'v3', credentials=credentials)
        return service
    
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Drive: {str(e)}")
        return None


@celery.task(base=BaseTaskWithRetry)
def upload_to_google_drive(file_path: str):
    """Uploads a file to Google Drive in the configured folder."""

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Extract filename from path
    filename = os.path.basename(file_path)

    try:
        # Get Google Drive service
        service = get_google_drive_service()
        if not service:
            raise Exception("Failed to initialize Google Drive service")

        # Prepare the file metadata
        file_metadata = {
            'name': filename,
        }
        
        # If folder ID is specified, set parent folder
        if settings.google_drive_folder_id:
            file_metadata['parents'] = [settings.google_drive_folder_id]
        
        # Upload file with metadata
        media = MediaFileUpload(
            file_path, 
            mimetype='application/pdf',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        # Log success details
        file_id = file.get('id')
        web_view_link = file.get('webViewLink')
        
        logger.info(f"Successfully uploaded {filename} to Google Drive with ID: {file_id}")
        logger.info(f"File accessible at: {web_view_link}")
        
        return {
            "status": "Completed", 
            "file_path": file_path,
            "google_drive_file_id": file_id,
            "google_drive_web_link": web_view_link
        }

    except Exception as e:
        error_msg = f"Failed to upload {filename} to Google Drive: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
