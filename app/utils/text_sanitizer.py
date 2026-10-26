"""Sanitize extracted text before writing it to text-backed stores."""

from typing import overload


@overload
def remove_nul_bytes(text: str) -> str: ...


@overload
def remove_nul_bytes(text: None) -> None: ...


def remove_nul_bytes(text: str | None) -> str | None:
    """Remove PostgreSQL-incompatible NUL characters without altering other text."""
    if text is None:
        return None
    return text.replace("\x00", "")
