"""
API endpoints for managing application settings.
"""

import logging
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.utils.input_validation import (validate_setting_key,
                                        validate_setting_key_format)
from app.utils.settings_service import (SETTING_METADATA,
                                        delete_setting_from_db,
                                        get_all_settings_from_db,
                                        get_audit_log, get_setting_history,
                                        get_setting_metadata,
                                        get_settings_by_category,
                                        rollback_setting, save_setting_to_db,
                                        validate_setting_value)
from app.utils.settings_sync import notify_settings_updated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


def require_admin(request: Request) -> dict:
    """
    Dependency to ensure the user is an admin.
    Raises HTTPException if not admin.

    Returns:
        User dict from session
    """
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return user


DbSession = Annotated[Session, Depends(get_db)]
AdminUser = Annotated[dict, Depends(require_admin)]


class SettingUpdate(BaseModel):
    """Model for updating a setting"""

    key: str = Field(..., description="Setting key")
    value: Optional[str] = Field(None, description="Setting value (None to delete)")


class SettingResponse(BaseModel):
    """Model for setting response"""

    key: str
    value: Optional[str]
    metadata: Dict[str, Any]


class SettingsListResponse(BaseModel):
    """Model for list of settings"""

    settings: Dict[str, Any]
    categories: Dict[str, list]
    db_settings: Dict[str, str]


@router.get("/", response_model=SettingsListResponse)
async def get_settings(request: Request, db: DbSession, admin: AdminUser):
    """
    Get all application settings with metadata.
    Admin only.
    """
    try:
        # Get current runtime settings
        current_settings = {}
        for key in SETTING_METADATA.keys():
            if hasattr(settings, key):
                value = getattr(settings, key)
                current_settings[key] = {
                    "value": value,
                    "metadata": get_setting_metadata(key),
                }

        # Get settings stored in database
        db_settings = get_all_settings_from_db(db)

        # Get settings organized by category
        categories = get_settings_by_category()

        return SettingsListResponse(
            settings=current_settings, categories=categories, db_settings=db_settings
        )
    except Exception as e:
        logger.error(f"Error retrieving settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings",
        )


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, request: Request, db: DbSession, admin: AdminUser):
    """
    Get a specific setting by key.
    Admin only.
    """
    validate_setting_key_format(key)
    try:
        # Get current value
        value = getattr(settings, key, None)

        # Get metadata
        metadata = get_setting_metadata(key)

        return SettingResponse(
            key=key, value=str(value) if value is not None else None, metadata=metadata
        )
    except Exception as e:
        logger.error(f"Error retrieving setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve setting: {key}",
        )


@router.post("/{key}")
async def update_setting(
    key: str,
    setting: SettingUpdate,
    request: Request,
    db: DbSession,
    admin: AdminUser,
):
    """
    Update a specific setting.
    Admin only.
    """
    validate_setting_key(key)
    try:
        # Validate the setting value
        if setting.value is not None:
            is_valid, error_message = validate_setting_value(key, setting.value)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=error_message
                )

        # Determine the username for the audit log
        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "admin"
        )

        # Save to database
        success = save_setting_to_db(db, key, setting.value, changed_by=changed_by)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save setting to database",
            )

        # Notify workers that settings have changed
        notify_settings_updated()

        # Get metadata
        metadata = get_setting_metadata(key)
        restart_required = metadata.get("restart_required", False)

        return {
            "success": True,
            "message": f"Setting '{key}' updated successfully",
            "restart_required": restart_required,
            "key": key,
            "value": setting.value,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update setting: {key}",
        )


@router.delete("/{key}")
async def delete_setting(key: str, request: Request, db: DbSession, admin: AdminUser):
    """
    Delete a setting from the database (reverts to environment variable or default).
    Admin only.
    """
    validate_setting_key(key)
    try:
        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "admin"
        )

        success = delete_setting_from_db(db, key, changed_by=changed_by)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting '{key}' not found in database",
            )

        notify_settings_updated()

        return {
            "success": True,
            "message": f"Setting '{key}' deleted from database (will use environment variable or default)",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete setting: {key}",
        )


@router.get("/credentials")
async def list_credentials(request: Request, db: DbSession, admin: AdminUser):
    """
    List all sensitive credential settings with their configured/unconfigured status.

    Returns a credential audit report indicating which credentials are set and whether
    each value originates from the database or an environment variable.
    This endpoint is intended to support credential rotation workflows.
    Admin only.
    """
    try:
        db_settings = get_all_settings_from_db(db)
        credentials = []

        for key, meta in SETTING_METADATA.items():
            if not meta.get("sensitive", False):
                continue

            env_value = getattr(settings, key, None)
            in_db = key in db_settings and db_settings[key]

            if in_db:
                source = "db"
                configured = True
            elif env_value:
                source = "env"
                configured = True
            else:
                source = None
                configured = False

            credentials.append(
                {
                    "key": key,
                    "category": meta.get("category", "Other"),
                    "description": meta.get("description", ""),
                    "configured": configured,
                    "source": source,
                    "restart_required": meta.get("restart_required", False),
                }
            )

        configured_count = sum(1 for c in credentials if c["configured"])
        return {
            "credentials": credentials,
            "total": len(credentials),
            "configured_count": configured_count,
            "unconfigured_count": len(credentials) - configured_count,
        }
    except Exception as e:
        logger.error(f"Error retrieving credential list: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve credentials",
        )


