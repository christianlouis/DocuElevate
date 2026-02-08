"""
API endpoints for managing application settings.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.config import settings
from app.utils.settings_service import (
    get_all_settings_from_db,
    save_setting_to_db,
    delete_setting_from_db,
    get_setting_metadata,
    get_settings_by_category,
    validate_setting_value,
    SETTING_METADATA,
)

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
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


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
async def get_settings(
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
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
                    "metadata": get_setting_metadata(key)
                }
        
        # Get settings stored in database
        db_settings = get_all_settings_from_db(db)
        
        # Get settings organized by category
        categories = get_settings_by_category()
        
        return SettingsListResponse(
            settings=current_settings,
            categories=categories,
            db_settings=db_settings
        )
    except Exception as e:
        logger.error(f"Error retrieving settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Get a specific setting by key.
    Admin only.
    """
    try:
        # Get current value
        value = getattr(settings, key, None)
        
        # Get metadata
        metadata = get_setting_metadata(key)
        
        return SettingResponse(
            key=key,
            value=str(value) if value is not None else None,
            metadata=metadata
        )
    except Exception as e:
        logger.error(f"Error retrieving setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve setting: {key}"
        )


@router.post("/{key}")
async def update_setting(
    key: str,
    setting: SettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Update a specific setting.
    Admin only.
    """
    try:
        # Validate the setting value
        if setting.value is not None:
            is_valid, error_message = validate_setting_value(key, setting.value)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_message
                )
        
        # Save to database
        success = save_setting_to_db(db, key, setting.value)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save setting to database"
            )
        
        # Get metadata
        metadata = get_setting_metadata(key)
        restart_required = metadata.get("restart_required", False)
        
        return {
            "success": True,
            "message": f"Setting '{key}' updated successfully",
            "restart_required": restart_required,
            "key": key,
            "value": setting.value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update setting: {key}"
        )


@router.delete("/{key}")
async def delete_setting(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Delete a setting from the database (reverts to environment variable or default).
    Admin only.
    """
    try:
        success = delete_setting_from_db(db, key)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Setting '{key}' not found in database"
            )
        
        return {
            "success": True,
            "message": f"Setting '{key}' deleted from database (will use environment variable or default)"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting setting {key}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete setting: {key}"
        )


@router.post("/bulk-update")
async def bulk_update_settings(
    updates: list[SettingUpdate],
    request: Request,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """
    Update multiple settings at once.
    Admin only.
    """
    results = []
    errors = []
    
    for update in updates:
        try:
            # Validate the setting value
            if update.value is not None:
                is_valid, error_message = validate_setting_value(update.key, update.value)
                if not is_valid:
                    errors.append({
                        "key": update.key,
                        "error": error_message
                    })
                    continue
            
            # Save to database
            success = save_setting_to_db(db, update.key, update.value)
            if success:
                results.append({
                    "key": update.key,
                    "value": update.value,
                    "status": "success"
                })
            else:
                errors.append({
                    "key": update.key,
                    "error": "Failed to save to database"
                })
        except Exception as e:
            logger.error(f"Error updating setting {update.key}: {e}")
            errors.append({
                "key": update.key,
                "error": str(e)
            })
    
    restart_required = any(
        get_setting_metadata(result["key"]).get("restart_required", False)
        for result in results
    )
    
    return {
        "success": len(errors) == 0,
        "updated": results,
        "errors": errors,
        "restart_required": restart_required
    }
