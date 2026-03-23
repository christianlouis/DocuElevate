"""File-sharing API endpoints.

Provides CRUD operations for ``FileShare`` records, which grant named
users ``viewer`` or ``editor`` access to a document owned by someone
else.  Only the file owner may create, update, or revoke shares.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import FILE_SHARE_ROLE_VIEWER, FILE_SHARE_ROLES, FileRecord, FileShare, UserProfile
from app.utils.user_scope import get_current_owner_id, get_file_role

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sharing"])

DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_share(share: FileShare) -> dict[str, Any]:
    """Serialize a ``FileShare`` to a JSON-friendly dict."""
    return {
        "id": share.id,
        "file_id": share.file_id,
        "owner_id": share.owner_id,
        "shared_with_user_id": share.shared_with_user_id,
        "role": share.role,
        "created_at": share.created_at.isoformat() if share.created_at else None,
        "updated_at": share.updated_at.isoformat() if share.updated_at else None,
    }


def _require_owner(file_record: FileRecord, user_id: str | None, db: Session) -> None:
    """Raise 403 unless the calling user is the file owner."""
    if get_file_role(file_record, user_id, db) != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the file owner can manage shares",
        )


# ---------------------------------------------------------------------------
# List shares
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/shares")
@require_login
def list_shares(request: Request, file_id: int, db: DbSession):
    """List all shares for a document.

    Only the file owner (or an admin) may call this endpoint.

    Path Parameters:
        file_id: The ID of the document.

    Returns:
        A list of share objects.
    """
    user_id = get_current_owner_id(request)
    user = request.session.get("user")
    is_admin = isinstance(user, dict) and bool(user.get("is_admin"))

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    role = get_file_role(file_record, user_id, db)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if role != "owner" and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the file owner can view shares",
        )

    shares = db.query(FileShare).filter(FileShare.file_id == file_id).all()
    return [_serialize_share(s) for s in shares]


# ---------------------------------------------------------------------------
# Create share
# ---------------------------------------------------------------------------


@router.post("/files/{file_id}/shares", status_code=status.HTTP_201_CREATED)
@require_login
def create_share(
    request: Request,
    file_id: int,
    db: DbSession,
    shared_with_user_id: str = Body(..., embed=True),
    role: str = Body(FILE_SHARE_ROLE_VIEWER, embed=True),
):
    """Share a document with another user.

    Only the file owner may share the document.  Sharing with a user
    that already has access updates their role instead of creating a
    duplicate record.

    Path Parameters:
        file_id: The ID of the document to share.

    Request body (JSON):
        shared_with_user_id: The stable user identifier of the recipient.
        role: ``"viewer"`` (default) or ``"editor"``.

    Returns:
        The created or updated share object.
    """
    owner_id = get_current_owner_id(request)

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    _require_owner(file_record, owner_id, db)

    if role not in FILE_SHARE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of: {', '.join(FILE_SHARE_ROLES)}",
        )

    if not shared_with_user_id or not shared_with_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="shared_with_user_id must be a non-empty string",
        )
    shared_with_user_id = shared_with_user_id.strip()

    # Cannot share with yourself
    if shared_with_user_id == owner_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You cannot share a file with yourself",
        )

    try:
        existing = (
            db.query(FileShare)
            .filter(FileShare.file_id == file_id, FileShare.shared_with_user_id == shared_with_user_id)
            .first()
        )

        if existing:
            # Update role if different
            if existing.role != role:
                existing.role = role
                db.commit()
                db.refresh(existing)
                logger.info(
                    "Share updated: file_id=%s, shared_with=%s, role=%s, by owner=%s",
                    file_id,
                    shared_with_user_id,
                    role,
                    owner_id,
                )
            return _serialize_share(existing)

        share = FileShare(
            file_id=file_id,
            owner_id=owner_id,
            shared_with_user_id=shared_with_user_id,
            role=role,
        )
        db.add(share)
        db.commit()
        db.refresh(share)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Failed to create share: file_id=%s, shared_with=%s", file_id, shared_with_user_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create share",
        )

    logger.info(
        "Share created: id=%s, file_id=%s, shared_with=%s, role=%s, by owner=%s",
        share.id,
        file_id,
        shared_with_user_id,
        role,
        owner_id,
    )
    return _serialize_share(share)


# ---------------------------------------------------------------------------
# Update share role
# ---------------------------------------------------------------------------


@router.put("/files/{file_id}/shares/{share_id}")
@require_login
def update_share(
    request: Request,
    file_id: int,
    share_id: int,
    db: DbSession,
    role: str = Body(..., embed=True),
):
    """Update the role of an existing share.

    Only the file owner may change the role of a share.

    Path Parameters:
        file_id: The ID of the document.
        share_id: The ID of the share record to update.

    Request body (JSON):
        role: New role — ``"viewer"`` or ``"editor"``.

    Returns:
        The updated share object.
    """
    owner_id = get_current_owner_id(request)

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    _require_owner(file_record, owner_id, db)

    if role not in FILE_SHARE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of: {', '.join(FILE_SHARE_ROLES)}",
        )

    share = db.query(FileShare).filter(FileShare.id == share_id, FileShare.file_id == file_id).first()
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

    try:
        share.role = role
        db.commit()
        db.refresh(share)
    except Exception:
        db.rollback()
        logger.exception("Failed to update share: share_id=%s", share_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update share",
        )

    logger.info("Share updated: id=%s, file_id=%s, new_role=%s, by owner=%s", share_id, file_id, role, owner_id)
    return _serialize_share(share)


# ---------------------------------------------------------------------------
# Revoke share
# ---------------------------------------------------------------------------


@router.delete("/files/{file_id}/shares/{share_id}", status_code=status.HTTP_200_OK)
@require_login
def revoke_share(request: Request, file_id: int, share_id: int, db: DbSession):
    """Revoke a share, removing the user's access.

    Only the file owner may revoke shares.

    Path Parameters:
        file_id: The ID of the document.
        share_id: The ID of the share record to delete.

    Returns:
        A success message.
    """
    owner_id = get_current_owner_id(request)

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    _require_owner(file_record, owner_id, db)

    share = db.query(FileShare).filter(FileShare.id == share_id, FileShare.file_id == file_id).first()
    if not share:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

    try:
        db.delete(share)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to revoke share: share_id=%s", share_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke share",
        )

    logger.info("Share revoked: id=%s, file_id=%s, by owner=%s", share_id, file_id, owner_id)
    return {"status": "success", "message": "Share revoked successfully"}


# ---------------------------------------------------------------------------
# List users that the file is already shared with  (for the share-picker UI)
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/shared-with")
@require_login
def list_shared_with(request: Request, file_id: int, db: DbSession):
    """Return the list of users a document is shared with and their roles.

    Accessible to any user that has at least viewer access to the file,
    so that editors/viewers can see who else has access.

    Path Parameters:
        file_id: The ID of the document.

    Returns:
        A list of ``{share_id, user_id, display_name, role}`` objects.
    """
    user_id = get_current_owner_id(request)
    user = request.session.get("user")
    is_admin = isinstance(user, dict) and bool(user.get("is_admin"))

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    role = get_file_role(file_record, user_id, db)
    if role is None and not is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    shares = db.query(FileShare).filter(FileShare.file_id == file_id).all()

    results = []
    for s in shares:
        profile = db.query(UserProfile).filter(UserProfile.user_id == s.shared_with_user_id).first()
        results.append(
            {
                "share_id": s.id,
                "user_id": s.shared_with_user_id,
                "display_name": (profile.display_name if profile and profile.display_name else s.shared_with_user_id),
                "role": s.role,
            }
        )
    return results
