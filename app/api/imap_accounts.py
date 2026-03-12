"""API endpoints for managing per-user IMAP ingestion accounts.

Provides CRUD operations for a user's IMAP accounts, quota enforcement
against their subscription plan's ``max_mailboxes`` limit, and a
test-connection endpoint so users can verify credentials before saving.
"""

import imaplib
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UserImapAccount
from app.utils.encryption import decrypt_value, encrypt_value
from app.utils.subscription import get_tier, get_user_tier_id
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imap-accounts", tags=["imap-accounts"])

DbSession = Annotated[Session, Depends(get_db)]

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_owner_id(request: Request) -> str:
    """Return the current user's owner ID, raising 401 if unauthenticated."""
    owner_id = get_current_owner_id(request)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return owner_id


CurrentOwner = Annotated[str, Depends(_get_owner_id)]


# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------

_FREE_TIER_ID = "free"


def _get_max_mailboxes(tier: dict[str, Any]) -> int | None:
    """Return the maximum number of IMAP accounts allowed by *tier*.

    Returns:
        ``None``  — unlimited (paid tiers with ``max_mailboxes == 0``)
        ``0``     — no mailboxes allowed (free tier)
        positive  — the configured limit
    """
    tier_id: str = tier.get("id", _FREE_TIER_ID)
    max_mb: int = tier.get("max_mailboxes", 0)

    # Free tier: 0 means "no access" (not "unlimited")
    if tier_id == _FREE_TIER_ID:
        return 0

    # Paid tiers: 0 means unlimited
    if max_mb == 0:
        return None

    return max_mb


def _check_quota(db: Session, owner_id: str) -> None:
    """Raise 403 if the user has reached their IMAP account quota."""
    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id, db)
    max_mb = _get_max_mailboxes(tier)

    if max_mb == 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Your current plan does not include email ingestion. Upgrade to a paid plan to add IMAP accounts."),
        )

    if max_mb is not None:
        current_count = db.query(UserImapAccount).filter(UserImapAccount.owner_id == owner_id).count()
        if current_count >= max_mb:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"You have reached your plan limit of {max_mb} IMAP account(s). "
                    "Please delete an existing account or upgrade your plan."
                ),
            )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ImapAccountCreate(BaseModel):
    """Schema for creating a new IMAP account."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    host: str = Field(..., min_length=1, max_length=255, description="IMAP server hostname")
    port: int = Field(default=993, ge=1, le=65535, description="IMAP server port")
    username: str = Field(..., min_length=1, max_length=255, description="IMAP login username")
    password: str = Field(..., min_length=1, max_length=1024, description="IMAP login password")
    use_ssl: bool = Field(default=True, description="Use SSL/TLS connection")
    delete_after_process: bool = Field(default=False, description="Delete emails from mailbox after processing")
    is_active: bool = Field(default=True, description="Whether to poll this mailbox")
    attachment_filter: str | None = Field(
        default=None,
        description=(
            "Controls which attachment types to ingest. "
            "'documents_only' – PDFs and office files only (default when None). "
            "'all' – all supported types including images. "
            "Null inherits the global imap_attachment_filter setting."
        ),
    )


class ImapAccountUpdate(BaseModel):
    """Schema for updating an existing IMAP account (all fields optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=1024)
    use_ssl: bool | None = None
    delete_after_process: bool | None = None
    is_active: bool | None = None
    attachment_filter: str | None = Field(
        default=None,
        description=(
            "Controls which attachment types to ingest. "
            "'documents_only' – PDFs and office files only. "
            "'all' – all supported types including images. "
            "Null or empty string clears the override (inherits global setting)."
        ),
    )


