"""
Admin-only file manager view for browsing the workdir directory.
"""

import logging
import mimetypes
import os
from datetime import datetime
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse

from app.config import settings
from app.views.base import APIRouter, require_login, templates
from app.views.settings import require_admin_access

logger = logging.getLogger(__name__)
router = APIRouter()

_SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"]


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
    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal detected")
    return target


@router.get("/admin/files")
@require_login
@require_admin_access
async def filemanager(request: Request):
    """
    Admin-only file manager for browsing the workdir directory.
    """
    workdir = settings.workdir
    rel_path = request.query_params.get("path", "")

    # Sanitise the relative path – strip leading slashes / dots
    rel_path = rel_path.lstrip("/").lstrip(".")

    try:
        target = _safe_path(workdir, rel_path)
    except ValueError:
        logger.warning(f"Path traversal attempt blocked: path={rel_path!r}")
        target = Path(workdir).resolve()
        rel_path = ""

    if not target.exists():
        target = Path(workdir).resolve()
        rel_path = ""

    entries = []
    if target.is_dir():
        for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = item.stat()
                item_rel = str(item.relative_to(Path(workdir).resolve()))
                mime_type, _ = mimetypes.guess_type(item.name)
                entries.append(
                    {
                        "name": item.name,
                        "rel_path": item_rel,
                        "is_dir": item.is_dir(),
                        "size": _format_size(stat.st_size) if not item.is_dir() else "",
                        "size_bytes": stat.st_size if not item.is_dir() else 0,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "mime_type": mime_type or "",
                    }
                )
            except (PermissionError, OSError) as exc:
                logger.warning(f"Could not stat {item}: {exc}")

    # Build breadcrumb trail
    breadcrumbs = []
    if rel_path:
        parts = Path(rel_path).parts
        accumulated = ""
        for part in parts:
            accumulated = str(Path(accumulated) / part) if accumulated else part
            breadcrumbs.append({"name": part, "path": accumulated})

    # Parent path for the "go up" link
    parent_path = str(Path(rel_path).parent) if rel_path and Path(rel_path).parent != Path(".") else ""
    if parent_path == ".":
        parent_path = ""

    return templates.TemplateResponse(
        "filemanager.html",
        {
            "request": request,
            "entries": entries,
            "current_path": rel_path,
            "parent_path": parent_path,
            "breadcrumbs": breadcrumbs,
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
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Invalid path")

    if not target.exists() or not target.is_file():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="File not found")

    mime_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type=mime_type or "application/octet-stream",
    )
