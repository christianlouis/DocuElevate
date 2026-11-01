"""Small, dependency-free helpers for durable bulk uploads."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.config import settings


def upload_root() -> Path:
    root = Path(settings.workdir) / "bulk_uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(batch_id: str, item_id: int, filename: str) -> Path:
    folder = upload_root() / batch_id
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()[:16]
    return folder / f"{item_id}{suffix}"


def stream_to_file(upload, target: Path, expected_sha256: str, max_size: int) -> tuple[int, str]:
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
        directory_fd = os.open(str(target.parent), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return size, actual
    finally:
        temporary.unlink(missing_ok=True)


def sniff_mime(filename: str, supplied: str | None, header: bytes = b"") -> str:
    supplied = (supplied or "").split(";", 1)[0].strip().lower()
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"PK\x03\x04") and filename.lower().endswith((".docx", ".xlsx", ".pptx")):
        return supplied or "application/zip"
    return supplied or "application/octet-stream"