class ImapTestRequest(BaseModel):
    """Schema for testing an IMAP connection without saving it."""

    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=1024)
    use_ssl: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _to_response(acct: UserImapAccount) -> dict[str, Any]:
    """Serialize a ``UserImapAccount`` row to a response dict.

    Passwords are never included in responses.
    """
    return {
        "id": acct.id,
        "owner_id": acct.owner_id,
        "name": acct.name,
        "host": acct.host,
        "port": acct.port,
        "username": acct.username,
        "use_ssl": acct.use_ssl,
        "delete_after_process": acct.delete_after_process,
        "is_active": acct.is_active,
        "attachment_filter": acct.attachment_filter,
        "last_checked_at": acct.last_checked_at.isoformat() if acct.last_checked_at else None,
        "last_error": acct.last_error,
        "created_at": acct.created_at.isoformat() if acct.created_at else None,
        "updated_at": acct.updated_at.isoformat() if acct.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Connection test helper
# ---------------------------------------------------------------------------


def _test_imap_connection(host: str, port: int, username: str, password: str, use_ssl: bool) -> dict[str, Any]:
    """Attempt to connect and log in to the IMAP server.

    Returns a dict with ``{"success": bool, "message": str}``.
    """
    try:
        if use_ssl:
            mail = imaplib.IMAP4_SSL(host, port)
        else:
            mail = imaplib.IMAP4(host, port)

        mail.login(username, password)
        mail.logout()
        return {"success": True, "message": "Connection successful"}
    except OSError as exc:
        logger.warning("IMAP network error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": f"Connection error: {exc}"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMAP error for %s@%s: %s", username, host, exc)
        return {"success": False, "message": f"IMAP error: {exc}"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/", summary="List IMAP accounts for the current user")
def list_imap_accounts(request: Request, db: DbSession, owner_id: CurrentOwner) -> list[dict[str, Any]]:
    """Return all IMAP accounts belonging to the authenticated user."""
    accounts = db.query(UserImapAccount).filter(UserImapAccount.owner_id == owner_id).order_by(UserImapAccount.id).all()
    return [_to_response(a) for a in accounts]


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new IMAP account")
def create_imap_account(
    request: Request, body: ImapAccountCreate, db: DbSession, owner_id: CurrentOwner
) -> dict[str, Any]:
    """Create a new IMAP ingestion account for the current user.

    Quota is enforced against the user's subscription plan's ``max_mailboxes``
    limit before the account is persisted.
    """
    _check_quota(db, owner_id)

    acct = UserImapAccount(
        owner_id=owner_id,
        name=body.name,
        host=body.host,
        port=body.port,
        username=body.username,
        password=encrypt_value(body.password),
        use_ssl=body.use_ssl,
        delete_after_process=body.delete_after_process,
        is_active=body.is_active,
        attachment_filter=body.attachment_filter or None,
    )
    try:
        db.add(acct)
        db.commit()
        db.refresh(acct)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s created IMAP account %d (%s)", owner_id, acct.id, body.host)
    return _to_response(acct)


@router.get("/{account_id}", summary="Get a single IMAP account")
def get_imap_account(account_id: int, request: Request, db: DbSession, owner_id: CurrentOwner) -> dict[str, Any]:
    """Return a single IMAP account by ID (must belong to the current user)."""
    acct = (
        db.query(UserImapAccount).filter(UserImapAccount.id == account_id, UserImapAccount.owner_id == owner_id).first()
    )
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAP account not found")
    return _to_response(acct)


@router.put("/{account_id}", summary="Update an IMAP account")
def update_imap_account(
    account_id: int,
    request: Request,
    body: ImapAccountUpdate,
    db: DbSession,
    owner_id: CurrentOwner,
) -> dict[str, Any]:
    """Update an existing IMAP account.  Only provided fields are changed."""
    acct = (
        db.query(UserImapAccount).filter(UserImapAccount.id == account_id, UserImapAccount.owner_id == owner_id).first()
    )
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAP account not found")

    if body.name is not None:
        acct.name = body.name
    if body.host is not None:
        acct.host = body.host
    if body.port is not None:
        acct.port = body.port
    if body.username is not None:
        acct.username = body.username
    if body.password is not None:
        acct.password = encrypt_value(body.password)
    if body.use_ssl is not None:
        acct.use_ssl = body.use_ssl
    if body.delete_after_process is not None:
        acct.delete_after_process = body.delete_after_process
    if body.is_active is not None:
        acct.is_active = body.is_active
    # attachment_filter uses a sentinel check: the field is always present in the
    # model (defaulting to None in Pydantic) so we update it unconditionally when
    # the caller sends any value (including explicit null to clear the override).
    # An empty string is normalised to None to avoid storing a non-meaningful value.
    if "attachment_filter" in body.model_fields_set:
        acct.attachment_filter = body.attachment_filter or None

    # Reset last_error so the next poll gives a fresh result
    acct.last_error = None
    acct.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(acct)
    except Exception:
        db.rollback()
        raise

    logger.info("User %s updated IMAP account %d", owner_id, account_id)
    return _to_response(acct)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an IMAP account")
def delete_imap_account(account_id: int, request: Request, db: DbSession, owner_id: CurrentOwner) -> None:
    """Delete an IMAP account permanently."""
    acct = (
        db.query(UserImapAccount).filter(UserImapAccount.id == account_id, UserImapAccount.owner_id == owner_id).first()
    )
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAP account not found")

    try:
        db.delete(acct)
        db.commit()
    except Exception:
        db.rollback()
        raise

    logger.info("User %s deleted IMAP account %d", owner_id, account_id)


@router.post("/{account_id}/test", summary="Test an existing IMAP account's connection")
def test_saved_imap_account(account_id: int, request: Request, db: DbSession, owner_id: CurrentOwner) -> dict[str, Any]:
    """Test the connection for an already-saved IMAP account."""
    acct = (
        db.query(UserImapAccount).filter(UserImapAccount.id == account_id, UserImapAccount.owner_id == owner_id).first()
    )
    if not acct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAP account not found")

    return _test_imap_connection(acct.host, acct.port, acct.username, decrypt_value(acct.password), acct.use_ssl)


@router.post("/test", summary="Test an IMAP connection without saving")
def test_imap_connection(request: Request, body: ImapTestRequest, owner_id: CurrentOwner) -> dict[str, Any]:
    """Test IMAP credentials without persisting anything.

    Useful for the "Test connection" button in the UI before the user saves
    a new account.
    """
    return _test_imap_connection(body.host, body.port, body.username, body.password, body.use_ssl)


@router.get("/quota/", summary="Get IMAP account quota information for the current user")
def get_imap_quota(request: Request, db: DbSession, owner_id: CurrentOwner) -> dict[str, Any]:
    """Return the user's current IMAP account usage vs. their plan quota."""
    tier_id = get_user_tier_id(db, owner_id)
    tier = get_tier(tier_id, db)
    max_mb = _get_max_mailboxes(tier)
    current_count = db.query(UserImapAccount).filter(UserImapAccount.owner_id == owner_id).count()

    return {
        "current_count": current_count,
        "max_mailboxes": max_mb,  # None = unlimited, 0 = not allowed
        "can_add": max_mb is None or (max_mb > 0 and current_count < max_mb),
        "tier_id": tier_id,
        "tier_name": tier.get("name", tier_id),
    }
