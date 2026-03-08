"""
Backup and restore API endpoints for DocuElevate.

Provides REST endpoints for:
- Listing existing backups
- Triggering a manual backup
- Downloading a backup archive
- Restoring from an uploaded backup file
- Deleting a backup record
- Running retention cleanup
"""

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BackupRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/backup", tags=["backup"])


def _require_admin(request: Request) -> dict:
    """Ensure the caller is an admin.  Raises 403 otherwise."""
    user = request.session.get("user")
    if not user or not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# Annotated shorthand so FastAPI can resolve and tests can override it.
AdminUser = Annotated[dict, Depends(_require_admin)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_backups(
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return all backup records, newest first."""
    records = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "backup_type": r.backup_type,
            "size_bytes": r.size_bytes,
            "checksum": r.checksum,
            "status": r.status,
            "local_path": r.local_path,
            "remote_destination": r.remote_destination,
            "remote_path": r.remote_path,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "local_available": bool(r.local_path and os.path.exists(r.local_path)),
        }
        for r in records
    ]


@router.post("/create")
async def trigger_backup(
    _admin: AdminUser,
    backup_type: str = "hourly",
) -> dict:
    """Trigger a manual backup immediately.

    Query parameter ``backup_type`` accepts ``hourly``, ``daily``, or
    ``weekly`` (default: ``hourly``).
    """
    if backup_type not in ("hourly", "daily", "weekly"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid backup_type")

    from app.tasks.backup_tasks import create_backup

    task = create_backup.delay(backup_type=backup_type)
    return {"task_id": task.id, "status": "queued", "backup_type": backup_type}


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Stream the backup archive to the client."""
    rec = db.get(BackupRecord, backup_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    if not rec.local_path or not os.path.exists(rec.local_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local archive file is not available (may have been pruned)",
        )
    return FileResponse(
        path=rec.local_path,
        filename=rec.filename,
        media_type="application/gzip",
    )


@router.post("/restore")
async def restore_backup(
    _admin: AdminUser,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> dict:
    """Restore the database from an uploaded gzip-compressed SQL dump.

    **Warning**: This overwrites the current database contents.

    Supported formats (must match the currently configured database backend):

    - ``*.db.gz``    – gzip-compressed SQLite ``.dump()`` SQL script (SQLite backend)
    - ``*.pgsql.gz`` – gzip-compressed ``pg_dump --format=plain`` output (PostgreSQL backend)
    - ``*.mysql.gz`` – gzip-compressed ``mysqldump`` output (MySQL / MariaDB backend)
    """
    import tempfile
    from pathlib import Path

    from sqlalchemy.engine.url import make_url

    from app.config import settings as app_settings
    from app.tasks.backup_tasks import (
        _archive_ext_for_backend,
        _db_path,
        _restore_mysql,
        _restore_postgresql,
        _restore_sqlite,
    )

    url = make_url(app_settings.database_url)
    backend = url.get_backend_name()
    expected_ext = _archive_ext_for_backend(backend)

    if not file.filename or not file.filename.endswith(expected_ext):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Uploaded file must be a '{expected_ext}' backup archive for the current database backend ({backend})."
            ),
        )

    # Write upload to a temp file
    with tempfile.NamedTemporaryFile(suffix=expected_ext, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        if backend == "sqlite":
            db_path = _db_path()
            if db_path is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Restore is only supported for file-based SQLite databases.",
                )
            # Close the application DB session before replacing the file
            db.close()
            try:
                _restore_sqlite(db_path, tmp_path)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=str(exc),
                ) from exc

        elif backend == "postgresql":
            db.close()
            try:
                _restore_postgresql(app_settings.database_url, tmp_path)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"psql binary not found – is PostgreSQL client installed? ({exc})",
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"PostgreSQL restore failed: {exc}",
                ) from exc

        elif backend == "mysql":
            db.close()
            try:
                _restore_mysql(app_settings.database_url, tmp_path)
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"mysql binary not found – is MySQL client installed? ({exc})",
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"MySQL restore failed: {exc}",
                ) from exc

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database backend '{backend}' does not support restore.",
            )

    finally:
        tmp_path.unlink(missing_ok=True)

    logger.info(f"Database restored from uploaded backup: {file.filename}")
    return {"status": "restored", "filename": file.filename}


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    _admin: AdminUser,
    db: Session = Depends(get_db),
) -> dict:
    """Delete a backup record (and local file if present)."""
    rec = db.get(BackupRecord, backup_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")

    if rec.local_path and os.path.exists(rec.local_path):
        try:
            os.remove(rec.local_path)
        except OSError as exc:
            logger.warning(f"Could not remove local backup file {rec.local_path}: {exc}")

    db.delete(rec)
    db.commit()
    return {"status": "deleted", "id": backup_id}


@router.post("/cleanup")
async def run_cleanup(_admin: AdminUser) -> dict:
    """Manually trigger the retention cleanup for all backup tiers."""
    from app.tasks.backup_tasks import cleanup_old_backups

    task = cleanup_old_backups.delay()
    return {"task_id": task.id, "status": "queued"}
