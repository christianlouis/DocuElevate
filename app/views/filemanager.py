"""
Admin-only file manager view for browsing the workdir directory.

Supports three views:
  filesystem  – navigate the raw workdir tree, each file tagged against DB records
  database    – list all FileRecord rows, each tagged with on-disk existence
  reconcile   – show only the delta: orphan disk files and ghost DB records
"""

import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FileRecord
from app.views.base import APIRouter, get_db, require_login, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()

_SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    size = float(size_bytes)
    for unit in _SIZE_UNITS:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _safe_path(workdir: str, rel_path: str) -> Path:
    """
    Resolve a relative path inside workdir safely.

    Raises ValueError if the resolved path escapes workdir.
    """
    base = Path(workdir).resolve()
    target = (base / rel_path).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Path traversal detected")
    return target


def _db_path_set(db: Session) -> Set[str]:
    """
    Return the set of all absolute, normalised paths that the DB references
    across local_filename, original_file_path, and processed_file_path.
    """
    paths: Set[str] = set()
    for row in db.query(
        FileRecord.local_filename,
        FileRecord.original_file_path,
        FileRecord.processed_file_path,
    ).all():
        for p in row:
            if p:
                paths.add(str(Path(p).resolve()))
    return paths


def _file_icon(mime_type: str, is_dir: bool) -> str:
    """Return a Font Awesome class for a file/directory."""
    if is_dir:
        return "fas fa-folder text-yellow-400"
    if mime_type.startswith("image/"):
        return "fas fa-file-image text-blue-400"
    if mime_type == "application/pdf":
        return "fas fa-file-pdf text-red-400"
    if "text/" in mime_type:
        return "fas fa-file-alt text-gray-400"
    if "json" in mime_type:
        return "fas fa-file-code text-green-400"
    return "fas fa-file text-gray-400"


def _scan_dir(target: Path, workdir_base: Path, db_paths: Set[str]) -> List[Dict[str, Any]]:
    """
    List one directory level; annotate each file with its DB status.

    db_status values:
      "in_db"   – path found in DB
      "orphan"  – on disk but not in DB
      ""        – directories (not checked against DB)
    """
    entries = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            stat = item.stat()
        except (PermissionError, OSError) as exc:
            logger.warning(f"Could not stat {item}: {exc}")
            continue

        item_rel = str(item.relative_to(workdir_base))
        mime_type, _ = mimetypes.guess_type(item.name)
        mime_type = mime_type or ""

        if item.is_dir():
            db_status = ""
        else:
            abs_str = str(item.resolve())
            db_status = "in_db" if abs_str in db_paths else "orphan"

        entries.append(
            {
                "name": item.name,
                "rel_path": item_rel,
                "abs_path": str(item.resolve()),
                "is_dir": item.is_dir(),
                "size": _format_size(stat.st_size) if not item.is_dir() else "",
                "size_bytes": stat.st_size if not item.is_dir() else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "mime_type": mime_type,
                "icon": _file_icon(mime_type, item.is_dir()),
                "db_status": db_status,
            }
        )
    return entries


def _walk_all_files(base: Path, db_paths: Set[str]) -> List[Dict[str, Any]]:
    """
    Walk the entire workdir tree and return every file (not directory).
    Used for the reconciliation view.
    """
    entries = []
    for item in sorted(base.rglob("*"), key=lambda p: str(p).lower()):
        if item.is_dir():
            continue
        try:
            stat = item.stat()
        except (PermissionError, OSError):
            continue

        abs_str = str(item.resolve())
        mime_type, _ = mimetypes.guess_type(item.name)
        mime_type = mime_type or ""
        entries.append(
            {
                "name": item.name,
                "rel_path": str(item.relative_to(base)),
                "abs_path": abs_str,
                "is_dir": False,
                "size": _format_size(stat.st_size),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "mime_type": mime_type,
                "icon": _file_icon(mime_type, False),
                "db_status": "in_db" if abs_str in db_paths else "orphan",
            }
        )
    return entries


