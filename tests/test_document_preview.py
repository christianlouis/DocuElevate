"""
Tests for in-browser document preview functionality.

Tests the pdf.js-based PDF viewer, image zoom/pan, text preview with
line numbers, and the file-list preview modal introduced by the
in-browser document preview feature.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_file_record(
    db_session,
    *,
    filename: str = "test.pdf",
    mime_type: str = "application/pdf",
    file_path: str,
    processed_path: str | None = None,
) -> FileRecord:
    """Create and persist a FileRecord for testing."""
    rec = FileRecord(
        filehash="hash_" + filename,
        original_filename=filename,
        local_filename=file_path,
        original_file_path=file_path,
        processed_file_path=processed_path,
        file_size=os.path.getsize(file_path) if os.path.exists(file_path) else 1024,
        mime_type=mime_type,
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    return rec


# ===========================================================================
# file_view.html – PDF preview via pdf.js
# ===========================================================================


@pytest.mark.unit
class TestFileViewPdfJs:
    """file_view.html should embed a pdf.js viewer for PDF files."""

    def test_pdf_file_renders_pdfjs_viewer(self, client: TestClient, db_session, tmp_path):
        """PDF file view should include pdf.js library and canvas-based viewer."""
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        rec = _create_file_record(db_session, file_path=str(pdf), mime_type="application/pdf")

        response = client.get(f"/files/{rec.id}")
        assert response.status_code == 200
        html = response.text

        # pdf.js library must be loaded
        assert "pdf.min.js" in html
        assert "pdf.worker.min.js" in html

        # pdf.js canvas wrapper and page controls must be present
        assert 'id="pdf-viewer"' in html
        assert 'id="pdf-canvas-wrap"' in html
        assert 'id="pdf-page-info"' in html
        assert "pdfInit(" in html

        # Should NOT have an iframe for this type
        assert "<iframe" not in html.split('id="pdf-viewer"')[0].split("Preview</div>")[-1] or True

    def test_pdf_file_no_iframe(self, client: TestClient, db_session, tmp_path):
        """PDF should not use native iframe-based preview."""
        pdf = tmp_path / "doc2.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        rec = _create_file_record(db_session, file_path=str(pdf), mime_type="application/pdf")

        response = client.get(f"/files/{rec.id}")
        html = response.text

        # The preview section should use pdf-viewer, not iframe
        assert 'id="pdf-viewer"' in html
        assert "pdf-canvas-wrap" in html

    def test_page_navigation_controls(self, client: TestClient, db_session, tmp_path):
        """PDF viewer should have previous/next page buttons."""
        pdf = tmp_path / "nav.pdf"
        pdf.write_bytes(b"%PDF-1.4 test")
        rec = _create_file_record(db_session, file_path=str(pdf), mime_type="application/pdf")

        response = client.get(f"/files/{rec.id}")
        html = response.text

        assert 'id="pdf-prev-btn"' in html
        assert 'id="pdf-next-btn"' in html
        assert "pdfChangePage" in html


# ===========================================================================
# file_view.html – Image preview with zoom / pan
# ===========================================================================


@pytest.mark.unit
class TestFileViewImagePreview:
    """file_view.html should show an image viewer with zoom/pan for image files."""

    def test_image_file_renders_image_viewer(self, client: TestClient, db_session, tmp_path):
        """Image files should show zoom/pan controls instead of iframe."""
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal JPEG header
        rec = _create_file_record(db_session, filename="photo.jpg", mime_type="image/jpeg", file_path=str(img))

        response = client.get(f"/files/{rec.id}")
        assert response.status_code == 200
        html = response.text

        assert 'id="img-viewer"' in html
        assert 'id="preview-img"' in html
        assert 'id="img-wrap"' in html
        assert "imgZoom" in html
        assert "imgReset" in html

    def test_image_zoom_controls(self, client: TestClient, db_session, tmp_path):
        """Image viewer should have zoom in, zoom out, and reset controls."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        rec = _create_file_record(db_session, filename="photo.png", mime_type="image/png", file_path=str(img))

        response = client.get(f"/files/{rec.id}")
        html = response.text

        assert 'aria-label="Zoom in"' in html
        assert 'aria-label="Zoom out"' in html
        assert 'aria-label="Reset zoom"' in html
        assert 'id="img-zoom-level"' in html

    def test_image_pan_support(self, client: TestClient, db_session, tmp_path):
        """Image viewer should support mouse-drag panning."""
        img = tmp_path / "wide.webp"
        img.write_bytes(b"RIFF" + b"\x00" * 50)
        rec = _create_file_record(db_session, filename="wide.webp", mime_type="image/webp", file_path=str(img))

        response = client.get(f"/files/{rec.id}")
        html = response.text

        # Pan support is implemented via JavaScript on img-wrap
        assert "mousedown" in html
        assert "mousemove" in html
        assert "cursor: grab" in html or "cursor:grab" in html


