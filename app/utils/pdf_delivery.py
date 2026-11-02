"""Lossless PDF preparation for destination delivery policies."""

from __future__ import annotations

from io import BytesIO


def optimize_pdf_bytes(file_path: str) -> bytes | None:
    """Return a smaller lossless copy, preserving the complete PDF structure.

    Signed PDFs are left untouched because rewriting invalidates their signature.
    ``None`` means no safe smaller copy was produced.
    """
    from pypdf import PdfReader, PdfWriter

    with open(file_path, "rb") as stream:
        original = stream.read()
    if b"/ByteRange" in original:
        return None
    reader = PdfReader(BytesIO(original))
    writer = PdfWriter(clone_from=reader)
    writer.compress_identical_objects()
    output = BytesIO()
    writer.write(output)
    optimized = output.getvalue()
    return optimized if len(optimized) < len(original) else None