@router.post("/bulk-update")
async def bulk_update_settings(
    updates: list[SettingUpdate], request: Request, db: DbSession, admin: AdminUser
):
    """
    Update multiple settings at once.
    Admin only.
    """
    results = []
    errors = []

    user = request.session.get("user", {}) if hasattr(request, "session") else {}
    changed_by = (
        user.get("preferred_username")
        or user.get("username")
        or user.get("email")
        or user.get("id")
        or "admin"
    )

    for update in updates:
        try:
            # Validate the setting value
            if update.value is not None:
                is_valid, error_message = validate_setting_value(
                    update.key, update.value
                )
                if not is_valid:
                    errors.append({"key": update.key, "error": error_message})
                    continue

            # Save to database
            success = save_setting_to_db(
                db, update.key, update.value, changed_by=changed_by
            )
            if success:
                results.append(
                    {"key": update.key, "value": update.value, "status": "success"}
                )
            else:
                errors.append(
                    {"key": update.key, "error": "Failed to save to database"}
                )
        except Exception as e:
            logger.error(f"Error updating setting {update.key}: {e}")
            errors.append({"key": update.key, "error": str(e)})

    if results:
        notify_settings_updated()

    restart_required = any(
        get_setting_metadata(result["key"]).get("restart_required", False)
        for result in results
    )

    return {
        "success": len(errors) == 0,
        "updated": results,
        "errors": errors,
        "restart_required": restart_required,
    }


@router.get("/audit-log")
async def list_audit_log(
    request: Request,
    db: DbSession,
    admin: AdminUser,
    limit: int = 100,
    offset: int = 0,
):
    """
    Retrieve the settings audit log (most recent first).

    Returns all configuration changes recorded in the audit log.
    Sensitive values are masked in the response.
    Admin only.
    """
    try:
        entries = get_audit_log(db, limit=limit, offset=offset)
        return {"entries": entries, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"Error retrieving audit log: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit log",
        )


@router.get("/{key}/history")
async def get_key_history(key: str, request: Request, db: DbSession, admin: AdminUser):
    """
    Get the change history for a specific setting key.

    Returns all audit log entries for that key, most recent first.
    Admin only.
    """
    validate_setting_key_format(key)
    try:
        entries = get_setting_history(db, key)
        return {"key": key, "history": entries}
    except Exception as e:
        logger.error(f"Error retrieving history for {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve history for setting: {key}",
        )


@router.post("/{key}/rollback/{history_id}")
async def rollback_setting_to_history(
    key: str,
    history_id: int,
    request: Request,
    db: DbSession,
    admin: AdminUser,
):
    """
    Revert a setting to the value it held at a specific point in the audit log.

    The ``history_id`` is the ID of the :class:`~app.models.SettingsAuditLog`
    entry whose ``new_value`` should be reinstated.  If that entry recorded a
    deletion (``new_value`` is ``None``), the setting is removed from the
    database and reverts to its ENV/default value.

    A new audit log entry is written to record the rollback.
    Admin only.
    """
    validate_setting_key_format(key)
    try:
        user = request.session.get("user", {}) if hasattr(request, "session") else {}
        changed_by = (
            user.get("preferred_username")
            or user.get("username")
            or user.get("email")
            or user.get("id")
            or "admin"
        )

        success = rollback_setting(db, key, history_id, changed_by=changed_by)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"History entry {history_id} not found for setting '{key}'",
            )

        notify_settings_updated()

        return {
            "success": True,
            "message": f"Setting '{key}' rolled back to history entry {history_id}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rolling back setting {key} to history {history_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to roll back setting: {key}",
        )


@router.get("/export-env")
async def export_env_settings(
    request: Request,
    db: DbSession,
    admin: AdminUser,
    source: str = "db",
):
    """
    Export current settings as a ``.env`` file.

    Query params:
    - ``source=db`` (default) – only settings explicitly saved to the database.
    - ``source=effective`` – full runtime configuration (DB > ENV > defaults) for
      every key defined in SETTING_METADATA.

    Returns a downloadable plain-text file suitable for bootstrapping another
    installation.  All values — including sensitive ones — are included; only
    admins can access this endpoint.
    """
    from fastapi.responses import Response as FastAPIResponse

    from app.utils.settings_service import get_settings_for_export

    if source not in ("db", "effective"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source must be 'db' or 'effective'",
        )

    try:
        export_data = get_settings_for_export(db, source=source)
        lines = [
            "# DocuElevate configuration export",
            f"# Source: {source}",
            "# Generated by DocuElevate Settings Export",
            "# WARNING: This file contains sensitive values. Handle with care.",
            "",
        ]
        for env_key, value in export_data.items():
            lines.append(f"{env_key}={value}")
        lines.append("")  # trailing newline
        content = "\n".join(lines)

        return FastAPIResponse(
            content=content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="docuelevate-{source}.env"'
            },
        )
    except Exception as e:
        logger.error(f"Error exporting settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export settings",
        )
