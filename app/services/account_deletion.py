"""Transactional, retryable self-service account deletion.

The service deliberately performs a preflight before changing the database:
legal holds, unsafe paths, and shared file references fail closed.  A durable
tombstone fences queued work and stale credentials throughout the lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base
from app.models import AccountDeletionTombstone, DocumentIntake, FileRecord, FileShare, LocalUser, ProviderGrant

CONFIRMATION = "DELETE MY ACCOUNT"


class AccountDeletionError(RuntimeError):
    status_code = 503


class DeletionBlocked(AccountDeletionError):
    status_code = 409


class UnsafeDeletion(AccountDeletionError):
    status_code = 409


def deletion_blocked(db: Session, owner_id: str) -> bool:
    row = db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == owner_id).first()
    return row is not None and row.status in {"deleting", "deleted", "failed"}


def assert_account_active(db: Session, owner_id: str) -> None:
    """Raise when an ingestion/worker must not create new owner data."""
    row = db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == owner_id).first()
    if row is not None and row.status in {"deleting", "deleted", "failed"}:
        raise DeletionBlocked("account deletion is in progress or complete")


def _safe_paths(files: list[FileRecord], workdir: str | Path) -> list[Path]:
    root = Path(workdir).expanduser().resolve()
    paths: list[Path] = []
    seen: set[Path] = set()
    for file in files:
        if file.legal_hold:
            raise DeletionBlocked(f"document {file.id} is under legal hold")
        for raw in (file.local_filename, file.original_file_path, file.processed_file_path, getattr(file, "original_pdfa_path", None), getattr(file, "processed_pdfa_path", None)):
            if not raw:
                continue
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = root / candidate
            # Resolve the parent even when the file has already disappeared.
            resolved = candidate.resolve(strict=False)
            if resolved == root or root not in resolved.parents:
                raise UnsafeDeletion(f"managed file path escapes workdir: {raw}")
            if candidate.is_symlink():
                raise UnsafeDeletion(f"refusing symlink deletion: {raw}")
            if resolved not in seen:
                seen.add(resolved)
                paths.append(candidate)
    return paths


def _delete_mapped_owner_rows(db: Session, owner_id: str) -> int:
    """Delete all explicitly owner/user/principal scoped records.

    Mapping inspection keeps this list in sync with newly introduced scoped
    records while excluding global tables and the lifecycle tombstone.
    """
    deleted = 0
    excluded = {FileRecord, AccountDeletionTombstone, LocalUser}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in {c.__table__.name for c in excluded}:
            continue
        predicates = [table.c[name] == owner_id for name in ("owner_id", "user_id", "principal_id", "invitee_id", "invited_by", "accepted_by") if name in table.c]
        if predicates:
            deleted += db.execute(delete(table).where(or_(*predicates))).rowcount or 0
    return deleted


def _safe_paths_for_sharing(file: FileRecord, workdir: str | Path) -> list[Path]:
    root = Path(workdir).expanduser().resolve()
    paths = []
    for raw in (file.local_filename, file.original_file_path, file.processed_file_path, getattr(file, "original_pdfa_path", None), getattr(file, "processed_pdfa_path", None)):
        if raw:
            path = Path(raw).expanduser()
            paths.append((path if path.is_absolute() else root / path).resolve(strict=False))
    return paths


def _delete_external_indexes(owner_id: str, file_ids: list[int]) -> None:
    if not file_ids:
        return
    from app.utils.meilisearch_client import get_meilisearch_client
    from app.utils.vector_index import QdrantVectorIndex

    client = get_meilisearch_client()
    if client is None:
        raise RuntimeError("Meilisearch unavailable")
    index = client.get_index(settings.meilisearch_index_name)
    for file_id in file_ids:
        task = index.delete_document(file_id)
        result = client.wait_for_task(task.task_uid)
        status = result.status if hasattr(result, "status") else result.get("status")
        if status != "succeeded":
            raise RuntimeError("Meilisearch deletion was not confirmed")
    # A configured Qdrant collection may contain data even if indexing is now disabled.
    QdrantVectorIndex().delete_documents(file_ids, owner_id=owner_id)


def _revoke_apple_grants(db: Session, owner_id: str) -> None:
    import time
    import requests
    from authlib.jose import jwt
    from app.utils.encryption import decrypt_value
    grants = db.query(ProviderGrant).filter_by(owner_id=owner_id, provider="apple").all()
    for grant in grants:
        now = int(time.time())
        secret = jwt.encode({"alg": "ES256", "kid": settings.social_auth_apple_key_id},
            {"iss": settings.social_auth_apple_team_id, "iat": now, "exp": now + 300,
             "aud": "https://appleid.apple.com", "sub": settings.social_auth_apple_client_id},
            settings.social_auth_apple_private_key).decode()
        token = decrypt_value(grant.encrypted_token)
        if not token or token.startswith("enc:"):
            raise RuntimeError("Apple grant decryption unavailable")
        response = requests.post("https://appleid.apple.com/auth/revoke", data={
            "client_id": settings.social_auth_apple_client_id, "client_secret": secret,
            "token": token, "token_type_hint": "refresh_token"}, timeout=15)
        response.raise_for_status()


def delete_account(db: Session, owner_id: str, *, confirmation: str, workdir: str | Path | None = None) -> dict[str, Any]:
    if confirmation != CONFIRMATION:
        raise DeletionBlocked("irreversible confirmation is required")
    if not owner_id or owner_id == "anonymous":
        raise DeletionBlocked("an authenticated owner is required")

    tombstone = db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == owner_id).first()
    if tombstone is not None and tombstone.status == "deleted":
        return {"status": "deleted", "files_deleted": 0, "already_deleted": True}

    # Validate every path and hold before fencing a previously active account.
    files = db.query(FileRecord).filter(FileRecord.owner_id == owner_id).all()
    paths = _safe_paths(files, workdir or settings.workdir)
    path_counts = Counter(str(p.resolve(strict=False)) for f in db.query(FileRecord).filter(FileRecord.owner_id != owner_id).all() for p in _safe_paths_for_sharing(f, workdir or settings.workdir))
    paths = [p for p in paths if str(p.resolve(strict=False)) not in path_counts]
    intake_paths = [Path(i.local_path) for i in db.query(DocumentIntake).filter(DocumentIntake.principal_id == owner_id).all() if i.local_path]
    paths.extend(_safe_paths([type('IntakeFile', (), {'legal_hold': False, 'local_filename': p, 'original_file_path': None, 'processed_file_path': None})() for p in intake_paths], workdir or settings.workdir))
    file_ids = [f.id for f in files]
    if tombstone is None:
        tombstone = AccountDeletionTombstone(owner_id=owner_id, status="deleting")
        db.add(tombstone)
        tombstone.cleanup_manifest = json.dumps({"file_ids": file_ids, "paths": [str(p) for p in paths]})
    elif tombstone.status == "deleting":
        raise DeletionBlocked("account deletion is already running")
    else:
        tombstone.status = "deleting"
        tombstone.error = None
        manifest = json.loads(tombstone.cleanup_manifest or "{}")
        file_ids = manifest.get("file_ids", file_ids)
        paths = [Path(p) for p in manifest.get("paths", [str(p) for p in paths])]
    db.commit()
    try:
        _revoke_apple_grants(db, owner_id)
        _delete_external_indexes(owner_id, file_ids)
    except Exception as exc:
        tombstone.status = "failed"
        tombstone.error = type(exc).__name__
        db.commit()
        raise AccountDeletionError("external index cleanup failed; retry is required") from exc

    # Delete files only after all filesystem preflight has passed.  If unlink
    # fails, the tombstone remains deleting and the retry can safely resume.
    try:
        for path in paths:
            if path.exists():
                path.unlink()
    except Exception as exc:
        tombstone.status = "failed"
        tombstone.error = str(exc)[:2000]
        db.commit()
        raise AccountDeletionError("account cleanup failed; retry is required") from exc

    # Remove dependent derived/search/OCR/share records before the owner row.
    dependent_deleted = 0
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in {FileRecord.__table__.name, AccountDeletionTombstone.__table__.name}:
            continue
        if "file_id" in table.c and file_ids:
            dependent_deleted += db.execute(delete(table).where(table.c.file_id.in_(file_ids))).rowcount or 0
    db.query(FileShare).filter((FileShare.owner_id == owner_id) | (FileShare.shared_with_user_id == owner_id)).delete(synchronize_session=False)
    db.query(FileRecord).filter(FileRecord.owner_id == owner_id).delete(synchronize_session=False)
    dependent_deleted += _delete_mapped_owner_rows(db, owner_id)
    # Local credentials are removed last; bearer/session rows are covered by
    # owner/user scoped deletion above.  OAuth provider copies remain external.
    db.query(LocalUser).filter((LocalUser.email == owner_id) | (LocalUser.username == owner_id)).delete(synchronize_session=False)

    try:
        tombstone.status = "deleted"
        tombstone.cleanup_manifest = None
        tombstone.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        # Preserve a retryable tombstone status in a separate transaction.
        row = db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == owner_id).first()
        if row is not None:
            row.status = "failed"
            row.error = str(exc)[:2000]
            db.commit()
        raise AccountDeletionError("account cleanup failed; retry is required") from exc
    return {"status": "deleted", "files_deleted": len(files), "dependent_records_deleted": dependent_deleted, "external_copies_not_deleted": True}
