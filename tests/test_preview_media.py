"""Unit tests for safe same-origin preview media types."""

import pytest

from app.utils.preview_media import safe_preview_media_type


@pytest.mark.unit
@pytest.mark.parametrize(
    ("declared_media_type", "filename", "expected"),
    [
        (None, "invoice.pdf", "application/pdf"),
        ("application/pdf; charset=binary", "invoice.bin", "application/pdf"),
        ("image/svg+xml", "drawing.svg", "text/plain; charset=utf-8"),
        ("application/vnd.example.active", "payload.bin", "application/octet-stream"),
    ],
)
def test_safe_preview_media_type(
    declared_media_type: str | None,
    filename: str,
    expected: str,
) -> None:
    """Allow inert formats while neutralizing active or unknown content."""
    assert safe_preview_media_type(declared_media_type, filename) == expected
