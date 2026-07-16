"""
Setup wizard views for initial system configuration.
"""

import logging
from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.utils.settings_service import get_setting_from_db, save_setting_to_db
from app.utils.settings_sync import notify_settings_updated
from app.utils.setup_wizard import get_missing_required_settings, get_wizard_steps, is_setup_required
from app.views.base import APIRouter, get_db, templates

logger = logging.getLogger(__name__)
router = APIRouter()

_BOOTSTRAP_SESSION_KEY = "_setup_wizard_bootstrap"
_COMPLETED_SETTING_KEY = "_setup_wizard_completed"


def _is_admin(request: Request) -> bool:
    user = request.session.get("user")
    return isinstance(user, dict) and bool(user.get("is_admin"))


def _setup_access_allowed(request: Request, db: Session, *, begin_bootstrap: bool = False) -> bool:
    """Allow a genuine first-run browser or an authenticated administrator."""
    if not app_settings.auth_enabled or _is_admin(request):
        return True
    if request.session.get(_BOOTSTRAP_SESSION_KEY) is True:
        return True
    if begin_bootstrap and not get_setting_from_db(db, _COMPLETED_SETTING_KEY) and is_setup_required():
        request.session[_BOOTSTRAP_SESSION_KEY] = True
        return True
    return False


def _login_redirect(request: Request) -> RedirectResponse:
    target = quote(str(request.url.path), safe="/")
    return RedirectResponse(url=f"/login?next={target}", status_code=303)


@router.get("/setup")
async def setup_wizard(request: Request, step: int = 1, db: Session = Depends(get_db)):
    """
    Setup wizard for first-time configuration.

    This wizard guides users through configuring essential settings
    needed for the system to operate properly.
    """
    if not _setup_access_allowed(request, db, begin_bootstrap=step == 1):
        return _login_redirect(request)

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
    from app.utils.config_validator.masking import mask_database_url
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
        if key == "database_url" and current_value:
            current_value = mask_database_url(str(current_value))
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
    if not _setup_access_allowed(request, db):
        return _login_redirect(request)

    try:
        # Get form data
        form_data = await request.form()

        # Get settings for current step
        wizard_steps = get_wizard_steps()
        current_settings = wizard_steps.get(step, [])

        # Fresh installs must not advance past an empty required value. During
        # an admin re-run an existing DB or environment value may be retained.
        for setting in current_settings:
            if not setting.get("required") or setting.get("bootstrap"):
                continue
            key = setting["key"]
            submitted = str(form_data.get(key) or "").strip()
            existing = get_setting_from_db(db, key) or getattr(app_settings, key, None)
            if not submitted and not existing:
                return RedirectResponse(url=f"/setup?step={step}&error=required_missing", status_code=303)

        # Save each setting from the form
        saved_count = 0
        for setting in current_settings:
            key = setting["key"]
            value = form_data.get(key)

            # Bootstrap settings are needed before the database can be read or
            # before encrypted DB values can be decrypted.  Showing their
            # source in the wizard is useful, but persisting them into that same
            # database would create a restart-time chicken-and-egg problem.
            if setting.get("bootstrap"):
                continue

            # Skip empty values unless it's explicitly allowed
            if value and value.strip():
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
            missing = get_missing_required_settings()
            if missing:
                missing_steps = {
                    setting["key"]: setting.get("wizard_step", 1)
                    for settings_for_step in wizard_steps.values()
                    for setting in settings_for_step
                }
                first_missing_step = min(missing_steps.get(key, 1) for key in missing)
                return RedirectResponse(
                    url=f"/setup?step={first_missing_step}&error=required_missing",
                    status_code=303,
                )

            save_setting_to_db(db, _COMPLETED_SETTING_KEY, "true", changed_by="setup_wizard")
            notify_settings_updated()
            request.session.pop(_BOOTSTRAP_SESSION_KEY, None)
            if app_settings.auth_enabled:
                return RedirectResponse(url="/login?setup=complete", status_code=303)
            return RedirectResponse(url="/", status_code=303)
        else:
            # Go to next step
            return RedirectResponse(url=f"/setup?step={next_step}", status_code=303)

    except Exception as e:
        logger.error(f"Error saving wizard settings: {e}")
        return RedirectResponse(url=f"/setup?step={step}&error=save_failed", status_code=303)


@router.post("/setup/skip")
async def setup_wizard_skip(request: Request, db: Session = Depends(get_db)):
    """
    Skip the setup wizard (for advanced users).

    Creates a marker to indicate setup was skipped.
    """
    if app_settings.auth_enabled and not _is_admin(request):
        return _login_redirect(request)
    try:
        save_setting_to_db(db, "_setup_wizard_skipped", "true", changed_by="setup_wizard_admin")
        notify_settings_updated()
        logger.info("Setup wizard skipped by administrator")
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        logger.error(f"Error skipping setup wizard: {e}")
        return RedirectResponse(url="/", status_code=303)


@router.post("/setup/undo-skip")
async def setup_wizard_undo_skip(request: Request, db: Session = Depends(get_db)):
    """
    Undo a previously skipped setup wizard.

    Removes the skip marker from the database so the wizard will be
    presented again on next visit to the home page.  Redirects to
    step 1 of the wizard immediately.
    """
    if app_settings.auth_enabled and not _is_admin(request):
        return _login_redirect(request)
    try:
        from app.utils.settings_service import delete_setting_from_db

        delete_setting_from_db(db, "_setup_wizard_skipped", changed_by="wizard_undo_skip")
        notify_settings_updated()
        logger.info("Setup wizard skip marker removed; redirecting to wizard")
        return RedirectResponse(url="/setup?step=1", status_code=303)
    except Exception as e:
        logger.error(f"Error undoing setup wizard skip: {e}")
        return RedirectResponse(url="/settings", status_code=303)
