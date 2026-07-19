"""Safe media-type handling for same-origin document previews."""

from __future__ import annotations

import mimetypes
from pathlib import Path

SAFE_INLINE_PREVIEW_TYPES = frozenset(
    {
        "application/json",
        "application/pdf",
        "image/bmp",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
        "text/csv",
        "text/markdown",
        "text/plain",
    }
)

SAFE_RASTER_IMAGE_TYPES = frozenset(
    media_type for media_type in SAFE_INLINE_PREVIEW_TYPES if media_type.startswith("image/")
)


def safe_preview_media_type(declared_media_type: str | None, file_path: str | Path) -> str:
    """Return a non-executable media type suitable for a same-origin preview.

    Uploaded HTML, SVG, XML, and other active formats must never be rendered as
    their declared type under the DocuElevate origin. They are intentionally
    neutralized even when the database or filename claims otherwise.
    """
    declared = (declared_media_type or "").split(";", 1)[0].strip().lower()
    guessed = (mimetypes.guess_type(str(file_path))[0] or "").lower()
    candidate = declared or guessed

    if candidate in SAFE_INLINE_PREVIEW_TYPES:
        return candidate
    if candidate.startswith("text/") or candidate in {
        "application/xhtml+xml",
        "application/xml",
        "image/svg+xml",
    }:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"
