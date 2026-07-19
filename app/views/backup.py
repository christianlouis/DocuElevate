"""
Backup management dashboard view – admin only.
"""

import logging
import os

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BackupRecord
from app.views.base import APIRouter, get_db, require_login, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/admin/backup")
@require_login
@require_admin_access
async def backup_dashboard(request: Request, db: Session = Depends(get_db)):
    """Backup management dashboard – admin only."""
    try:
        records = (
            db.query(BackupRecord).order_by(BackupRecord.created_at.desc(), BackupRecord.id.desc()).limit(500).all()
        )

        # Summarise counts per tier
        counts: dict[str, int] = {"hourly": 0, "daily": 0, "weekly": 0}
        for r in records:
            if r.backup_type in counts:
                counts[r.backup_type] += 1

        # Compute total local size
        total_size = sum(r.size_bytes for r in records if r.local_path and os.path.exists(r.local_path))
        from app.tasks.backup_tasks import _archive_ext_for_backend, _db_backend, backup_storage_status

        storage = backup_storage_status()
        last_failure = records[0] if records and records[0].status == "failed" else None

        return templates.TemplateResponse(
            "backup.html",
            {
                "request": request,
                "records": records,
                "counts": counts,
                "total_size": total_size,
                "backup_enabled": getattr(settings, "backup_enabled", True),
                "backup_remote_destination": getattr(settings, "backup_remote_destination", None),
                "backup_retain_hourly": getattr(settings, "backup_retain_hourly", 96),
                "backup_retain_daily": getattr(settings, "backup_retain_daily", 21),
                "backup_retain_weekly": getattr(settings, "backup_retain_weekly", 13),
                "backup_storage": storage,
                "backup_storage_free_mib": int(storage["free_bytes"]) // 1048576,
                "backup_storage_budget_mib": int(storage["max_local_bytes"]) // 1048576,
                "backup_storage_used_mib": int(storage["backup_bytes"]) // 1048576,
                "backup_storage_reserve_mib": int(storage["min_free_bytes"]) // 1048576,
                "last_backup_failure": last_failure,
                "backup_archive_extension": _archive_ext_for_backend(_db_backend()),
                "app_version": settings.version,
            },
        )
    except Exception as e:
        logger.error(f"Error loading backup dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load backup dashboard",
        )
