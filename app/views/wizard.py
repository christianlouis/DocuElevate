"""
Setup wizard views for initial system configuration.
"""

import logging
import secrets

from fastapi import Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.utils.settings_service import save_setting_to_db
from app.utils.settings_sync import notify_settings_updated
from app.utils.setup_wizard import get_wizard_steps
from app.views.base import APIRouter, get_db, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/setup")
async def setup_wizard(request: Request, step: int = 1, db: Session = Depends(get_db)):
    """
    Setup wizard for first-time configuration.

    This wizard guides users through configuring essential settings
    needed for the system to operate properly.
    """
    # Get wizard steps
    wizard_steps = get_wizard_steps()
    max_step = max(wizard_steps.keys())

    # Validate step number
    if step < 1:
        step = 1
    elif step > max_step:
        step = max_step

    # Get settings for current step
    current_settings = wizard_steps.get(step, [])

    # Get step category (all settings in a step should have same category)
    step_category = current_settings[0].get("wizard_category", "Configuration") if current_settings else "Configuration"

    # Enrich settings with current live values
    from app.config import settings as app_settings
    from app.utils.settings_service import get_setting_from_db

    enriched_settings = []
    for s in current_settings:
        key = s["key"]
        db_val = get_setting_from_db(db, key)
        env_val = getattr(app_settings, key, None)
        # Determine current_value and source
        if db_val is not None:
            current_value = db_val
            value_source = "db"
        elif env_val is not None and str(env_val).strip():
            current_value = str(env_val)
            value_source = "env"
        elif s.get("default") is not None:
            current_value = s["default"]
            value_source = "default"
        else:
            current_value = ""
            value_source = "none"
        enriched_settings.append({**s, "current_value": current_value, "value_source": value_source})
    current_settings = enriched_settings

    return templates.TemplateResponse(
        "setup_wizard.html",
        {
            "request": request,
            "current_step": step,
            "max_step": max_step,
            "settings": current_settings,
            "step_category": step_category,
            "progress_percent": int((step / max_step) * 100),
            "setup_skipped": bool(get_setting_from_db(db, "_setup_wizard_skipped")),
        },
    )


@router.post("/setup")
async def setup_wizard_save(request: Request, step: int = Form(...), db: Session = Depends(get_db)):
    """
    Save settings from the current wizard step.
    """
    try:
        # Get form data
        form_data = await request.form()

        # Get settings for current step
        wizard_steps = get_wizard_steps()
        current_settings = wizard_steps.get(step, [])

        # Save each setting from the form
        saved_count = 0
        for setting in current_settings:
            key = setting["key"]
            value = form_data.get(key)

            # Skip empty values unless it's explicitly allowed
            if value and value.strip():
                # Auto-generate session_secret if needed
                if key == "session_secret" and value == "auto-generate":
                    value = secrets.token_hex(32)
                    logger.info("Auto-generated session secret")

                # Save to database
                if save_setting_to_db(db, key, value):
                    saved_count += 1
                    logger.info(f"Setup wizard: Saved {key}")

        logger.info(f"Setup wizard step {step}: Saved {saved_count} settings")

        if saved_count > 0:
            notify_settings_updated()

        # Determine next step
        max_step = max(wizard_steps.keys())
        next_step = step + 1

        if next_step > max_step:
            # Setup complete, redirect to home
            return RedirectResponse(url="/?setup=complete", status_code=303)
        else:
            # Go to next step
            return RedirectResponse(url=f"/setup?step={next_step}", status_code=303)

    except Exception as e:
        logger.error(f"Error saving wizard settings: {e}")
        return RedirectResponse(url=f"/setup?step={step}&error=save_failed", status_code=303)


@router.get("/setup/skip")
async def setup_wizard_skip(request: Request):
    """
    Skip the setup wizard (for advanced users).

    Creates a marker to indicate setup was skipped.
    """
    try:
        db = next(get_db())
        try:
            # Save a marker to indicate setup was skipped
            save_setting_to_db(db, "_setup_wizard_skipped", "true")
            logger.info("Setup wizard skipped by user")
            return RedirectResponse(url="/", status_code=303)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error skipping setup wizard: {e}")
        return RedirectResponse(url="/", status_code=303)


@router.get("/setup/undo-skip")
async def setup_wizard_undo_skip(request: Request, db: Session = Depends(get_db)):
    """
    Undo a previously skipped setup wizard.

    Removes the skip marker from the database so the wizard will be
    presented again on next visit to the home page.  Redirects to
    step 1 of the wizard immediately.
    """
    try:
        from app.utils.settings_service import delete_setting_from_db

        delete_setting_from_db(db, "_setup_wizard_skipped", changed_by="wizard_undo_skip")
        logger.info("Setup wizard skip marker removed; redirecting to wizard")
        return RedirectResponse(url="/setup?step=1", status_code=303)
    except Exception as e:
        logger.error(f"Error undoing setup wizard skip: {e}")
        return RedirectResponse(url="/settings", status_code=303)
