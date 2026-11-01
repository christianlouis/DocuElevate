"""Small, dependency-free helpers for durable bulk uploads."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from app.config import settings

_EXTENSION_MIME = {
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".docm": "application/vnd.ms-word.document.macroenabled.12", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pptm": "application/vnd.ms-powerpoint.presentation.macroenabled.12", ".txt": "text/plain", ".csv": "text/csv",
    ".rtf": "application/rtf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
}


def _sync_directory(path: Path) -> None:
    directory_fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def upload_root() -> Path:
    root = Path(settings.workdir) / "bulk_uploads"
    root.mkdir(parents=True, exist_ok=True)
    _sync_directory(root.parent)
    return root


def safe_path(batch_id: str, item_id: str | int, filename: str) -> Path:
    folder = upload_root() / batch_id
    folder.mkdir(parents=True, exist_ok=True)
    _sync_directory(folder.parent)
    suffix = Path(filename).suffix.lower()[:16]
    return folder / f"{item_id}{suffix}"


def stream_to_file(upload: Any, target: Path, expected_sha256: str, max_size: int) -> tuple[int, str]:
    """Write an upload atomically, verifying the client hash while streaming."""
    temporary = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_size:
                    raise ValueError("file exceeds configured upload limit")
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        actual = digest.hexdigest()
        if actual != expected_sha256.lower():
            raise ValueError("sha256 does not match upload content")
        os.replace(temporary, target)
        # A successful file fsync is insufficient after rename: without an
        # fsync of the containing directory a power loss may lose the name.
        _sync_directory(target.parent)
        return size, actual
    finally:
        temporary.unlink(missing_ok=True)


def sniff_mime(filename: str, supplied: str | None, header: bytes = b"") -> str:
    supplied = (supplied or "").split(";", 1)[0].strip().lower()
    filename = filename.lower()
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if filename.endswith((".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm")):
        # OOXML macro and non-macro documents must be ZIP containers. Never
        # trust a declared MIME type when the signature is absent.
        return supplied if header.startswith(b"PK\x03\x04") and supplied not in {"", "application/octet-stream"} else (
            _EXTENSION_MIME.get("." + filename.rsplit(".", 1)[-1], "application/octet-stream")
            if header.startswith(b"PK\x03\x04") else "application/octet-stream"
        )
    return supplied or _EXTENSION_MIME.get("." + filename.rsplit(".", 1)[-1], "application/octet-stream")


def extension_mime(filename: str) -> str | None:
    return _EXTENSION_MIME.get(Path(filename).suffix.lower())