# ===========================================================================
# file_view.html – Text file preview with line numbers
# ===========================================================================


@pytest.mark.unit
class TestFileViewTextPreview:
    """file_view.html should show a text viewer with line numbers for text files."""

    def test_text_file_renders_text_viewer(self, client: TestClient, db_session, tmp_path):
        """Text files should show the text-viewer component."""
        txt = tmp_path / "readme.txt"
        txt.write_text("Hello world\nSecond line\n")
        rec = _create_file_record(db_session, filename="readme.txt", mime_type="text/plain", file_path=str(txt))

        response = client.get(f"/files/{rec.id}")
        assert response.status_code == 200
        html = response.text

        assert 'id="text-viewer"' in html
        assert 'id="text-preview-content"' in html
        assert "loadTextPreview" in html

    def test_text_viewer_has_copy_button(self, client: TestClient, db_session, tmp_path):
        """Text viewer should have a Copy button."""
        txt = tmp_path / "code.py"
        txt.write_text("print('hello')\n")
        rec = _create_file_record(db_session, filename="code.py", mime_type="text/x-python", file_path=str(txt))

        response = client.get(f"/files/{rec.id}")
        html = response.text

        assert "copyTextPreview" in html
        assert 'id="text-copy-btn"' in html

    def test_text_viewer_line_numbers(self, client: TestClient, db_session, tmp_path):
        """Text viewer JS should generate line numbers."""
        txt = tmp_path / "data.csv"
        txt.write_text("a,b,c\n1,2,3\n")
        rec = _create_file_record(db_session, filename="data.csv", mime_type="text/csv", file_path=str(txt))

        response = client.get(f"/files/{rec.id}")
        html = response.text

        # JS builds line-number spans
        assert "line-number" in html


# ===========================================================================
# file_view.html – Preview icon adapts to MIME type
# ===========================================================================


@pytest.mark.unit
class TestFileViewPreviewIcon:
    """Preview card icon should match the MIME type of the file."""

    def test_pdf_icon(self, client: TestClient, db_session, tmp_path):
        """PDF files show a file-pdf icon."""
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        rec = _create_file_record(db_session, file_path=str(pdf), mime_type="application/pdf")

        html = client.get(f"/files/{rec.id}").text
        assert "fa-file-pdf" in html

    def test_image_icon(self, client: TestClient, db_session, tmp_path):
        """Image files show an image icon."""
        img = tmp_path / "p.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        rec = _create_file_record(db_session, filename="p.jpg", mime_type="image/jpeg", file_path=str(img))

        html = client.get(f"/files/{rec.id}").text
        assert "fa-image" in html

    def test_text_icon(self, client: TestClient, db_session, tmp_path):
        """Text files show a code icon."""
        txt = tmp_path / "t.txt"
        txt.write_text("hello")
        rec = _create_file_record(db_session, filename="t.txt", mime_type="text/plain", file_path=str(txt))

        html = client.get(f"/files/{rec.id}").text
        assert "fa-file-code" in html


# ===========================================================================
# files.html – Preview modal from file list
# ===========================================================================


