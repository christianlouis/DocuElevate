"""View route for the user onboarding wizard."""

import logging

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.config import settings as _settings
from app.models import UserProfile
from app.utils.subscription import get_all_tiers
from app.views.base import APIRouter, get_db, require_login, templates

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Destination helper
# ---------------------------------------------------------------------------

_DESTINATION_META: list[dict] = [
    {"id": "dropbox", "name": "Dropbox", "icon": "fab fa-dropbox"},
    {"id": "gdrive", "name": "Google Drive", "icon": "fab fa-google-drive"},
    {"id": "onedrive", "name": "OneDrive", "icon": "fab fa-microsoft"},
    {"id": "s3", "name": "Amazon S3", "icon": "fab fa-aws"},
    {"id": "nextcloud", "name": "Nextcloud", "icon": "fas fa-cloud"},
    {"id": "webdav", "name": "WebDAV", "icon": "fas fa-server"},
    {"id": "sftp", "name": "SFTP", "icon": "fas fa-terminal"},
    {"id": "ftp", "name": "FTP", "icon": "fas fa-server"},
]


def _get_configured_destinations(cfg: Settings) -> list[dict]:
    """Return which storage providers are fully configured in the current settings.

    Each entry is a dict with ``id``, ``name``, and ``icon`` keys.

    Args:
        cfg: The application settings object (``app.config.settings``).

    Returns:
        A list of destination dicts for providers that have the required
        credentials set.
    """
    checks: dict[str, bool] = {
        "dropbox": bool(cfg.dropbox_refresh_token and cfg.dropbox_app_key),
        "gdrive": bool(cfg.google_drive_credentials_json or cfg.google_drive_refresh_token),
        "onedrive": bool(cfg.onedrive_refresh_token and cfg.onedrive_client_id),
        "s3": bool(cfg.aws_access_key_id and cfg.s3_bucket_name),
        "nextcloud": bool(cfg.nextcloud_upload_url and cfg.nextcloud_username),
        "webdav": bool(cfg.webdav_url and cfg.webdav_username),
        "sftp": bool(cfg.sftp_host and cfg.sftp_username),
        "ftp": bool(cfg.ftp_host and cfg.ftp_username),
    }
    return [meta for meta in _DESTINATION_META if checks.get(meta["id"], False)]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/onboarding", include_in_schema=False)
@require_login
async def onboarding_page(request: Request, db: Session = Depends(get_db)):
    """Render the multi-step onboarding wizard.

    Redirects to ``/upload`` when the user has already completed onboarding.
    """
    user = request.session.get("user") or {}
    user_id = user.get("sub") or user.get("preferred_username") or user.get("email") or user.get("id")

    if user_id:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if profile and profile.onboarding_completed:
            from starlette.responses import RedirectResponse

            return RedirectResponse(url="/upload", status_code=302)

    configured_destinations = _get_configured_destinations(_settings)
    tiers = get_all_tiers(db)

    return templates.TemplateResponse(
        "onboarding.html",
        {
            "request": request,
            "user": user,
            "configured_destinations": configured_destinations,
            "tiers": tiers,
        },
    )
