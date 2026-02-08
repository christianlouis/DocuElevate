"""
Setup wizard views for initial system configuration.
"""

import logging
import secrets

from fastapi import Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.utils.settings_service import save_setting_to_db
from app.utils.setup_wizard import get_wizard_steps
from app.views.base import APIRouter, get_db, templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/setup")
async def setup_wizard(request: Request, step: int = 1):
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

    return templates.TemplateResponse(
        "setup_wizard.html",
        {
            "request": request,
            "current_step": step,
            "max_step": max_step,
            "settings": current_settings,
            "step_category": step_category,
            "progress_percent": int((step / max_step) * 100),
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
