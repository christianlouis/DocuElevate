"""Classification Rules API endpoints.

Provides CRUD operations for managing custom document classification rules.
System-wide rules (``owner_id IS NULL``) can only be managed by admins.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import ClassificationRuleModel
from app.utils.classification_rules import (
    BUILTIN_CATEGORIES,
    RULE_TYPE_CONTENT,
    RULE_TYPE_FILENAME,
    RULE_TYPE_METADATA,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/classification-rules", tags=["classification"])

DbSession = Annotated[Session, Depends(get_db)]

_VALID_RULE_TYPES = {RULE_TYPE_FILENAME, RULE_TYPE_CONTENT, RULE_TYPE_METADATA}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_id(request: Request) -> str:
    """Extract the user identifier from the request session."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "get"):
        return user.get("sub") or user.get("email") or "anonymous"
    return "anonymous"


def _is_admin(request: Request) -> bool:
    """Check whether the current user is an admin."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "get"):
        groups = user.get("groups", [])
        return "admin" in groups or "Admin" in groups
    return False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RuleCreate(BaseModel):
    """Schema for creating a classification rule."""

    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    rule_type: str = Field(..., description="One of: filename_pattern, content_keyword, metadata_match")
    pattern: str = Field(..., min_length=1, max_length=1000)
    priority: int = Field(default=0, ge=0, le=1000)
    case_sensitive: bool = False
    enabled: bool = True


class RuleUpdate(BaseModel):
    """Schema for updating a classification rule."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    rule_type: str | None = Field(default=None)
    pattern: str | None = Field(default=None, min_length=1, max_length=1000)
    priority: int | None = Field(default=None, ge=0, le=1000)
    case_sensitive: bool | None = None
    enabled: bool | None = None


class RuleResponse(BaseModel):
    """Schema for a classification rule response."""

    id: int
    owner_id: str | None
    name: str
    category: str
    rule_type: str
    pattern: str
    priority: int
    case_sensitive: bool
    enabled: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/categories")
@require_login
async def list_categories(request: Request) -> dict[str, str]:
    """Return all built-in classification categories.

    Custom categories created via rules are not included here; they are
    discovered dynamically when rules are evaluated.
    """
    return BUILTIN_CATEGORIES


@router.get("/rule-types")
@require_login
async def list_rule_types(request: Request) -> list[dict[str, str]]:
    """Return the supported rule types with descriptions."""
    return [
        {
            "type": RULE_TYPE_FILENAME,
            "label": "Filename Pattern",
            "description": "Regex pattern matched against the original filename.",
        },
        {
            "type": RULE_TYPE_CONTENT,
            "label": "Content Keyword",
            "description": "Pipe-separated keywords matched against the OCR text.",
        },
        {
            "type": RULE_TYPE_METADATA,
            "label": "Metadata Match",
            "description": "field=value pattern matched against existing AI metadata.",
        },
    ]


@router.get("/")
@require_login
async def list_rules(request: Request, db: DbSession) -> list[dict[str, Any]]:
    """List classification rules visible to the current user.

    Returns both system rules (``owner_id IS NULL``) and the user's own rules.
    """
    user_id = _get_user_id(request)
    rules = (
        db.query(ClassificationRuleModel)
        .filter((ClassificationRuleModel.owner_id.is_(None)) | (ClassificationRuleModel.owner_id == user_id))
        .order_by(ClassificationRuleModel.priority.desc(), ClassificationRuleModel.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "owner_id": r.owner_id,
            "name": r.name,
            "category": r.category,
            "rule_type": r.rule_type,
            "pattern": r.pattern,
            "priority": r.priority,
            "case_sensitive": r.case_sensitive,
            "enabled": r.enabled,
        }
        for r in rules
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
@require_login
async def create_rule(request: Request, body: RuleCreate, db: DbSession) -> dict[str, Any]:
    """Create a new custom classification rule.

    The rule is owned by the current user.  Admins may create system-wide
    rules by setting ``owner_id`` to ``null`` (not yet exposed).
    """
    if body.rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rule_type. Must be one of: {', '.join(sorted(_VALID_RULE_TYPES))}",
        )

    user_id = _get_user_id(request)

    # Check for duplicate name within the user's scope
    existing = (
        db.query(ClassificationRuleModel)
        .filter(ClassificationRuleModel.owner_id == user_id, ClassificationRuleModel.name == body.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A rule named '{body.name}' already exists.",
        )

    rule = ClassificationRuleModel(
        owner_id=user_id,
        name=body.name,
        category=body.category,
        rule_type=body.rule_type,
        pattern=body.pattern,
        priority=body.priority,
        case_sensitive=body.case_sensitive,
        enabled=body.enabled,
    )
    try:
        db.add(rule)
        db.commit()
        db.refresh(rule)
    except Exception:
        db.rollback()
        raise

    logger.info("Classification rule created: id=%s, user=%s", rule.id, user_id)
    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "name": rule.name,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "priority": rule.priority,
        "case_sensitive": rule.case_sensitive,
        "enabled": rule.enabled,
    }


@router.get("/{rule_id}")
@require_login
async def get_rule(request: Request, rule_id: int, db: DbSession) -> dict[str, Any]:
    """Get a single classification rule by ID."""
    user_id = _get_user_id(request)
    rule = db.query(ClassificationRuleModel).filter(ClassificationRuleModel.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    # Users can see system rules and their own rules
    if rule.owner_id is not None and rule.owner_id != user_id and not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "name": rule.name,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "priority": rule.priority,
        "case_sensitive": rule.case_sensitive,
        "enabled": rule.enabled,
    }


@router.put("/{rule_id}")
@require_login
async def update_rule(request: Request, rule_id: int, body: RuleUpdate, db: DbSession) -> dict[str, Any]:
    """Update an existing classification rule.

    Users can only update their own rules.  Admins can update any rule.
    """
    user_id = _get_user_id(request)
    rule = db.query(ClassificationRuleModel).filter(ClassificationRuleModel.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    if rule.owner_id != user_id and not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this rule")

    if body.rule_type is not None and body.rule_type not in _VALID_RULE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rule_type. Must be one of: {', '.join(sorted(_VALID_RULE_TYPES))}",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(rule, field_name, value)

    try:
        db.commit()
        db.refresh(rule)
    except Exception:
        db.rollback()
        raise

    logger.info("Classification rule updated: id=%s, user=%s", rule.id, user_id)
    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "name": rule.name,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "priority": rule.priority,
        "case_sensitive": rule.case_sensitive,
        "enabled": rule.enabled,
    }


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
async def delete_rule(request: Request, rule_id: int, db: DbSession) -> None:
    """Delete a classification rule.

    Users can only delete their own rules.  Admins can delete any rule.
    """
    user_id = _get_user_id(request)
    rule = db.query(ClassificationRuleModel).filter(ClassificationRuleModel.id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    if rule.owner_id != user_id and not _is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete this rule")

    try:
        db.delete(rule)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("Classification rule deleted: id=%s, user=%s", rule_id, user_id)
