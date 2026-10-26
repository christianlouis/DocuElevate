#!/usr/bin/env python3
"""Create deterministic, nonsensitive PDFs for DocuElevate acceptance checks."""

from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
TOKEN_NATIVE = "DOCUELEVATE_NATIVE_20261027_X7K4"
TOKEN_SCAN = "DOCUELEVATE_SCAN_20261027_Q2M9"


def native_pdf(path: Path) -> None:
    pdf = FPDF()
    pdf.set_title("DocuElevate native-text acceptance fixture")
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(text="DocuElevate acceptance fixture: native text")
    pdf.ln(14)
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        w=0,
        text=(
            "Synthetic content only. No personal, customer, or secret data.\n"
            f"Acceptance token: {TOKEN_NATIVE}\n"
            "Expected source: embedded/native PDF text."
        ),
    )
    pdf.output(str(path))


def image_only_pdf(path: Path) -> None:
    image = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
    except OSError:
        font = ImageFont.load_default()
    lines = [
        "DocuElevate acceptance fixture: image-only scan",
        "Synthetic content only. No personal, customer, or secret data.",
        f"Acceptance token: {TOKEN_SCAN}",
        "Expected source: image-only PDF requiring OCR.",
    ]
    for index, line in enumerate(lines):
        draw.text((90, 120 + index * 130), line, fill="black", font=font)
    image_path = path.with_suffix(".png")
    image.save(image_path, format="PNG")
    pdf = FPDF()
    pdf.set_title("DocuElevate image-only acceptance fixture")
    pdf.add_page()
    pdf.image(str(image_path), x=10, y=10, w=190)
    pdf.output(str(path))
    image_path.unlink()


if __name__ == "__main__":
    native_pdf(ROOT / "native-text-acceptance.pdf")
    image_only_pdf(ROOT / "image-only-scan-acceptance.pdf")
    print("created native-text-acceptance.pdf and image-only-scan-acceptance.pdf")
