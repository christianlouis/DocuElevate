"""Tests for the comments and annotations UI on the file annotations page."""

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord


def _create_file(db_session, tmp_path) -> FileRecord:
    """Create a minimal FileRecord with a real file path for the annotations page."""
    file_path = tmp_path / "test.pdf"
    file_path.write_bytes(b"%PDF-1.4")
    f = FileRecord(
        filehash="uihash123",
        original_filename="test.pdf",
        local_filename=str(file_path),
        original_file_path=str(file_path),
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


@pytest.mark.unit
class TestCommentsUIRendering:
    """Verify the file annotations page includes the comments panel HTML."""

    def test_annotations_page_contains_comments_section(self, client: TestClient, db_session, tmp_path):
        """The annotations page should render the comments panel container."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="comments-list"' in html
        assert 'id="comment-form"' in html
        assert 'id="comment-input"' in html

    def test_annotations_page_contains_annotations_section(self, client: TestClient, db_session, tmp_path):
        """The annotations page should render the annotations panel container."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="annotations-list"' in html
        assert 'id="annotation-form"' in html
        assert 'id="annotation-content-input"' in html

    def test_annotations_page_loads_comments_js(self, client: TestClient, db_session, tmp_path):
        """The annotations page should include the comments JavaScript file."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        assert "js/comments.js" in resp.text

    def test_annotations_page_loads_annotations_js(self, client: TestClient, db_session, tmp_path):
        """The annotations page should include the annotations JavaScript file."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        assert "js/annotations.js" in resp.text

    def test_annotations_page_has_mention_dropdown(self, client: TestClient, db_session, tmp_path):
        """The mention autocomplete dropdown should be present."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        assert 'id="mention-dropdown"' in resp.text

    def test_annotations_page_has_annotation_form_fields(self, client: TestClient, db_session, tmp_path):
        """Annotation form should have page, type, and color inputs."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="annotation-page-input"' in html
        assert 'id="annotation-type-input"' in html
        assert 'id="annotation-color-input"' in html

    def test_annotations_page_has_collab_grid(self, client: TestClient, db_session, tmp_path):
        """Comments and annotations should be in a side-by-side grid layout."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        assert "collab-grid" in resp.text

    def test_annotations_page_no_comments_for_missing_file(self, client: TestClient):
        """When file is not found, no comments section should appear."""
        resp = client.get("/files/99999/annotations")
        assert resp.status_code == 200
        # The error block is shown, not the main content
        assert 'id="comments-list"' not in resp.text

    def test_annotations_page_annotation_type_options(self, client: TestClient, db_session, tmp_path):
        """Annotation type selector should include all four types."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'value="note"' in html
        assert 'value="highlight"' in html
        assert 'value="underline"' in html
        assert 'value="strikethrough"' in html

    def test_annotations_page_comments_panel_accessibility(self, client: TestClient, db_session, tmp_path):
        """Comments panel should have proper ARIA attributes."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'aria-live="polite"' in html
        assert 'role="listbox"' in html

    def test_annotations_page_init_script(self, client: TestClient, db_session, tmp_path):
        """The init script should call initComments and initAnnotations."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert "initComments" in html
        assert "initAnnotations" in html

    def test_comments_url_redirects_to_annotations(self, client: TestClient, db_session, tmp_path):
        """The /comments URL should redirect to /annotations."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/comments", follow_redirects=False)
        assert resp.status_code == 302
        assert f"/files/{f.id}/annotations" in resp.headers["location"]

    def test_process_page_no_comments_section(self, client: TestClient, db_session, tmp_path):
        """The process page should NOT render the comments panel."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/process")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="comments-list"' not in html
        assert 'id="comment-form"' not in html

    def test_detail_page_no_comments_section(self, client: TestClient, db_session, tmp_path):
        """The detail page should NOT render the comments panel."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/detail")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="comments-list"' not in html
        assert 'id="annotation-form"' not in html

    def test_annotations_page_has_embedpdf_viewer_for_pdf(self, client: TestClient, db_session, tmp_path):
        """The annotations page should include the EmbedPDF viewer for PDF files."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}/annotations")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="embedpdf-viewer"' in html
        assert "@embedpdf/snippet" in html

    def test_summary_page_renders(self, client: TestClient, db_session, tmp_path):
        """The summary page at /files/{id} should render correctly."""
        f = _create_file(db_session, tmp_path)
        resp = client.get(f"/files/{f.id}")
        assert resp.status_code == 200
        html = resp.text
        assert "Document Detail" in html
        assert "Processing" in html
        assert "Comments" in html or "Annotations" in html
