"""Owner-only automatic privacy rules for the canonical file private flag."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import FileRecord, PrivacyDecisionAudit, PrivacyRuleModel
from app.utils.file_privacy import apply_privacy_decision, queue_privacy_reconciliation
from app.utils.privacy_rules import SINGLE_USER_PRIVACY_OWNER, VALID_RULE_TYPES, match_rule_to_file
from app.utils.user_scope import get_current_owner_id

router = APIRouter(prefix="/privacy-rules", tags=["privacy"])
DbSession = Annotated[Session, Depends(get_db)]


class PrivacyRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    rule_type: str
    pattern: str = Field(..., min_length=1, max_length=1000)
    priority: int = Field(default=0, ge=0, le=1000)
    case_sensitive: bool = False
    enabled: bool = True


class PrivacyRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    rule_type: str | None = None
    pattern: str | None = Field(default=None, min_length=1, max_length=1000)
    priority: int | None = Field(default=None, ge=0, le=1000)
    case_sensitive: bool | None = None
    enabled: bool | None = None


def _serialize(rule: PrivacyRuleModel) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "priority": rule.priority,
        "case_sensitive": rule.case_sensitive,
        "enabled": rule.enabled,
        "policy_version": rule.policy_version,
    }


def _privacy_owner_id(request: Request) -> str:
    """Return an owner scope, including a stable single-user sentinel."""
    owner_id = get_current_owner_id(request)
    if owner_id:
        return owner_id
    from app.config import settings

    if not settings.multi_user_enabled:
        return SINGLE_USER_PRIVACY_OWNER
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authenticated owner required")


def _owned_rule(db: Session, owner_id: str, rule_id: int) -> PrivacyRuleModel:
    rule = (
        db.query(PrivacyRuleModel).filter(PrivacyRuleModel.id == rule_id, PrivacyRuleModel.owner_id == owner_id).first()
    )
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Privacy rule not found")
    return rule


def _validate_type(rule_type: str) -> None:
    if rule_type not in VALID_RULE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rule_type. Must be one of: {', '.join(sorted(VALID_RULE_TYPES))}",
        )


def _validate_pattern(rule_type: str, pattern: str) -> None:
    if rule_type == "filename_pattern":
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename pattern") from exc
    if rule_type == "metadata_match" and "=" not in pattern:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Metadata rules require field=value")


@router.get("/")
@require_login
def list_privacy_rules(request: Request, db: DbSession) -> list[dict[str, Any]]:
    owner_id = _privacy_owner_id(request)
    rules = (
        db.query(PrivacyRuleModel)
        .filter(PrivacyRuleModel.owner_id == owner_id)
        .order_by(PrivacyRuleModel.priority.desc(), PrivacyRuleModel.id)
        .all()
    )
    return [_serialize(rule) for rule in rules]


@router.post("/", status_code=status.HTTP_201_CREATED)
@require_login
def create_privacy_rule(request: Request, body: PrivacyRuleCreate, db: DbSession) -> dict[str, Any]:
    _validate_type(body.rule_type)
    _validate_pattern(body.rule_type, body.pattern)
    owner_id = _privacy_owner_id(request)
    duplicate = (
        db.query(PrivacyRuleModel)
        .filter(PrivacyRuleModel.owner_id == owner_id, PrivacyRuleModel.name == body.name)
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A privacy rule with this name exists")
    rule = PrivacyRuleModel(owner_id=owner_id, **body.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


@router.get("/{rule_id}")
@require_login
def get_privacy_rule(request: Request, rule_id: int, db: DbSession) -> dict[str, Any]:
    return _serialize(_owned_rule(db, _privacy_owner_id(request), rule_id))


@router.put("/{rule_id}")
@require_login
def update_privacy_rule(
    request: Request,
    rule_id: int,
    body: PrivacyRuleUpdate,
    db: DbSession,
) -> dict[str, Any]:
    owner_id = _privacy_owner_id(request)
    rule = _owned_rule(db, owner_id, rule_id)
    changes = body.model_dump(exclude_unset=True)
    if "rule_type" in changes:
        _validate_type(changes["rule_type"])
    effective_type = changes.get("rule_type", rule.rule_type)
    effective_pattern = changes.get("pattern", rule.pattern)
    _validate_pattern(effective_type, effective_pattern)
    if "name" in changes:
        duplicate = (
            db.query(PrivacyRuleModel)
            .filter(
                PrivacyRuleModel.owner_id == owner_id,
                PrivacyRuleModel.name == changes["name"],
                PrivacyRuleModel.id != rule.id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A privacy rule with this name exists")
    for key, value in changes.items():
        setattr(rule, key, value)
    if changes:
        rule.policy_version += 1
    db.commit()
    db.refresh(rule)
    return _serialize(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_privacy_rule(request: Request, rule_id: int, db: DbSession) -> None:
    rule = _owned_rule(db, _privacy_owner_id(request), rule_id)
    db.query(PrivacyDecisionAudit).filter(PrivacyDecisionAudit.rule_id == rule.id).update(
        {PrivacyDecisionAudit.rule_id: None}, synchronize_session=False
    )
    db.delete(rule)
    db.commit()


def _matching_files(
    db: Session,
    owner_id: str,
    rule: PrivacyRuleModel,
    *,
    limit: int,
) -> list[tuple[FileRecord, Any]]:
    query = db.query(FileRecord)
    query = (
        query.filter(FileRecord.owner_id.is_(None))
        if owner_id == SINGLE_USER_PRIVACY_OWNER
        else query.filter(FileRecord.owner_id == owner_id)
    )
    files = query.order_by(FileRecord.id).limit(limit).all()
    matches = []
    for file_record in files:
        match = match_rule_to_file(rule, file_record)
        if match.matched:
            matches.append((file_record, match))
    return matches


@router.post("/{rule_id}/preview")
@require_login
def preview_privacy_rule(
    request: Request,
    rule_id: int,
    db: DbSession,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict[str, Any]:
    owner_id = _privacy_owner_id(request)
    rule = _owned_rule(db, owner_id, rule_id)
    matches = _matching_files(db, owner_id, rule, limit=limit)
    return {
        "rule_id": rule.id,
        "examined_limit": limit,
        "match_count": len(matches),
        "matches": [
            {
                "file_id": file_record.id,
                "filename": file_record.original_filename,
                "title": file_record.document_title,
                "is_private": file_record.is_private,
                "manual_override": file_record.privacy_manual_override is not None,
                "evidence": match.evidence,
                "confidence": match.confidence,
            }
            for file_record, match in matches
        ],
    }


@router.post("/{rule_id}/apply")
@require_login
def apply_privacy_rule(
    request: Request,
    rule_id: int,
    db: DbSession,
    limit: int = Query(default=5000, ge=1, le=25000),
) -> dict[str, Any]:
    owner_id = _privacy_owner_id(request)
    rule = _owned_rule(db, owner_id, rule_id)
    if not rule.enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Enable the rule before applying it")

    changed_ids: list[int] = []
    skipped_manual = 0
    skipped_ownerless = 0
    for file_record, match in _matching_files(db, owner_id, rule, limit=limit):
        if file_record.owner_id is None:
            skipped_ownerless += 1
            continue
        if file_record.privacy_manual_override is not None:
            skipped_manual += 1
            continue
        if file_record.is_private:
            continue
        apply_privacy_decision(
            db,
            file_record,
            is_private=True,
            source="rule",
            manual_override=None,
            rule=rule,
            match=match,
            decision_owner_id=owner_id,
        )
        changed_ids.append(file_record.id)

    db.commit()
    queue_privacy_reconciliation(changed_ids)
    return {
        "rule_id": rule.id,
        "changed_count": len(changed_ids),
        "changed_file_ids": changed_ids,
        "skipped_manual_override": skipped_manual,
        "skipped_ownerless": skipped_ownerless,
    }
