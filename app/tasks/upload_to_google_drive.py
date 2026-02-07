"""
app/tasks/upload_to_google_drive.py
"""

import os
import json
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

from app.config import settings
from app.tasks.retry_config import BaseTaskWithRetry
from app.celery_app import celery
from app.utils import log_task_progress

logger = logging.getLogger(__name__)

def get_drive_service_oauth():
    """
    Get Google Drive service using OAuth credentials.
    Uses saved refresh token to get a new access token.
    """
    try:
        # Check for required OAuth settings
        if not (settings.google_drive_client_id and 
                settings.google_drive_client_secret and 
                settings.google_drive_refresh_token):
            logger.error("Google Drive OAuth credentials not fully configured")
            return None
        
        # Create credentials object from refresh token
        credentials = OAuthCredentials(
            None,  # No access token initially, will be refreshed
            refresh_token=settings.google_drive_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_drive_client_id,
            client_secret=settings.google_drive_client_secret,
            # Use only drive.file scope
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        
        # Refresh the access token
        credentials.refresh(Request())
        
        # Build and return the service
        service = build('drive', 'v3', credentials=credentials)
        return service
        
    except RefreshError as e:
        logger.error(f"Failed to refresh Google Drive token: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Failed to authenticate with Google Drive OAuth: {str(e)}")
        return None

def get_google_drive_service():
    """
    Authenticate with Google Drive API using service account credentials
    and return an authorized service object.
    """
    try:
        # Check if we should use OAuth instead of service account
        if getattr(settings, 'google_drive_use_oauth', False):
            return get_drive_service_oauth()
            
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

def extract_metadata_from_file(file_path):
    """
    Try to extract metadata from a file using several methods:
    1. Check for a .json metadata file with the same name
    
    Returns a dictionary of metadata or empty dict if not found
    """
    # Check for separate metadata JSON file
    metadata_path = os.path.splitext(file_path)[0] + '.json'
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                logger.info(f"Loaded metadata from external JSON file: {metadata_path}")
                return metadata
        except Exception as e:
            logger.warning(f"Failed to load metadata from JSON file: {str(e)}")
    
    return {}

def truncate_property_value(key, value, max_bytes=100):
    """
    Truncate a property value to ensure the key+value stays under the byte limit.
    Google Drive has a 124 byte limit for property key-value pairs.
    We reserve ~20-24 bytes for the key and leave ~100 bytes for the value.
    """
    # Convert to string if not already
    str_value = str(value)
    
    # Calculate current size of key and value in bytes
    key_bytes = len(key.encode('utf-8'))
    value_bytes = len(str_value.encode('utf-8'))
    total_bytes = key_bytes + value_bytes
    
    # If under limit, return original value
    if total_bytes <= max_bytes:
        return str_value
    
    # Calculate how many bytes we need to trim from value
    # Leave a small buffer to be safe
    bytes_to_trim = total_bytes - max_bytes + 4
    
    # Iteratively truncate the string until it's under the byte limit
    while len(str_value.encode('utf-8')) > value_bytes - bytes_to_trim:
        str_value = str_value[:-1]
    
    # Add ellipsis to indicate truncation
    if str_value != str(value):
        str_value = str_value[:-3] + "..."
        
    return str_value

@celery.task(base=BaseTaskWithRetry, bind=True)
def upload_to_google_drive(self, file_path: str, file_id: int = None, include_metadata=True):
    """
    Uploads a file to Google Drive in the configured folder with optional metadata.
    
    Args:
        file_path: Path to the file to upload
        file_id: Optional file ID to associate with logs
        include_metadata: Whether to include metadata in the upload
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting Google Drive upload: {file_path}")
    log_task_progress(
        task_id, "upload_to_google_drive", "in_progress", f"Uploading to Google Drive: {os.path.basename(file_path)}", file_id=file_id
    )

    if not os.path.exists(file_path):
        error_msg = f"File not found: {file_path}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_google_drive", "failure", error_msg, file_id=file_id)
        raise FileNotFoundError(error_msg)

    # Extract filename from path
    filename = os.path.basename(file_path)

    # Extract metadata if available
    metadata = {}
    if include_metadata:
        metadata = extract_metadata_from_file(file_path)

    try:
        # Get Google Drive service
        service = get_google_drive_service()
        if not service:
            error_msg = "Failed to initialize Google Drive service"
            logger.error(f"[{task_id}] {error_msg}")
            log_task_progress(task_id, "upload_to_google_drive", "failure", error_msg, file_id=file_id)
            raise Exception(error_msg)

        # Prepare the file metadata
        file_metadata = {
            'name': filename,
        }
        
        # If folder ID is specified, set parent folder
        if settings.google_drive_folder_id:
            file_metadata['parents'] = [settings.google_drive_folder_id]
            
        # Add custom properties if metadata exists
        if metadata:
            # Google Drive properties must be strings and can't be nested objects
            file_metadata['properties'] = {}
            
            # Only add a few important top-level metadata fields as properties
            # Skip nested objects and long values to avoid the 124-byte limit
            safe_properties = {}
            for key, value in metadata.items():
                # Skip nested structures completely - they'll be in the description
                if isinstance(value, (dict, list)):
                    continue
                
                # Try to add simple values with truncation if needed
                try:
                    truncated_value = truncate_property_value(key, value)
                    safe_properties[key] = truncated_value
                except Exception as e:
                    logger.warning(f"Skipping metadata property {key}: {str(e)}")
            
            # Only use the safe properties
            file_metadata['properties'] = safe_properties
            
            # Add minimal appProperties
            file_metadata['appProperties'] = {
                'docuelevate': 'true'
            }
            
            # Add metadata to file description for better visibility in Google Drive UI
            # Description has much higher size limits than properties
            formatted_json = json.dumps(metadata, indent=2)
            file_metadata['description'] = f"Document Metadata:\n\n```json\n{formatted_json}\n```"
            
            logger.debug(f"Adding metadata to Google Drive file: {json.dumps(file_metadata['properties'])}")
        
        # Upload file with metadata
        media = MediaFileUpload(
            file_path, 
            mimetype='application/pdf',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink,properties,appProperties,description'
        ).execute()
        
        # Log success details
        file_id_gd = file.get('id')
        web_view_link = file.get('webViewLink')
        
        logger.info(f"[{task_id}] Successfully uploaded {filename} to Google Drive with ID: {file_id_gd}")
        logger.info(f"[{task_id}] File accessible at: {web_view_link}")
        log_task_progress(task_id, "upload_to_google_drive", "success", f"Uploaded to Google Drive: {filename}", file_id=file_id)
        
        result = {
            "status": "Completed", 
            "file_path": file_path,
            "google_drive_file_id": file_id_gd,
            "google_drive_web_link": web_view_link
        }
        
        # Add metadata info to result if included
        if metadata:
            result["metadata_included"] = True
            
        return result

    except Exception as e:
        error_msg = f"Failed to upload {filename} to Google Drive: {str(e)}"
        logger.error(f"[{task_id}] {error_msg}")
        log_task_progress(task_id, "upload_to_google_drive", "failure", error_msg, file_id=file_id)
        raise Exception(error_msg)
