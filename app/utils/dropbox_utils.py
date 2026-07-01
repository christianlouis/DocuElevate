"""Shared Dropbox helpers."""

from typing import Any

from dropbox.exceptions import ApiError


def dropbox_path_exists(dbx: Any, path: str) -> bool:
    """Return whether *path* already exists in Dropbox."""
    try:
        dbx.files_get_metadata(path)
        return True
    except ApiError as e:
        if e.error.is_path() and e.error.get_path().is_not_found():
            return False
        raise