def _db_records(db: Session, workdir_base: Path) -> List[Dict[str, Any]]:
    """
    Return every FileRecord annotated with on-disk existence for each stored path.
    """
    rows = []
    for rec in db.query(FileRecord).order_by(FileRecord.id.desc()).all():

        def _check(p: str | None) -> Dict[str, Any]:
            if not p:
                return {"path": None, "exists": None, "rel": None}
            resolved = Path(p).resolve()
            exists = resolved.exists()
            try:
                rel = str(resolved.relative_to(workdir_base))
            except ValueError:
                rel = p  # outside workdir – show full path
            return {"path": p, "exists": exists, "rel": rel}

        local = _check(rec.local_filename)
        original = _check(rec.original_file_path)
        processed = _check(rec.processed_file_path)

        any_missing = any(info["exists"] is False for info in [local, original, processed])

        rows.append(
            {
                "id": rec.id,
                "original_filename": rec.original_filename or "—",
                "file_size": _format_size(rec.file_size) if rec.file_size else "—",
                "mime_type": rec.mime_type or "—",
                "created_at": rec.created_at.strftime("%Y-%m-%d %H:%M") if rec.created_at else "—",
                "is_duplicate": rec.is_duplicate,
                "filehash": (rec.filehash or "")[:12],
                "local": local,
                "original": original,
                "processed": processed,
                # overall health flag
                "health": "missing" if any_missing else "ok",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/admin/files")
@require_login
@require_admin_access
async def filemanager(request: Request, db: Session = Depends(get_db)):
    """
    Admin-only file manager with three views:
      ?view=filesystem  (default) – navigate workdir tree
      ?view=database              – list all DB FileRecord rows
      ?view=reconcile             – show only deltas (orphans + ghost records)
    """
    workdir = settings.workdir
    workdir_base = Path(workdir).resolve()
    view = request.query_params.get("view", "filesystem")

    # Build the DB path set once (used by all views)
    db_paths = _db_path_set(db)

    # ── Filesystem view ───────────────────────────────────────────────────
    rel_path = request.query_params.get("path", "").lstrip("/").lstrip(".")
    try:
        target = _safe_path(workdir, rel_path)
    except ValueError:
        logger.warning(f"Path traversal attempt blocked: path={rel_path!r}")
        target = workdir_base
        rel_path = ""

    if not target.exists():
        target = workdir_base
        rel_path = ""

    fs_entries: List[Dict[str, Any]] = []
    if view == "filesystem" and target.is_dir():
        fs_entries = _scan_dir(target, workdir_base, db_paths)

    # Breadcrumb for filesystem view
    breadcrumbs = []
    if rel_path:
        accumulated = Path()
        for part in Path(rel_path).parts:
            accumulated = accumulated / part
            breadcrumbs.append({"name": part, "path": str(accumulated)})

    parent_path = ""
    if rel_path:
        parent = str(Path(rel_path).parent)
        parent_path = "" if parent == "." else parent

    # ── Database view ─────────────────────────────────────────────────────
    db_records: List[Dict[str, Any]] = []
    if view in ("database", "reconcile"):
        db_records = _db_records(db, workdir_base)

    # ── Reconciliation view ───────────────────────────────────────────────
    orphan_files: List[Dict[str, Any]] = []
    ghost_records: List[Dict[str, Any]] = []
    if view == "reconcile":
        all_disk = _walk_all_files(workdir_base, db_paths)
        orphan_files = [f for f in all_disk if f["db_status"] == "orphan"]
        ghost_records = [r for r in db_records if r["health"] == "missing"]

    # ── Summary counts ────────────────────────────────────────────────────
    # Disk file count is only computed for non-filesystem views to avoid
    # the overhead of walking the full tree on every directory navigation.
    if view in ("database", "reconcile") and workdir_base.exists():
        total_disk = sum(1 for p in workdir_base.rglob("*") if p.is_file())
    else:
        total_disk = None  # deferred; not shown on filesystem tab header
    total_db = db.query(FileRecord).count()

    return templates.TemplateResponse(
        "filemanager.html",
        {
            "request": request,
            # view selector
            "view": view,
            # filesystem tab
            "fs_entries": fs_entries,
            "current_path": rel_path,
            "parent_path": parent_path,
            "breadcrumbs": breadcrumbs,
            # database tab
            "db_records": db_records,
            # reconcile tab
            "orphan_files": orphan_files,
            "ghost_records": ghost_records,
            # summary
            "total_disk": total_disk,
            "total_db": total_db,
            "workdir": workdir,
            "app_version": settings.version,
        },
    )


@router.get("/admin/files/download")
@require_login
@require_admin_access
async def filemanager_download(request: Request):
    """
    Admin-only endpoint to download a file from workdir.
    """
    workdir = settings.workdir
    rel_path = request.query_params.get("path", "").lstrip("/").lstrip(".")

    try:
        target = _safe_path(workdir, rel_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    mime_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type=mime_type or "application/octet-stream",
    )
