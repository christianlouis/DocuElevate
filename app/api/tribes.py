"""Tenant-safe Tribe membership and invitation management."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Tribe, TribeInvitation, TribeMembership
from app.utils.user_scope import get_current_owner_id

router = APIRouter(prefix="/tribes", tags=["tribes"])
DbSession = Annotated[Session, Depends(get_db)]


class InvitationCreate(BaseModel):
    invitee_id: str = Field(min_length=1, max_length=320)
    role: Literal["member", "routing_manager", "admin"] = "member"
    expires_hours: int = Field(default=168, ge=1, le=24 * 30)


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class MembershipRoleUpdate(BaseModel):
    role: Literal["member", "routing_manager", "admin"]


def _identity_values(request: Request) -> set[str]:
    user = request.session.get("user")
    if not isinstance(user, dict):
        user = getattr(request.state, "api_token_user", None)
    values = {
        str(value).strip().casefold()
        for key in ("sub", "preferred_username", "email", "id")
        if isinstance(user, dict) and (value := user.get(key)) is not None and str(value).strip()
    }
    if owner_id := get_current_owner_id(request):
        values.add(owner_id.strip().casefold())
    return values


def _current_user_id(request: Request) -> str:
    user_id = get_current_owner_id(request)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user_id


def _membership(db: Session, tribe_id: str, user_id: str) -> TribeMembership | None:
    return (
        db.query(TribeMembership)
        .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.user_id == user_id)
        .first()
    )


def _require_membership(db: Session, tribe_id: str, user_id: str) -> TribeMembership:
    membership = _membership(db, tribe_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tribe not found")
    return membership


def _require_admin(db: Session, tribe_id: str, user_id: str) -> TribeMembership:
    membership = _require_membership(db, tribe_id, user_id)
    if membership.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tribe administrator access is required")
    return membership


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    """Normalize database timestamps before comparing them with aware UTC values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invitation_payload(invitation: TribeInvitation, *, token: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "id": invitation.id,
        "tenant_id": invitation.tenant_id,
        "tribe_id": invitation.tribe_id,
        "invitee_id": invitation.invitee_id,
        "role": invitation.role,
        "invited_by": invitation.invited_by,
        "accepted_by": invitation.accepted_by,
        "expires_at": invitation.expires_at.isoformat(),
        "accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
        "revoked_at": invitation.revoked_at.isoformat() if invitation.revoked_at else None,
        "expired": _as_utc(invitation.expires_at) <= now,
    }
    if token is not None:
        payload["token"] = token
    return payload


@router.get("")
def list_tribes(request: Request, db: DbSession) -> list[dict[str, Any]]:
    """List only Tribes the current user belongs to."""
    user_id = _current_user_id(request)
    rows = (
        db.query(TribeMembership, Tribe)
        .join(Tribe, Tribe.id == TribeMembership.tribe_id)
        .filter(TribeMembership.user_id == user_id)
        .order_by(Tribe.name.asc())
        .all()
    )
    return [
        {
            "tenant_id": tribe.tenant_id,
            "tribe_id": tribe.id,
            "name": tribe.name,
            "role": membership.role,
        }
        for membership, tribe in rows
    ]


@router.get("/{tribe_id}/members")
def list_members(request: Request, tribe_id: str, db: DbSession) -> list[dict[str, Any]]:
    user_id = _current_user_id(request)
    _require_membership(db, tribe_id, user_id)
    rows = (
        db.query(TribeMembership)
        .filter(TribeMembership.tribe_id == tribe_id)
        .order_by(TribeMembership.created_at.asc(), TribeMembership.user_id.asc())
        .all()
    )
    return [{"user_id": row.user_id, "role": row.role, "created_at": row.created_at.isoformat()} for row in rows]