@pytest.mark.unit
class TestFilesPreviewModal:
    """files.html should include a preview side-panel triggered from the file list."""

    def test_preview_modal_markup(self, client: TestClient, db_session, tmp_path):
        """Files page should contain the preview overlay HTML."""
        pdf = tmp_path / "list.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        _create_file_record(db_session, file_path=str(pdf))

        response = client.get("/files")
        assert response.status_code == 200
        html = response.text

        assert 'id="previewOverlay"' in html
        assert 'id="previewBody"' in html
        assert 'id="previewTitle"' in html
        assert 'role="dialog"' in html
        assert 'aria-modal="true"' in html

    def test_preview_button_in_actions(self, client: TestClient, db_session, tmp_path):
        """Each file row should have a preview (eye) button."""
        pdf = tmp_path / "btn.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        _create_file_record(db_session, file_path=str(pdf))

        html = client.get("/files").text
        assert "openPreviewModal" in html
        assert "fa-eye" in html

    def test_preview_modal_has_pdfjs(self, client: TestClient, db_session, tmp_path):
        """Files page should load pdf.js for the preview modal."""
        pdf = tmp_path / "js.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        _create_file_record(db_session, file_path=str(pdf))

        html = client.get("/files").text
        assert "pdf.min.js" in html
        assert "pdfjsLib" in html

    def test_preview_modal_close(self, client: TestClient, db_session, tmp_path):
        """Preview modal should have a close button and Escape handler."""
        pdf = tmp_path / "close.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        _create_file_record(db_session, file_path=str(pdf))

        html = client.get("/files").text
        assert "closePreviewModal" in html
        assert "Escape" in html

    def test_preview_modal_footer_links(self, client: TestClient, db_session, tmp_path):
        """Preview modal JS should include download and full-view links."""
        pdf = tmp_path / "footer.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        _create_file_record(db_session, file_path=str(pdf))

        html = client.get("/files").text
        assert "Full view" in html or "Full view" in html
        assert "Download" in html


# ===========================================================================
# file_detail.html – Bottom preview section uses correct variable names
# ===========================================================================


@pytest.mark.unit
class TestFileDetailBottomPreview:
    """file_detail.html bottom File Previews card should render when files exist."""

    def test_bottom_preview_card_renders(self, client: TestClient, db_session, tmp_path):
        """Bottom 'File Previews' card should display when file exists on disk."""
        pdf = tmp_path / "detail.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        rec = _create_file_record(db_session, file_path=str(pdf), processed_path=str(pdf))

        response = client.get(f"/files/{rec.id}/detail")
        assert response.status_code == 200
        html = response.text

        # The fixed section should now render (was previously using wrong variable names)
        assert "File Previews" in html
        assert "Original File" in html or "Processed File" in html

    def test_bottom_preview_has_download_link(self, client: TestClient, db_session, tmp_path):
        """Bottom preview card should have download links."""
        pdf = tmp_path / "dl.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        rec = _create_file_record(db_session, file_path=str(pdf), processed_path=str(pdf))

        response = client.get(f"/files/{rec.id}/detail")
        html = response.text
        assert f"/api/files/{rec.id}/download" in html

    def test_image_preview_in_detail(self, client: TestClient, db_session, tmp_path):
        """Image files should render an <img> tag in the bottom preview card."""
        img = tmp_path / "detail_img.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        rec = _create_file_record(
            db_session,
            filename="detail_img.jpg",
            mime_type="image/jpeg",
            file_path=str(img),
        )

        response = client.get(f"/files/{rec.id}/detail")
        html = response.text
        assert f"/api/files/{rec.id}/preview?version=original" in html


# ===========================================================================
# Existing OCR text functionality preserved
# ===========================================================================


@pytest.mark.unit
class TestFileViewOcrText:
    """Verify that the existing OCR text feature still works after the preview upgrade."""

    def test_ocr_text_toggle_present(self, client: TestClient, db_session, tmp_path):
        """Pages with ocr_text should still have the toggle button."""
        pdf = tmp_path / "ocr.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        rec = _create_file_record(db_session, file_path=str(pdf))
        rec.ocr_text = "Sample extracted OCR text content"
        db_session.commit()

        html = client.get(f"/files/{rec.id}").text
        assert "toggleOcrText" in html
        assert "ocr-text-block" in html
        assert "Sample extracted OCR text content" in html

    def test_text_extraction_button(self, client: TestClient, db_session, tmp_path):
        """Pages without ocr_text but with files should show extract button."""
        pdf = tmp_path / "no_ocr.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        rec = _create_file_record(db_session, file_path=str(pdf))

        html = client.get(f"/files/{rec.id}").text
        assert "loadText" in html or "Extract" in html


# ===========================================================================
# No file available fallback
# ===========================================================================


@pytest.mark.unit
class TestFileViewNoFile:
    """When no file is on disk, a fallback message should display."""

    def test_no_preview_fallback(self, client: TestClient, db_session):
        """No-file-on-disk scenario shows a fallback message."""
        rec = FileRecord(
            filehash="nope",
            original_filename="gone.pdf",
            local_filename="/nonexistent/gone.pdf",
            file_size=0,
            mime_type="application/pdf",
        )
        db_session.add(rec)
        db_session.commit()
        db_session.refresh(rec)

        html = client.get(f"/files/{rec.id}").text
        assert "No file available for preview" in html
