"""Transactional, retryable self-service account deletion.

The service deliberately performs a preflight before changing the database:
legal holds, unsafe paths, and shared file references fail closed.  A durable
tombstone fences queued work and stale credentials throughout the lifecycle.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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


def tombstone_key(owner_id: str) -> str:
    """Return a stable pseudonymous deletion fence for a canonical owner."""
    return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()


def deletion_blocked(db: Session, owner_id: str) -> bool:
    row = (
        db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == tombstone_key(owner_id)).first()
    )
    return row is not None and row.status in {"deleting", "deleted", "failed"}


def assert_account_active(db: Session, owner_id: str) -> None:
    """Raise when an ingestion/worker must not create new owner data."""
    row = (
        db.query(AccountDeletionTombstone).filter(AccountDeletionTombstone.owner_id == tombstone_key(owner_id)).first()
    )
    if row is not None and row.status in {"deleting", "deleted", "failed"}:
        raise DeletionBlocked("account deletion is in progress or complete")


def _safe_paths(files: list[FileRecord], workdir: str | Path) -> list[Path]:
    root = Path(workdir).expanduser().resolve()
    paths: list[Path] = []
    seen: set[Path] = set()
    for file in files:
        if file.legal_hold:
            raise DeletionBlocked(f"document {file.id} is under legal hold")
        for raw in (
            file.local_filename,
            file.original_file_path,
            file.processed_file_path,
            getattr(file, "original_pdfa_path", None),
            getattr(file, "processed_pdfa_path", None),
        ):
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
        predicates = [
            table.c[name] == owner_id
            for name in ("owner_id", "user_id", "principal_id", "invitee_id", "invited_by", "accepted_by")
            if name in table.c
        ]
        if predicates:
            deleted += db.execute(delete(table).where(or_(*predicates))).rowcount or 0
    return deleted


def _safe_paths_for_sharing(file: FileRecord, workdir: str | Path) -> list[Path]:
    root = Path(workdir).expanduser().resolve()
    paths = []
    for raw in (
        file.local_filename,
        file.original_file_path,
        file.processed_file_path,
        getattr(file, "original_pdfa_path", None),
        getattr(file, "processed_pdfa_path", None),
    ):
        if raw:
            path = Path(raw).expanduser()
            paths.append((path if path.is_absolute() else root / path).resolve(strict=False))
    return paths


def _delete_external_indexes(owner_id: str, file_ids: list[int]) -> None:
    if not file_ids:
        return
    if not settings.meilisearch_url or not settings.vector_index_url:
        raise RuntimeError("Search or vector endpoint is missing; historical index cleanup cannot be verified")
    import meilisearch

    from app.utils.vector_index import QdrantVectorIndex

    if settings.meilisearch_url:
        client = meilisearch.Client(url=settings.meilisearch_url, api_key=settings.meilisearch_api_key or None)
        try:
            index = client.get_index(settings.meilisearch_index_name)
        except Exception as exc:
            from app.tasks.batch_tasks import _is_missing_search_index_error

            if not _is_missing_search_index_error(exc):
                raise
            index = None
        if index:
            for file_id in file_ids:
                task = index.delete_document(file_id)
                result = client.wait_for_task(task.task_uid)
                status = result.status if hasattr(result, "status") else result.get("status")
                if status != "succeeded":
                    raise RuntimeError("Meilisearch deletion was not confirmed")
    if settings.vector_index_url:
        QdrantVectorIndex().delete_documents(file_ids, owner_id=owner_id)


def _revoke_apple_grants(db: Session, owner_id: str) -> None:
    import time

    import requests
    from authlib.jose import jwt

    from app.utils.encryption import decrypt_value

    grants = db.query(ProviderGrant).filter_by(owner_id=owner_id, provider="apple").all()
    for grant in grants:
        now = int(time.time())
        secret = jwt.encode(
            {"alg": "ES256", "kid": settings.social_auth_apple_key_id},
            {
                "iss": settings.social_auth_apple_team_id,
                "iat": now,
                "exp": now + 300,
                "aud": "https://appleid.apple.com",
                "sub": settings.social_auth_apple_client_id,
            },
            settings.social_auth_apple_private_key,
        ).decode()
        token = decrypt_value(grant.encrypted_token)
        if not token or token.startswith("enc:"):
            raise RuntimeError("Apple grant decryption unavailable")
        response = requests.post(
            "https://appleid.apple.com/auth/revoke",
            data={
                "client_id": settings.social_auth_apple_client_id,
                "client_secret": secret,
                "token": token,
                "token_type_hint": "refresh_token",
            },
            timeout=15,
        )
        response.raise_for_status()


def delete_account(
    db: Session, owner_id: str, *, confirmation: str, workdir: str | Path | None = None
) -> dict[str, Any]:
    if confirmation != CONFIRMATION:
        raise DeletionBlocked("irreversible confirmation is required")
    if not owner_id or owner_id == "anonymous":
        raise DeletionBlocked("an authenticated owner is required")
    from app.services.account_lifecycle_lock import account_lifecycle_lock

    with account_lifecycle_lock(db, owner_id, exclusive=True):
        return _delete_account_locked(db, owner_id, workdir=workdir)


def _delete_account_locked(db: Session, owner_id: str, *, workdir: str | Path | None) -> dict[str, Any]:
    from app.models import (
        DocumentComment,
        DropboxImportObject,
        Pipeline,
        PipelineRoutingRule,
        PipelineStep,
        PipelineVersion,
        UserIntegration,
    )

    tombstone = db.query(AccountDeletionTombstone).filter_by(owner_id=tombstone_key(owner_id)).first()
    if tombstone is not None and tombstone.status == "deleted":
        return {"status": "deleted", "files_deleted": 0, "already_deleted": True}
    fenced = tombstone is not None
    try:
        files = db.query(FileRecord).filter(FileRecord.owner_id == owner_id).all()
        owned_pipeline_ids = db.query(Pipeline.id).filter(Pipeline.owner_id == owner_id)
        foreign_rule = (
            db.query(PipelineRoutingRule.id)
            .filter(
                PipelineRoutingRule.target_pipeline_id.in_(owned_pipeline_ids),
                or_(PipelineRoutingRule.owner_id != owner_id, PipelineRoutingRule.owner_id.is_(None)),
            )
            .first()
        )
        if foreign_rule is not None:
            raise DeletionBlocked(
                "Shared pipeline has routing rules owned by another account; remove or reassign them before deletion"
            )
        root = workdir or settings.workdir
        paths = _safe_paths(files, root)
        intake_paths = [
            i.local_path for i in db.query(DocumentIntake).filter_by(principal_id=owner_id).all() if i.local_path
        ]
        paths.extend(
            _safe_paths(
                [
                    type(
                        "IntakeFile",
                        (),
                        {
                            "legal_hold": False,
                            "local_filename": p,
                            "original_file_path": None,
                            "processed_file_path": None,
                        },
                    )()
                    for p in intake_paths
                ],
                root,
            )
        )
        # SQL != does not include NULL; unowned documents also protect paths.
        others = db.query(FileRecord).filter(or_(FileRecord.owner_id != owner_id, FileRecord.owner_id.is_(None))).all()
        shared = {str(p) for f in others for p in _safe_paths_for_sharing(f, root)}
        for intake in (
            db.query(DocumentIntake)
            .filter(or_(DocumentIntake.principal_id != owner_id, DocumentIntake.principal_id.is_(None)))
            .all()
        ):
            if intake.local_path:
                candidate = Path(intake.local_path).expanduser()
                shared.add(
                    str(
                        (
                            candidate if candidate.is_absolute() else Path(root).expanduser().resolve() / candidate
                        ).resolve(strict=False)
                    )
                )
        paths = [p for p in paths if str(p.resolve(strict=False)) not in shared]
        file_ids = [f.id for f in files]
        if tombstone is None:
            tombstone = AccountDeletionTombstone(owner_id=tombstone_key(owner_id), status="deleting")
            tombstone.cleanup_manifest = json.dumps({"file_ids": file_ids, "paths": [str(p) for p in paths]})
            db.add(tombstone)
        else:
            manifest = json.loads(tombstone.cleanup_manifest or "{}")
            file_ids = manifest.get("file_ids", file_ids)
            # Revalidate retained paths and sharing on every retry.
            raw_paths = manifest.get("paths", [str(p) for p in paths])
            paths = _safe_paths(
                [
                    type(
                        "SavedPath",
                        (),
                        {
                            "legal_hold": False,
                            "local_filename": p,
                            "original_file_path": None,
                            "processed_file_path": None,
                        },
                    )()
                    for p in raw_paths
                ],
                root,
            )
            paths = [p for p in paths if str(p.resolve(strict=False)) not in shared]
            tombstone.status = "deleting"
            tombstone.error = None
        db.commit()
        fenced = True
        _revoke_apple_grants(db, owner_id)
        _delete_external_indexes(owner_id, file_ids)
        for path in paths:
            if path.exists():
                path.unlink()

        # Delete indirect children before their owner-scoped parent rows.
        pipeline_ids = db.query(Pipeline.id).filter(Pipeline.owner_id == owner_id)
        routing_ids = db.query(PipelineRoutingRule.id).filter(PipelineRoutingRule.owner_id == owner_id)
        other_files = or_(FileRecord.owner_id != owner_id, FileRecord.owner_id.is_(None))
        for column, ids in (
            (FileRecord.duplicate_of_id, file_ids),
            (FileRecord.pipeline_id, pipeline_ids),
            (FileRecord.pipeline_routing_rule_id, routing_ids),
        ):
            db.query(FileRecord).filter(other_files, column.in_(ids)).update({column: None}, synchronize_session=False)
        deleted_comment_ids = [
            row[0]
            for row in db.query(DocumentComment.id)
            .filter(or_(DocumentComment.user_id == owner_id, DocumentComment.file_id.in_(file_ids)))
            .all()
        ]
        if deleted_comment_ids:
            db.query(DocumentComment).filter(
                DocumentComment.parent_id.in_(deleted_comment_ids), ~DocumentComment.id.in_(deleted_comment_ids)
            ).update({DocumentComment.parent_id: None}, synchronize_session=False)
        integration_ids = db.query(UserIntegration.id).filter(UserIntegration.owner_id == owner_id)
        intake_ids = db.query(DocumentIntake.id).filter(DocumentIntake.principal_id == owner_id)
        db.query(PipelineStep).filter(PipelineStep.pipeline_id.in_(pipeline_ids)).delete(synchronize_session=False)
        db.query(PipelineVersion).filter(PipelineVersion.pipeline_id.in_(pipeline_ids)).delete(
            synchronize_session=False
        )
        db.query(DropboxImportObject).filter(
            or_(DropboxImportObject.integration_id.in_(integration_ids), DropboxImportObject.intake_id.in_(intake_ids))
        ).delete(synchronize_session=False)
        dependent_deleted = 0
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in {FileRecord.__table__.name, AccountDeletionTombstone.__table__.name}:
                continue
            if "file_id" in table.c and file_ids:
                dependent_deleted += db.execute(delete(table).where(table.c.file_id.in_(file_ids))).rowcount or 0
        db.query(FileShare).filter(
            (FileShare.owner_id == owner_id) | (FileShare.shared_with_user_id == owner_id)
        ).delete(synchronize_session=False)
        db.query(FileRecord).filter(FileRecord.owner_id == owner_id).delete(synchronize_session=False)
        dependent_deleted += _delete_mapped_owner_rows(db, owner_id)
        db.query(LocalUser).filter(LocalUser.email == owner_id).delete(synchronize_session=False)
        tombstone.status = "deleted"
        tombstone.error = None
        tombstone.cleanup_manifest = None
        tombstone.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "status": "deleted",
            "files_deleted": len(file_ids),
            "dependent_records_deleted": dependent_deleted,
            "external_copies_not_deleted": True,
        }
    except Exception as exc:
        db.rollback()
        if not fenced:
            raise
        row = db.query(AccountDeletionTombstone).filter_by(owner_id=tombstone_key(owner_id)).first()
        if row is not None:
            row.status = "failed"
            row.error = type(exc).__name__
            db.commit()
        raise AccountDeletionError(
            "account cleanup could not be verified; check configured services and retry"
        ) from exc
