"""Authenticated account lifecycle endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.services.account_deletion import CONFIRMATION, AccountDeletionError, delete_account
from app.utils.user_scope import get_current_owner_id

router = APIRouter(prefix="/account", tags=["account"])
DbSession = Annotated[Session, Depends(get_db)]


class AccountDeletionRequest(BaseModel):
    # Deliberately human-readable and impossible to submit accidentally.
    confirmation: str


@router.delete("", status_code=status.HTTP_200_OK)
@require_login
async def delete_my_account(request: Request, payload: AccountDeletionRequest, db: DbSession):
    """Permanently delete the authenticated account and owned data.

    Browser requests remain subject to the application's CSRF middleware;
    mobile clients may authenticate with the existing Bearer-token path.
    """
    owner_id = get_current_owner_id(request)
    if not owner_id or owner_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        result = delete_account(db, owner_id, confirmation=payload.confirmation)
    except AccountDeletionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    request.session.clear()
    return {"confirmation_required": CONFIRMATION, **result}


@router.get("")
@require_login
async def account_deletion_status(request: Request, db: DbSession):
    from app.models import AccountDeletionTombstone
    from app.services.account_deletion import tombstone_key

    owner_id = get_current_owner_id(request)
    if not owner_id or owner_id == "anonymous":
        raise HTTPException(status_code=401, detail="Authentication required")
    row = (
        db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == tombstone_key(owner_id)).first()
    )
    return {"status": row.status if row else "active"}
