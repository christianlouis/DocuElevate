"""
General routes for the application homepage and basic pages.
"""

from datetime import date
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.utils.config_validator import get_provider_status, validate_storage_configs
from app.views.base import APIRouter, get_db, logger, require_login, templates

router = APIRouter()


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

    # Query the actual file count from the database
    processed_files = 0
    try:
        # Import the model here to avoid circular imports
        from app.models import FileRecord

        processed_files = db.query(FileRecord.id).count()
    except Exception as e:
        # Log error but continue (don't break the page if DB query fails)
        logger.error(f"Error counting files: {str(e)}")

    # Create stats object to pass to the template
    stats = {
        "processed_files": processed_files,
        "active_integrations": configured_providers,
        "storage_targets": configured_storage_targets,
    }

    return templates.TemplateResponse("index.html", {"request": request, "stats": stats})


@router.get("/about", include_in_schema=False)
async def serve_about(request: Request):
    """Serve the about page."""
    return templates.TemplateResponse("about.html", {"request": request})


@router.get("/privacy", include_in_schema=False)
async def serve_privacy(request: Request):
    """Serve the privacy policy page."""
    # Pass the current date for the "Last Updated" field
    current_date = date.today().strftime("%B %d, %Y")
    return templates.TemplateResponse("privacy.html", {"request": request, "current_date": current_date})


@router.get("/imprint", include_in_schema=False)
async def serve_imprint(request: Request):
    """Serve the imprint/impressum page."""
    return templates.TemplateResponse("imprint.html", {"request": request})


@router.get("/upload", include_in_schema=False)
@require_login
async def serve_upload(request: Request):
    """Serve the upload page."""
    return templates.TemplateResponse("upload.html", {"request": request})


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
    current_date = date.today().strftime("%B %d, %Y")
    return templates.TemplateResponse("cookies.html", {"request": request, "current_date": current_date})


@router.get("/terms", include_in_schema=False)
async def serve_terms(request: Request):
    """Serve the terms of service page."""
    current_date = date.today().strftime("%B %d, %Y")
    return templates.TemplateResponse("terms.html", {"request": request, "current_date": current_date})
