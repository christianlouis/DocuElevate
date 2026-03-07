"""
General routes for the application homepage and basic pages.
"""

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.utils.config_validator import get_provider_status, validate_storage_configs
from app.views.base import APIRouter, get_db, logger, require_login, templates

router = APIRouter()

# Date format constant
_DATE_DISPLAY_FORMAT = "%B %d, %Y"


@router.get("/", include_in_schema=False)
async def serve_index(request: Request, db: Session = Depends(get_db)):
    """
    Serve the index/home page.

    If the system requires initial setup, redirect to the setup wizard.
    """
    # Check if setup wizard is needed
    from app.utils.settings_service import get_setting_from_db
    from app.utils.setup_wizard import is_setup_required

    # Check if setup was explicitly skipped
    setup_skipped = get_setting_from_db(db, "_setup_wizard_skipped")

    # Check setup completion query param
    setup_complete = request.query_params.get("setup") == "complete"

    if not setup_skipped and not setup_complete and is_setup_required():
        logger.info("System requires initial setup, redirecting to wizard")
        return RedirectResponse(url="/setup?step=1", status_code=303)

    # Get provider information from config validator
    providers = get_provider_status()

    # Count configured providers
    configured_providers = sum(1 for provider in providers.values() if provider["configured"])

    # Count different types of storage targets
    storage_issues = validate_storage_configs()
    configured_storage_targets = sum(
        1
        for provider, issues in storage_issues.items()
        if not issues
        and provider in ["dropbox", "nextcloud", "sftp", "s3", "ftp", "webdav", "google_drive", "onedrive"]
    )

    from app.models import FileRecord

    today = datetime.now(timezone.utc).date()

    # Global file counts (or per-user in multi-user mode)
    from app.config import settings

    user = request.session.get("user") or {}
    is_admin = user.get("is_admin", False)

    try:
        total_files: int = db.query(func.count(FileRecord.id)).scalar() or 0

        files_today: int = (
            db.query(func.count(FileRecord.id)).filter(func.date(FileRecord.created_at) == today).scalar() or 0
        )

        files_month: int = (
            db.query(func.count(FileRecord.id))
            .filter(func.strftime("%Y-%m", FileRecord.created_at) == today.strftime("%Y-%m"))
            .scalar()
            or 0
        )

        files_with_ocr: int = db.query(func.count(FileRecord.id)).filter(FileRecord.ocr_text.isnot(None)).scalar() or 0

        unique_users: int = (
            db.query(func.count(func.distinct(FileRecord.owner_id))).filter(FileRecord.owner_id.isnot(None)).scalar()
            or 0
        )
    except Exception as e:
        logger.error(f"Error computing dashboard stats: {e}")
        total_files = files_today = files_month = files_with_ocr = unique_users = 0

    # Per-user usage for the subscription widget (multi-user only)
    user_usage = None
    user_tier = None
    if settings.multi_user_enabled:
        owner_id: str = user.get("username") or user.get("email") or user.get("sub") or ""
        if owner_id:
            try:
                from app.utils.subscription import get_tier, get_user_tier_id, get_user_usage

                tier_id = get_user_tier_id(db, owner_id)
                user_tier = get_tier(tier_id)
                user_usage = get_user_usage(db, owner_id)
            except Exception as e:
                logger.error(f"Error fetching subscription info: {e}")

    stats = {
        "processed_files": total_files,
        "files_today": files_today,
        "files_month": files_month,
        "files_with_ocr": files_with_ocr,
        "unique_users": unique_users,
        "active_integrations": configured_providers,
        "storage_targets": configured_storage_targets,
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "user_usage": user_usage,
            "user_tier": user_tier,
            "multi_user_enabled": settings.multi_user_enabled,
            "is_admin": is_admin,
            "allow_signup": settings.multi_user_enabled and settings.allow_local_signup,
        },
    )


@router.get("/about", include_in_schema=False)
async def serve_about(request: Request):
    """Serve the about page."""
    return templates.TemplateResponse("about.html", {"request": request})


@router.get("/privacy", include_in_schema=False)
async def serve_privacy(request: Request):
    """Serve the privacy policy page."""
    # Pass the current date for the "Last Updated" field
    current_date = date.today().strftime(_DATE_DISPLAY_FORMAT)
    return templates.TemplateResponse("privacy.html", {"request": request, "current_date": current_date})


@router.get("/imprint", include_in_schema=False)
async def serve_imprint(request: Request):
    """Serve the imprint/impressum page."""
    return templates.TemplateResponse("imprint.html", {"request": request})


@router.get("/upload", include_in_schema=False)
@require_login
async def serve_upload(request: Request):
    """Serve the upload page."""
    from app.config import settings

    return templates.TemplateResponse(
        "upload.html",
        {
            "request": request,
            "upload_concurrency": settings.upload_concurrency,
            "upload_queue_delay_ms": settings.upload_queue_delay_ms,
        },
    )


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve the favicon."""
    favicon_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "favicon.ico"
    if not favicon_path.exists():
        # If favicon doesn't exist, return a 404
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(favicon_path)


@router.get("/license", include_in_schema=False)
async def serve_license(request: Request):
    """Serve the license page."""
    # Try multiple possible locations for the license file
    possible_locations = [
        Path(__file__).parent.parent.parent / "LICENSE",  # Repository root
        Path("/app/LICENSE"),  # Docker container path
        Path.home() / "LICENSE",  # Home directory (fallback)
    ]

    license_text = None

    # Try to read from any of the possible locations
    for path in possible_locations:
        try:
            with open(path, "r") as f:
                license_text = f.read()
                break  # File found and read, exit loop
        except (FileNotFoundError, PermissionError):
            continue  # Try next location

    # If license text is still None, use embedded text
    if license_text is None:
        license_text = """
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

This software is licensed under the Apache License 2.0.
The full license text could not be located on this system.
Please visit http://www.apache.org/licenses/LICENSE-2.0 for the complete license text.
"""

    return templates.TemplateResponse("license.html", {"request": request, "license_text": license_text})


@router.get("/cookies", include_in_schema=False)
async def serve_cookies(request: Request):
    """Serve the cookie policy page."""
    current_date = date.today().strftime(_DATE_DISPLAY_FORMAT)
    return templates.TemplateResponse("cookies.html", {"request": request, "current_date": current_date})


@router.get("/terms", include_in_schema=False)
async def serve_terms(request: Request):
    """Serve the terms of service page."""
    current_date = date.today().strftime(_DATE_DISPLAY_FORMAT)
    return templates.TemplateResponse("terms.html", {"request": request, "current_date": current_date})