@router.post("/{tribe_id}/invitations", status_code=status.HTTP_201_CREATED)
def create_invitation(
    request: Request,
    tribe_id: str,
    body: InvitationCreate,
    db: DbSession,
) -> dict[str, Any]:
    actor_id = _current_user_id(request)
    actor = _require_admin(db, tribe_id, actor_id)
    invitee_id = body.invitee_id.strip()
    if _membership(db, tribe_id, invitee_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This user is already a Tribe member")

    now = datetime.now(timezone.utc)
    active = (
        db.query(TribeInvitation)
        .filter(
            TribeInvitation.tribe_id == tribe_id,
            TribeInvitation.invitee_id == invitee_id,
            TribeInvitation.accepted_at.is_(None),
            TribeInvitation.revoked_at.is_(None),
            TribeInvitation.expires_at > now,
        )
        .all()
    )
    for invitation in active:
        invitation.revoked_at = now

    token = secrets.token_urlsafe(32)
    invitation = TribeInvitation(
        tenant_id=actor.tenant_id,
        tribe_id=actor.tribe_id,
        invitee_id=invitee_id,
        role=body.role,
        token_hash=_hash_token(token),
        invited_by=actor_id,
        expires_at=now + timedelta(hours=body.expires_hours),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return _invitation_payload(invitation, token=token)


@router.get("/{tribe_id}/invitations")
def list_invitations(request: Request, tribe_id: str, db: DbSession) -> list[dict[str, Any]]:
    actor_id = _current_user_id(request)
    _require_admin(db, tribe_id, actor_id)
    rows = (
        db.query(TribeInvitation)
        .filter(TribeInvitation.tribe_id == tribe_id)
        .order_by(TribeInvitation.created_at.desc())
        .all()
    )
    return [_invitation_payload(row) for row in rows]


@router.get("/invitations/pending")
def pending_invitations(request: Request, db: DbSession) -> list[dict[str, Any]]:
    identities = _identity_values(request)
    if not identities:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    now = datetime.now(timezone.utc)
    rows = (
        db.query(TribeInvitation)
        .filter(
            TribeInvitation.accepted_at.is_(None),
            TribeInvitation.revoked_at.is_(None),
            TribeInvitation.expires_at > now,
        )
        .order_by(TribeInvitation.created_at.desc())
        .all()
    )
    return [_invitation_payload(row) for row in rows if row.invitee_id.strip().casefold() in identities]


@router.post("/invitations/accept")
def accept_invitation(request: Request, body: InvitationAccept, db: DbSession) -> dict[str, Any]:
    user_id = _current_user_id(request)
    identities = _identity_values(request)
    invitation = db.query(TribeInvitation).filter(TribeInvitation.token_hash == _hash_token(body.token)).first()
    now = datetime.now(timezone.utc)
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or _as_utc(invitation.expires_at) <= now
        or invitation.invitee_id.strip().casefold() not in identities
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found or no longer valid")

    membership = _membership(db, invitation.tribe_id, user_id)
    if membership is None:
        membership = TribeMembership(
            tenant_id=invitation.tenant_id,
            tribe_id=invitation.tribe_id,
            user_id=user_id,
            role=invitation.role,
        )
        db.add(membership)
    invitation.accepted_by = user_id
    invitation.accepted_at = now
    db.commit()
    return {
        "accepted": True,
        "tenant_id": invitation.tenant_id,
        "tribe_id": invitation.tribe_id,
        "role": membership.role,
    }


@router.post("/{tribe_id}/invitations/{invitation_id}/revoke")
def revoke_invitation(request: Request, tribe_id: str, invitation_id: int, db: DbSession) -> dict[str, bool]:
    actor_id = _current_user_id(request)
    _require_admin(db, tribe_id, actor_id)
    invitation = (
        db.query(TribeInvitation)
        .filter(TribeInvitation.id == invitation_id, TribeInvitation.tribe_id == tribe_id)
        .first()
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accepted invitations cannot be revoked")
    if invitation.revoked_at is None:
        invitation.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"revoked": True}


@router.patch("/{tribe_id}/members/{member_id}")
def update_member_role(
    request: Request,
    tribe_id: str,
    member_id: str,
    body: MembershipRoleUpdate,
    db: DbSession,
) -> dict[str, str]:
    actor_id = _current_user_id(request)
    _require_admin(db, tribe_id, actor_id)
    membership = _membership(db, tribe_id, member_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tribe member not found")
    if membership.role == "admin" and body.role != "admin":
        admin_count = (
            db.query(TribeMembership)
            .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.role == "admin")
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Tribe must retain an administrator")
    membership.role = body.role
    db.commit()
    return {"user_id": membership.user_id, "role": membership.role}


@router.delete("/{tribe_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(request: Request, tribe_id: str, member_id: str, db: DbSession) -> None:
    actor_id = _current_user_id(request)
    _require_admin(db, tribe_id, actor_id)
    membership = _membership(db, tribe_id, member_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tribe member not found")
    if membership.role == "admin":
        admin_count = (
            db.query(TribeMembership)
            .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.role == "admin")
            .count()
        )
        if admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A Tribe must retain an administrator")
    db.delete(membership)
    db.commit()
