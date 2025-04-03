"""
Diagnostic API endpoints
"""
from fastapi import APIRouter, Request, Depends
import logging

from app.auth import require_login, get_current_user
from app.config import settings

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

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
