"""Tenant/Tribe assignment helpers used before document processing starts."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_TENANT_ID,
    QUARANTINE_TRIBE_ID,
    Tenant,
    Tribe,
    TribeMembership,
)


def personal_tribe_id(owner_id: str) -> str:
    """Return a stable opaque ID without exposing the login in file payloads."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:tribe:{DEFAULT_TENANT_ID}:{owner_id}"))


def ensure_document_scope(db: Session, owner_id: str | None) -> tuple[str, str]:
    """Return a valid tenant/Tribe pair and create missing foundation rows.

    Unowned intake is quarantined.  An owner starts in a personal Tribe; a
    later routing decision may move the document to an explicitly selected
    shared Tribe before indexing or delivery.
    """
    tenant = db.get(Tenant, DEFAULT_TENANT_ID)
    if tenant is None:
        db.add(Tenant(id=DEFAULT_TENANT_ID, name="Default tenant"))
        db.flush()

    if owner_id is None:
        tribe_id = QUARANTINE_TRIBE_ID
        tribe = db.get(Tribe, tribe_id)
        if tribe is None:
            db.add(Tribe(id=tribe_id, tenant_id=DEFAULT_TENANT_ID, name="Unassigned intake quarantine"))
            db.flush()
        return DEFAULT_TENANT_ID, tribe_id

    tribe_id = personal_tribe_id(owner_id)
    tribe = db.get(Tribe, tribe_id)
    if tribe is None:
        db.add(Tribe(id=tribe_id, tenant_id=DEFAULT_TENANT_ID, name=f"Personal space for {owner_id}"))
        db.flush()
    membership = (
        db.query(TribeMembership)
        .filter(TribeMembership.tribe_id == tribe_id, TribeMembership.user_id == owner_id)
        .first()
    )
    if membership is None:
        db.add(
            TribeMembership(
                tenant_id=DEFAULT_TENANT_ID,
                tribe_id=tribe_id,
                user_id=owner_id,
                role="admin",
            )
        )
        db.flush()
    return DEFAULT_TENANT_ID, tribe_id
