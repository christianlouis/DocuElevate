"""Tribe-scoped recipient profiles, policy and explainable classifications."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.tribes import _current_user_id, _require_membership
from app.database import get_db
from app.models import (
    DocumentRecipientDecision,
    FileRecord,
    RecipientIdentityProfile,
    RecipientRoutingPolicy,
    TribeMembership,
)
from app.utils.recipient_classifier import classify_recipient
from app.utils.user_scope import get_file_role

router = APIRouter(prefix="/tribes/{tribe_id}/recipients", tags=["recipient-identities"])
DbSession = Annotated[Session, Depends(get_db)]


class RecipientProfileBody(BaseModel):
    profile_type: Literal["person", "household"] = "person"
    display_name: str = Field(min_length=1, max_length=255)
    user_ids: list[str] = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    postal_addresses: list[str] = Field(default_factory=list)
    email_addresses: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_members(self) -> "RecipientProfileBody":
        self.user_ids = sorted({value.strip() for value in self.user_ids if value.strip()})
        if not self.user_ids:
            raise ValueError("At least one recipient user is required")
        if self.profile_type == "person" and len(self.user_ids) != 1:
            raise ValueError("A person profile must identify exactly one user")
        return self


class RecipientPolicyBody(BaseModel):
    auto_assign_threshold: int = Field(default=80, ge=1, le=100)
    review_threshold: int = Field(default=45, ge=0, le=100)
    minimum_margin: int = Field(default=15, ge=0, le=100)
    ai_fallback_enabled: bool = False
    ai_model: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "RecipientPolicyBody":
        if self.review_threshold > self.auto_assign_threshold:
            raise ValueError("review_threshold cannot exceed auto_assign_threshold")
        if self.ai_fallback_enabled and not (self.ai_model or "").strip():
            raise ValueError("ai_model is required when AI fallback is enabled")
        return self


class RecipientDryRunBody(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    text: str = Field(default="", max_length=100_000)


def _json(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _require_manager(db: Session, tribe_id: str, user_id: str) -> TribeMembership:
    membership = _require_membership(db, tribe_id, user_id)
    if membership.role not in {"admin", "routing_manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tribe routing manager access is required")
    return membership


def _validate_user_ids(db: Session, tribe_id: str, user_ids: list[str]) -> None:
    members = {
        row.user_id
        for row in db.query(TribeMembership)
        .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.user_id.in_(user_ids))
        .all()
    }
    unknown = sorted(set(user_ids) - members)
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown_tribe_members": unknown})


def _profile_payload(row: RecipientIdentityProfile) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "tribe_id": row.tribe_id,
        "profile_type": row.profile_type,
        "display_name": row.display_name,
        "user_ids": _json(row.user_ids),
        "aliases": _json(row.aliases),
        "postal_addresses": _json(row.postal_addresses),
        "email_addresses": _json(row.email_addresses),
        "identifiers": _json(row.identifiers),
        "is_active": row.is_active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _apply_profile_body(row: RecipientIdentityProfile, body: RecipientProfileBody) -> None:
    row.profile_type = body.profile_type
    row.display_name = body.display_name.strip()
    row.user_ids = json.dumps(body.user_ids)
    row.aliases = json.dumps(sorted({value.strip() for value in body.aliases if value.strip()}), ensure_ascii=False)
    row.postal_addresses = json.dumps(
        sorted({value.strip() for value in body.postal_addresses if value.strip()}), ensure_ascii=False
    )
    row.email_addresses = json.dumps(
        sorted({value.strip().casefold() for value in body.email_addresses if value.strip()}), ensure_ascii=False
    )
    row.identifiers = json.dumps(
        sorted({value.strip() for value in body.identifiers if value.strip()}), ensure_ascii=False
    )
    row.is_active = body.is_active


@router.get("/profiles")
def list_profiles(request: Request, tribe_id: str, db: DbSession) -> list[dict[str, Any]]:
    _require_manager(db, tribe_id, _current_user_id(request))
    rows = (
        db.query(RecipientIdentityProfile)
        .filter(RecipientIdentityProfile.tribe_id == tribe_id)
        .order_by(RecipientIdentityProfile.display_name.asc())
        .all()
    )
    return [_profile_payload(row) for row in rows]


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
def create_profile(request: Request, tribe_id: str, body: RecipientProfileBody, db: DbSession) -> dict[str, Any]:
    actor_id = _current_user_id(request)
    membership = _require_manager(db, tribe_id, actor_id)
    _validate_user_ids(db, tribe_id, body.user_ids)
    row = RecipientIdentityProfile(
        tenant_id=membership.tenant_id,
        tribe_id=tribe_id,
        display_name=body.display_name.strip(),
        created_by=actor_id,
    )
    _apply_profile_body(row, body)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A recipient profile with this name already exists") from exc
    db.refresh(row)
    return _profile_payload(row)


@router.put("/profiles/{profile_id}")
def update_profile(
    request: Request,
    tribe_id: str,
    profile_id: int,
    body: RecipientProfileBody,
    db: DbSession,
) -> dict[str, Any]:
    actor_id = _current_user_id(request)
    _require_manager(db, tribe_id, actor_id)
    _validate_user_ids(db, tribe_id, body.user_ids)
    row = (
        db.query(RecipientIdentityProfile)
        .filter(RecipientIdentityProfile.id == profile_id, RecipientIdentityProfile.tribe_id == tribe_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Recipient profile not found")
    _apply_profile_body(row, body)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A recipient profile with this name already exists") from exc
    db.refresh(row)
    return _profile_payload(row)


def _policy_payload(row: RecipientRoutingPolicy | None, tribe_id: str) -> dict[str, Any]:
    return {
        "tribe_id": tribe_id,
        "auto_assign_threshold": row.auto_assign_threshold if row else 80,
        "review_threshold": row.review_threshold if row else 45,
        "minimum_margin": row.minimum_margin if row else 15,
        "ai_fallback_enabled": row.ai_fallback_enabled if row else False,
        "ai_model": row.ai_model if row else None,
    }


@router.get("/policy")
def get_policy(request: Request, tribe_id: str, db: DbSession) -> dict[str, Any]:
    _require_membership(db, tribe_id, _current_user_id(request))
    return _policy_payload(db.query(RecipientRoutingPolicy).filter_by(tribe_id=tribe_id).first(), tribe_id)


@router.put("/policy")
def update_policy(request: Request, tribe_id: str, body: RecipientPolicyBody, db: DbSession) -> dict[str, Any]:
    actor_id = _current_user_id(request)
    membership = _require_manager(db, tribe_id, actor_id)
    row = db.query(RecipientRoutingPolicy).filter_by(tribe_id=tribe_id).first()
    if row is None:
        row = RecipientRoutingPolicy(tribe_id=tribe_id, tenant_id=membership.tenant_id, updated_by=actor_id)
        db.add(row)
    row.auto_assign_threshold = body.auto_assign_threshold
    row.review_threshold = body.review_threshold
    row.minimum_margin = body.minimum_margin
    row.ai_fallback_enabled = body.ai_fallback_enabled
    row.ai_model = body.ai_model.strip() if body.ai_model else None
    row.updated_by = actor_id
    db.commit()
    db.refresh(row)
    return _policy_payload(row, tribe_id)


@router.post("/dry-run")
def dry_run(request: Request, tribe_id: str, body: RecipientDryRunBody, db: DbSession) -> dict[str, Any]:
    actor_id = _current_user_id(request)
    membership = _require_manager(db, tribe_id, actor_id)
    transient = FileRecord(
        id=-1,
        owner_id=actor_id,
        tenant_id=membership.tenant_id,
        tribe_id=tribe_id,
        filehash="dry-run",
        local_filename="dry-run.pdf",
        file_size=0,
    )
    return classify_recipient(db, transient, body.metadata, body.text).as_dict()


@router.get("/files/{file_id}/decision")
def get_decision(request: Request, tribe_id: str, file_id: int, db: DbSession) -> dict[str, Any]:
    user_id = _current_user_id(request)
    _require_membership(db, tribe_id, user_id)
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id, FileRecord.tribe_id == tribe_id).first()
    if file_record is None or get_file_role(file_record, user_id, db) is None:
        raise HTTPException(status_code=404, detail="Recipient decision not found")
    row = (
        db.query(DocumentRecipientDecision)
        .filter(DocumentRecipientDecision.file_id == file_id, DocumentRecipientDecision.tribe_id == tribe_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Recipient decision not found")
    return {
        "file_id": row.file_id,
        "tenant_id": row.tenant_id,
        "tribe_id": row.tribe_id,
        "status": row.status,
        "recipient_user_ids": _json(row.recipient_user_ids),
        "matched_profile_ids": _json(row.matched_profile_ids),
        "candidates": _json(row.candidates),
        "evidence": _json(row.evidence),
        "confidence": row.confidence,
        "strategy": row.strategy,
        "classifier_version": row.classifier_version,
    }
