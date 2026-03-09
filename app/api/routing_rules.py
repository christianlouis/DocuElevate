"""Routing rules API endpoints.

Provides full CRUD for pipeline routing rules that conditionally assign
documents to pipelines based on document properties (file type, category,
metadata fields, size, etc.).

Rules are evaluated in ascending ``position`` order.  The first rule whose
condition matches wins and routes the document to the specified target
pipeline.  If no rule matches, the caller falls back to the owner's (or
system) default pipeline.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import Pipeline, PipelineRoutingRule
from app.utils.routing_engine import (
    BUILTIN_FIELDS,
    VALID_OPERATORS,
    _evaluate_condition,
    _resolve_field,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/routing-rules", tags=["routing-rules"])

DbSession = Annotated[Session, Depends(get_db)]

MAX_RULES_PER_OWNER = 100
MAX_NAME_LENGTH = 255


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user_id(request: Request) -> str:
    """Return the authenticated user identifier."""
    user = getattr(request.state, "user", None)
    if user:
        if isinstance(user, dict):
            return user.get("sub", user.get("email", "anonymous"))
        return getattr(user, "sub", getattr(user, "email", "anonymous"))
    return "anonymous"


def _is_admin(request: Request) -> bool:
    """Return ``True`` when the current user has admin privileges."""
    user = getattr(request.state, "user", None)
    if not user:
        return False
    groups = user.get("groups", []) if isinstance(user, dict) else getattr(user, "groups", [])
    return "admin" in groups


def _can_access_rule(rule: PipelineRoutingRule, user_id: str, admin: bool) -> bool:
    """Check whether the user is allowed to read this rule."""
    if admin:
        return True
    return rule.owner_id == user_id


def _can_write_rule(rule: PipelineRoutingRule, user_id: str, admin: bool) -> bool:
    """Check whether the user is allowed to modify this rule."""
    if rule.owner_id is None:
        return admin
    return rule.owner_id == user_id


def _validate_field(field: str) -> None:
    """Raise 422 if the field name is invalid."""
    if field in BUILTIN_FIELDS:
        return
    if field.startswith("metadata.") and len(field) > len("metadata."):
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            f"Invalid field '{field}'. "
            f"Valid built-in fields: {sorted(BUILTIN_FIELDS)}. "
            "For AI metadata, use 'metadata.<key>'."
        ),
    )


def _validate_operator(operator: str) -> None:
    """Raise 422 if the operator is not recognised."""
    if operator not in VALID_OPERATORS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid operator '{operator}'. Valid operators: {sorted(VALID_OPERATORS)}",
        )


def _serialize_rule(rule: PipelineRoutingRule) -> dict[str, Any]:
    """Serialize a routing rule to a JSON-compatible dict."""
    return {
        "id": rule.id,
        "owner_id": rule.owner_id,
        "name": rule.name,
        "position": rule.position,
        "field": rule.field,
        "operator": rule.operator,
        "value": rule.value,
        "target_pipeline_id": rule.target_pipeline_id,
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class RoutingRuleCreate(BaseModel):
    """Request body for creating a routing rule."""

    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    field: str = Field(..., min_length=1, max_length=255)
    operator: str = Field(..., min_length=1, max_length=50)
    value: str = Field(..., max_length=1024)
    target_pipeline_id: int
    position: int | None = None
    is_active: bool = True


class RoutingRuleUpdate(BaseModel):
    """Request body for updating a routing rule."""

    name: str | None = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    field: str | None = Field(None, min_length=1, max_length=255)
    operator: str | None = Field(None, min_length=1, max_length=50)
    value: str | None = Field(None, max_length=1024)
    target_pipeline_id: int | None = None
    position: int | None = None
    is_active: bool | None = None


class RoutingRuleEvaluateRequest(BaseModel):
    """Request body for dry-run rule evaluation."""

    file_type: str | None = None
    filename: str | None = None
    size: int | None = None
    document_type: str | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
@require_login
def list_routing_rules(request: Request, db: DbSession) -> list[dict[str, Any]]:
    """List all routing rules accessible by the current user.

    Returns the user's own rules plus any system-wide rules (``owner_id=NULL``).
    Rules are sorted by position.
    """
    user_id = _get_user_id(request)

    rules = (
        db.query(PipelineRoutingRule)
        .filter((PipelineRoutingRule.owner_id == user_id) | (PipelineRoutingRule.owner_id.is_(None)))
        .order_by(
            PipelineRoutingRule.owner_id.is_(None).asc(),
            PipelineRoutingRule.position.asc(),
        )
        .all()
    )

    return [_serialize_rule(r) for r in rules]


@router.post("", status_code=status.HTTP_201_CREATED)
@require_login
def create_routing_rule(request: Request, db: DbSession, body: RoutingRuleCreate) -> dict[str, Any]:
    """Create a new routing rule for the current user.

    Returns:
        The created routing rule.

    Raises:
        HTTPException 422: If the field or operator is invalid.
        HTTPException 404: If the target pipeline does not exist.
        HTTPException 409: If the maximum number of rules is reached.
    """
    user_id = _get_user_id(request)

    _validate_field(body.field)
    _validate_operator(body.operator)

    # Verify target pipeline exists and is accessible.
    pipeline = db.query(Pipeline).filter(Pipeline.id == body.target_pipeline_id).first()
    if not pipeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target pipeline {body.target_pipeline_id} not found",
        )

    # Enforce per-owner limit.
    count = db.query(PipelineRoutingRule).filter(PipelineRoutingRule.owner_id == user_id).count()
    if count >= MAX_RULES_PER_OWNER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Maximum of {MAX_RULES_PER_OWNER} routing rules per user reached",
        )

    # Auto-assign position if not specified.
    position = body.position
    if position is None:
        max_pos = (
            db.query(PipelineRoutingRule.position)
            .filter(PipelineRoutingRule.owner_id == user_id)
            .order_by(PipelineRoutingRule.position.desc())
            .first()
        )
        position = (max_pos[0] + 1) if max_pos else 0

    rule = PipelineRoutingRule(
        owner_id=user_id,
        name=body.name.strip(),
        position=position,
        field=body.field,
        operator=body.operator,
        value=body.value,
        target_pipeline_id=body.target_pipeline_id,
        is_active=body.is_active,
    )

    try:
        db.add(rule)
        db.commit()
        db.refresh(rule)
    except Exception:
        db.rollback()
        logger.exception("Failed to create routing rule for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create routing rule",
        )

    logger.info("Routing rule created: id=%s, user=%s", rule.id, user_id)
    return _serialize_rule(rule)


@router.get("/operators")
def list_operators() -> dict[str, Any]:
    """Return the list of supported operators and fields.

    This is a public endpoint (no auth required) so that UIs can populate
    dropdowns without hard-coding the catalogue.
    """
    return {
        "operators": sorted(VALID_OPERATORS),
        "builtin_fields": sorted(BUILTIN_FIELDS),
        "metadata_prefix": "metadata.",
    }


@router.post("/evaluate")
@require_login
def evaluate_rules(request: Request, db: DbSession, body: RoutingRuleEvaluateRequest) -> dict[str, Any]:
    """Dry-run rule evaluation against the provided document properties.

    Returns the first matching rule and target pipeline (if any), or
    indicates that no rule matched (default pipeline will be used).
    """
    user_id = _get_user_id(request)

    doc_props: dict[str, Any] = {
        "file_type": body.file_type,
        "filename": body.filename,
        "size": body.size,
        "document_type": body.document_type,
        "metadata": body.metadata or {},
    }

    rules = (
        db.query(PipelineRoutingRule)
        .filter(
            PipelineRoutingRule.is_active.is_(True),
            (PipelineRoutingRule.owner_id == user_id) | (PipelineRoutingRule.owner_id.is_(None)),
        )
        .order_by(
            PipelineRoutingRule.owner_id.is_(None).asc(),
            PipelineRoutingRule.position.asc(),
        )
        .all()
    )

    for rule in rules:
        actual = _resolve_field(rule.field, doc_props)
        if _evaluate_condition(actual, rule.operator, rule.value):
            pipeline = db.query(Pipeline).filter(Pipeline.id == rule.target_pipeline_id).first()
            return {
                "matched": True,
                "rule": _serialize_rule(rule),
                "target_pipeline": {
                    "id": pipeline.id,
                    "name": pipeline.name,
                    "is_active": pipeline.is_active,
                }
                if pipeline
                else None,
            }

    return {"matched": False, "rule": None, "target_pipeline": None}


@router.put("/reorder")
@require_login
def reorder_routing_rules(
    request: Request,
    db: DbSession,
    rule_ids: list[int] = Body(..., embed=True),
) -> list[dict[str, Any]]:
    """Reorder the caller's routing rules.

    Expects a JSON body ``{"rule_ids": [3, 1, 2]}`` where the list
    contains the IDs of the caller's rules in the desired order.
    """
    user_id = _get_user_id(request)

    rules = (
        db.query(PipelineRoutingRule)
        .filter(PipelineRoutingRule.owner_id == user_id, PipelineRoutingRule.id.in_(rule_ids))
        .all()
    )

    rule_map = {r.id: r for r in rules}

    if len(rule_map) != len(rule_ids) or set(rule_map.keys()) != set(rule_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rule_ids must contain exactly the IDs of your routing rules",
        )

    for pos, rid in enumerate(rule_ids):
        rule_map[rid].position = pos

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to reorder routing rules for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reorder routing rules",
        )

    ordered = sorted(rules, key=lambda r: r.position)
    return [_serialize_rule(r) for r in ordered]


@router.get("/{rule_id}")
@require_login
def get_routing_rule(rule_id: int, request: Request, db: DbSession) -> dict[str, Any]:
    """Return a single routing rule by ID."""
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    rule = db.query(PipelineRoutingRule).filter(PipelineRoutingRule.id == rule_id).first()
    if not rule or not _can_access_rule(rule, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")

    return _serialize_rule(rule)


@router.put("/{rule_id}")
@require_login
def update_routing_rule(rule_id: int, request: Request, db: DbSession, body: RoutingRuleUpdate) -> dict[str, Any]:
    """Update a routing rule.

    Only the fields present in the request body are updated.
    """
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    rule = db.query(PipelineRoutingRule).filter(PipelineRoutingRule.id == rule_id).first()
    if not rule or not _can_access_rule(rule, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")

    if not _can_write_rule(rule, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this rule")

    if body.field is not None:
        _validate_field(body.field)
        rule.field = body.field

    if body.operator is not None:
        _validate_operator(body.operator)
        rule.operator = body.operator

    if body.value is not None:
        rule.value = body.value

    if body.name is not None:
        rule.name = body.name.strip()

    if body.target_pipeline_id is not None:
        pipeline = db.query(Pipeline).filter(Pipeline.id == body.target_pipeline_id).first()
        if not pipeline:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target pipeline {body.target_pipeline_id} not found",
            )
        rule.target_pipeline_id = body.target_pipeline_id

    if body.position is not None:
        rule.position = body.position

    if body.is_active is not None:
        rule.is_active = body.is_active

    try:
        db.commit()
        db.refresh(rule)
    except Exception:
        db.rollback()
        logger.exception("Failed to update routing rule id=%s", rule_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update routing rule",
        )

    logger.info("Routing rule updated: id=%s, user=%s", rule_id, user_id)
    return _serialize_rule(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_routing_rule(rule_id: int, request: Request, db: DbSession) -> None:
    """Delete a routing rule."""
    user_id = _get_user_id(request)
    admin = _is_admin(request)

    rule = db.query(PipelineRoutingRule).filter(PipelineRoutingRule.id == rule_id).first()
    if not rule or not _can_access_rule(rule, user_id, admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found")

    if not _can_write_rule(rule, user_id, admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this rule")

    try:
        db.delete(rule)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete routing rule id=%s", rule_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete routing rule",
        )

    logger.info("Routing rule deleted: id=%s, user=%s", rule_id, user_id)
