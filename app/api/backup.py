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
    Only SQLite databases are supported.

    The uploaded file must be a ``.db.gz`` file produced by the DocuElevate
    backup task (a gzip-compressed SQLite ``.dump()`` SQL script).
    """
    from app.tasks.backup_tasks import _db_path

    db_path = _db_path()
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore is only supported for SQLite databases.",
        )

    if not file.filename or not file.filename.endswith(".db.gz"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must be a .db.gz backup archive.",
        )

    import gzip
    import sqlite3
    import tempfile
    from pathlib import Path

    # Write the upload to a temp file first so we can validate it
    with tempfile.NamedTemporaryFile(suffix=".db.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        content = await file.read()
        tmp.write(content)

    try:
        # Decompress and read SQL statements
        with gzip.open(str(tmp_path), "rt", encoding="utf-8") as gz:
            sql_script = gz.read()
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to decompress backup file: {exc}",
        ) from exc

    # Create a fresh in-memory DB from the script to validate it
    try:
        mem_conn = sqlite3.connect(":memory:")
        mem_conn.executescript(sql_script)
        mem_conn.close()
    except sqlite3.Error as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Backup file contains invalid SQL: {exc}",
        ) from exc

    # Close the application DB session before replacing the file
    db.close()

    # Preserve the current DB before overwriting
    import shutil

    bak = str(db_path) + ".pre_restore"
    try:
        shutil.copy2(str(db_path), bak)
    except OSError as exc:
        logger.warning(f"Could not create pre-restore backup at {bak}: {exc}")

    try:
        # Write the restored database
        restore_conn = sqlite3.connect(str(db_path))
        restore_conn.executescript(sql_script)
        restore_conn.close()
    except sqlite3.Error as exc:
        # Attempt rollback
        try:
            if os.path.exists(bak):
                shutil.copy2(bak, str(db_path))
        except OSError as rollback_exc:
            logger.error(f"Rollback failed; database may be corrupted: {rollback_exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {exc}",
        ) from exc
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
