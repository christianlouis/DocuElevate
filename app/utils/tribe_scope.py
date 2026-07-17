"""Tenant/Tribe assignment helpers used before document processing starts."""

from __future__ import annotations

import unicodedata
import uuid

from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_TENANT_ID,
    QUARANTINE_TRIBE_ID,
    Tenant,
    Tribe,
    TribeMembership,
)


def personal_tribe_id(owner_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """Return a stable opaque ID without exposing the login in file payloads."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:tribe:{tenant_id}:{owner_id}"))


def canonical_tribe_name(name: str) -> str:
    """Return the canonical comparison form for a user-supplied Tribe name."""
    normalized_name = unicodedata.normalize("NFKC", name)
    return " ".join(normalized_name.split()).casefold()


def shared_tribe_id(name: str, tenant_id: str = DEFAULT_TENANT_ID) -> str:
    """Return a stable ID for a named shared Tribe inside one tenant."""
    normalized_name = canonical_tribe_name(name)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:shared-tribe:{tenant_id}:{normalized_name}"))


def ensure_personal_scope(
    db: Session,
    user_id: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> tuple[str, str]:
    """Ensure a user has a personal Tribe proving membership in one tenant."""
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        db.add(Tenant(id=tenant_id, name="Default tenant" if tenant_id == DEFAULT_TENANT_ID else tenant_id))
        db.flush()

    tribe_id = personal_tribe_id(user_id, tenant_id)
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        db.add(Tribe(id=tribe_id, tenant_id=tenant_id, name=f"Personal space for {user_id}"))
        db.flush()
    ensure_tribe_membership(
        db,
        tenant_id=tenant_id,
        tribe_id=tribe_id,
        user_id=user_id,
        role="admin",
    )
    return tenant_id, tribe_id


def ensure_document_scope(db: Session, owner_id: str | None) -> tuple[str, str]:
    """Return a valid tenant/Tribe pair and create missing foundation rows.

    Unowned intake is quarantined.  An owner starts in a personal Tribe; a
    later routing decision may move the document to an explicitly selected
    shared Tribe before indexing or delivery.
    """
    if owner_id is None:
        tenant = db.get(Tenant, DEFAULT_TENANT_ID)
        if tenant is None:
            db.add(Tenant(id=DEFAULT_TENANT_ID, name="Default tenant"))
            db.flush()
        tribe_id = QUARANTINE_TRIBE_ID
        tribe = db.get(Tribe, tribe_id)
        if tribe is None:
            db.add(Tribe(id=tribe_id, tenant_id=DEFAULT_TENANT_ID, name="Unassigned intake quarantine"))
            db.flush()
        return DEFAULT_TENANT_ID, tribe_id

    return ensure_personal_scope(db, owner_id)


def ensure_tribe_membership(
    db: Session,
    *,
    tenant_id: str,
    tribe_id: str,
    user_id: str,
    role: str = "member",
) -> TribeMembership:
    """Return the user's membership, creating it when collaboration grants access."""
    membership = (
        db.query(TribeMembership)
        .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.user_id == user_id)
        .first()
    )
    if membership is None:
        membership = TribeMembership(
            tenant_id=tenant_id,
            tribe_id=tribe_id,
            user_id=user_id,
            role=role,
        )
        db.add(membership)
        db.flush()
    return membership
