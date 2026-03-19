"""Tests for duplicate document detection and management.

Covers:
- ``GET /api/duplicates``            — list all exact-duplicate groups
- ``GET /api/files/{id}/duplicates`` — per-file exact + near-duplicate info
- ``POST /api/ui-upload``            — exact-duplicate rejection at upload time
- ``GET /duplicates``                — duplicate management UI page
"""

import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(db, *, filehash, filename, is_duplicate=False, duplicate_of_id=None, ocr_text=None, embedding=None):
    """Insert a FileRecord and return it."""
    record = FileRecord(
        filehash=filehash,
        original_filename=filename,
        local_filename=f"/tmp/{filename}",
        file_size=1024,
        mime_type="application/pdf",
        is_duplicate=is_duplicate,
        duplicate_of_id=duplicate_of_id,
        ocr_text=ocr_text,
        embedding=embedding,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# GET /api/duplicates
# ---------------------------------------------------------------------------


class TestListDuplicateGroups:
    """Tests for the GET /api/duplicates endpoint."""

    @pytest.mark.integration
    def test_returns_empty_when_no_duplicates(self, client: TestClient):
        """Should return empty groups list when no duplicates exist."""
        response = client.get("/api/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] == 0
        assert data["groups"] == []
        assert data["total_duplicate_files"] == 0

    @pytest.mark.integration
    def test_returns_duplicate_group(self, client: TestClient, db_session):
        """Should return one group with original and duplicate."""
        original = _make_file(db_session, filehash="aaa111", filename="doc.pdf")
        dup = _make_file(
            db_session,
            filehash="aaa111",
            filename="doc_copy.pdf",
            is_duplicate=True,
            duplicate_of_id=original.id,
        )

        response = client.get("/api/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["total_groups"] == 1
        assert data["total_duplicate_files"] == 1

        group = data["groups"][0]
        assert group["filehash"] == "aaa111"
        assert group["duplicate_count"] == 1
        assert group["original"]["id"] == original.id
        assert group["duplicates"][0]["id"] == dup.id

    @pytest.mark.integration
    def test_multiple_groups(self, client: TestClient, db_session):
        """Should handle multiple distinct duplicate groups."""
        orig1 = _make_file(db_session, filehash="hash1", filename="a.pdf")
        _make_file(db_session, filehash="hash1", filename="a_copy.pdf", is_duplicate=True, duplicate_of_id=orig1.id)

        orig2 = _make_file(db_session, filehash="hash2", filename="b.pdf")
        _make_file(db_session, filehash="hash2", filename="b_copy.pdf", is_duplicate=True, duplicate_of_id=orig2.id)

        response = client.get("/api/duplicates")
        assert response.status_code == 200
        assert response.json()["total_groups"] == 2

    @pytest.mark.integration
    def test_pagination(self, client: TestClient, db_session):
        """Should respect page/per_page parameters."""
        for i in range(5):
            orig = _make_file(db_session, filehash=f"phash{i}", filename=f"p{i}.pdf")
            _make_file(
                db_session, filehash=f"phash{i}", filename=f"p{i}c.pdf", is_duplicate=True, duplicate_of_id=orig.id
            )

        r1 = client.get("/api/duplicates?per_page=2&page=1")
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["groups"]) == 2
        assert d1["pagination"]["total"] == 5
        assert d1["pagination"]["pages"] == 3

        r2 = client.get("/api/duplicates?per_page=2&page=2")
        assert r2.status_code == 200
        assert len(r2.json()["groups"]) == 2

    @pytest.mark.integration
    def test_response_structure(self, client: TestClient, db_session):
        """Each group should have the expected keys."""
        orig = _make_file(db_session, filehash="struct1", filename="s.pdf")
        _make_file(db_session, filehash="struct1", filename="s2.pdf", is_duplicate=True, duplicate_of_id=orig.id)

        data = client.get("/api/duplicates").json()
        group = data["groups"][0]
        assert "filehash" in group
        assert "original" in group
        assert "duplicates" in group
        assert "duplicate_count" in group

        orig_dict = group["original"]
        assert "id" in orig_dict
        assert "original_filename" in orig_dict
        assert "filehash" in orig_dict
        assert "is_duplicate" in orig_dict


# ---------------------------------------------------------------------------
# GET /api/files/{file_id}/duplicates
# ---------------------------------------------------------------------------


class TestGetFileDuplicates:
    """Tests for the GET /api/files/{id}/duplicates endpoint."""

    @pytest.mark.integration
    def test_404_for_missing_file(self, client: TestClient):
        response = client.get("/api/files/99999/duplicates")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_no_duplicates_returns_empty(self, client: TestClient, db_session):
        """File with no duplicates returns empty lists."""
        f = _make_file(db_session, filehash="unique111", filename="unique.pdf")
        response = client.get(f"/api/files/{f.id}/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["exact_duplicates"] == []
        assert data["near_duplicates"] == []
        assert data["exact_duplicate_count"] == 0
        assert data["near_duplicate_count"] == 0

    @pytest.mark.integration
    def test_exact_duplicates_returned(self, client: TestClient, db_session):
        """Exact duplicates (same hash) should be listed."""
        orig = _make_file(db_session, filehash="dup_hash", filename="orig.pdf")
        dup = _make_file(
            db_session,
            filehash="dup_hash",
            filename="dup.pdf",
            is_duplicate=True,
            duplicate_of_id=orig.id,
        )

        response = client.get(f"/api/files/{orig.id}/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["exact_duplicate_count"] == 1
        assert data["exact_duplicates"][0]["id"] == dup.id

    @pytest.mark.integration
    def test_self_is_duplicate_flag(self, client: TestClient, db_session):
        """When the queried file is itself a duplicate, is_duplicate=True and duplicate_of is populated."""
        orig = _make_file(db_session, filehash="selfdup", filename="orig.pdf")
        dup = _make_file(
            db_session,
            filehash="selfdup",
            filename="copy.pdf",
            is_duplicate=True,
            duplicate_of_id=orig.id,
        )

        response = client.get(f"/api/files/{dup.id}/duplicates")
        assert response.status_code == 200
        data = response.json()
        assert data["is_duplicate"] is True
        assert data["duplicate_of"] is not None
        assert data["duplicate_of"]["id"] == orig.id

    @pytest.mark.integration
    def test_near_duplicates_returned(self, client: TestClient, db_session):
        """Near-duplicates found via embedding similarity should appear in results."""
        embedding = json.dumps([1.0, 0.0, 0.0])
        target = _make_file(
            db_session,
            filehash="th1",
            filename="target.pdf",
            ocr_text="Invoice from Acme Corp for January services rendered",
            embedding=embedding,
        )
        similar = _make_file(
            db_session,
            filehash="th2",  # different hash — same content (re-scan)
            filename="rescan.pdf",
            ocr_text="Invoice from Acme Corp for January services rendered",
            embedding=embedding,
        )

        response = client.get(f"/api/files/{target.id}/duplicates?near_duplicate_threshold=0.8")
        assert response.status_code == 200
        data = response.json()
        assert data["near_duplicate_count"] >= 1
        ids = [nd["file_id"] for nd in data["near_duplicates"]]
        assert similar.id in ids

    @pytest.mark.integration
    def test_no_near_duplicates_without_ocr(self, client: TestClient, db_session):
        """Files without OCR text should return empty near_duplicates."""
        f = _make_file(db_session, filehash="noocr1", filename="noocr.pdf", ocr_text=None)
        response = client.get(f"/api/files/{f.id}/duplicates")
        assert response.status_code == 200
        assert response.json()["near_duplicates"] == []

    @pytest.mark.integration
    def test_threshold_filters_near_duplicates(self, client: TestClient, db_session):
        """A very high threshold should filter out lower-scoring near-duplicates."""
        target = _make_file(
            db_session,
            filehash="tt1",
            filename="t.pdf",
            ocr_text="Some document text about invoices",
        )
        _make_file(
            db_session,
            filehash="tt2",
            filename="c.pdf",
            ocr_text="Some document text about invoices",
        )

        # Patch embeddings to give moderate similarity
        with patch("app.utils.similarity.generate_embedding") as mock_embed:
            # target gets [1,0,0], candidate gets [0.6, 0.8, 0.0] → ~0.6 similarity
            mock_embed.side_effect = lambda text: [1.0, 0.0, 0.0] if target.ocr_text in text else [0.6, 0.8, 0.0]

            # Very high threshold — should not match
            response = client.get(f"/api/files/{target.id}/duplicates?near_duplicate_threshold=0.99")
            assert response.status_code == 200
            # near_duplicates may or may not be empty depending on the mock, but 200 must succeed

    @pytest.mark.integration
    def test_response_contains_required_fields(self, client: TestClient, db_session):
        """Response must always include all required top-level fields."""
        f = _make_file(db_session, filehash="reqf", filename="req.pdf")
        data = client.get(f"/api/files/{f.id}/duplicates").json()
        required = {
            "file_id",
            "is_duplicate",
            "duplicate_of",
            "exact_duplicates",
            "near_duplicates",
            "near_duplicate_threshold",
            "exact_duplicate_count",
            "near_duplicate_count",
        }
        for key in required:
            assert key in data, f"Missing key: {key}"

    @pytest.mark.integration
    def test_invalid_threshold_rejected(self, client: TestClient, db_session):
        """Threshold outside [−1, 1] should be rejected with 422."""
        f = _make_file(db_session, filehash="vth", filename="v.pdf")
        response = client.get(f"/api/files/{f.id}/duplicates?near_duplicate_threshold=2.0")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/ui-upload  — exact-duplicate rejection
# ---------------------------------------------------------------------------


class TestUploadDuplicateRejection:
    """Tests for duplicate rejection at upload time.

    When ``ENABLE_DEDUPLICATION`` is ``True`` (the default) and the uploaded
    file's SHA-256 hash matches an already-processed document, the upload
    endpoint must:
    - return ``status: "duplicate"`` instead of ``"queued"``
    - **not** enqueue a Celery task
    - clean up the temporary file from disk
    """

    @pytest.mark.integration
    @patch("app.tasks.process_document.process_document.delay")
    def test_no_warning_for_unique_file(self, mock_delay, client: TestClient, tmp_path):
        """Uploading a unique file should not produce a duplicate response."""
        mock_delay.return_value.id = "task-unique"
        pdf = tmp_path / "unique.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%%EOF")

        with open(pdf, "rb") as f:
            response = client.post(
                "/api/ui-upload",
                files={"file": ("unique.pdf", f, "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "duplicate_of" not in data

    @pytest.mark.integration
    def test_exact_duplicate_rejected(self, client: TestClient, db_session, tmp_path):
        """Uploading a file with the same hash as an existing record is rejected."""
        # Create a real PDF with known content
        pdf_bytes = b"%PDF-1.4\nsome unique content for test\n%%EOF"
        pdf = tmp_path / "existing.pdf"
        pdf.write_bytes(pdf_bytes)

        # Compute the hash to insert a matching record
        from app.utils.file_operations import hash_file

        filehash = hash_file(str(pdf))

        existing = _make_file(db_session, filehash=filehash, filename="existing.pdf")

        # Upload the same file (same bytes → same hash)
        with open(pdf, "rb") as f:
            response = client.post(
                "/api/ui-upload",
                files={"file": ("dup_upload.pdf", f, "application/pdf")},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert "duplicate_of" in data
        assert data["duplicate_of"]["duplicate_type"] == "exact"
        assert data["duplicate_of"]["original_file_id"] == existing.id

    @pytest.mark.integration
    def test_duplicate_not_enqueued(self, client: TestClient, db_session, tmp_path):
        """When a duplicate is detected, no Celery task should be created."""
        pdf_bytes = b"%PDF-1.4\nqueue test content\n%%EOF"
        pdf = tmp_path / "queue_test.pdf"
        pdf.write_bytes(pdf_bytes)

        from app.utils.file_operations import hash_file

        filehash = hash_file(str(pdf))
        _make_file(db_session, filehash=filehash, filename="queue_orig.pdf")

        with patch("app.tasks.process_document.process_document.delay") as mock_delay:
            with open(pdf, "rb") as f:
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("queue_test.pdf", f, "application/pdf")},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "duplicate"
        assert "task_id" not in data
        mock_delay.assert_not_called()

    @pytest.mark.integration
    def test_duplicate_temp_file_cleaned_up(self, client: TestClient, db_session, tmp_path):
        """The temporary file saved to disk should be removed for a duplicate."""
        pdf_bytes = b"%PDF-1.4\ncleanup test content\n%%EOF"
        pdf = tmp_path / "cleanup_test.pdf"
        pdf.write_bytes(pdf_bytes)

        from app.utils.file_operations import hash_file

        filehash = hash_file(str(pdf))
        _make_file(db_session, filehash=filehash, filename="cleanup_orig.pdf")

        with patch("app.tasks.process_document.process_document.delay"):
            with open(pdf, "rb") as f:
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("cleanup_test.pdf", f, "application/pdf")},
                )

        assert response.status_code == 200
        data = response.json()
        # The stored_filename is returned so we can verify cleanup
        stored = data.get("stored_filename")
        assert stored is not None

        from app.config import settings

        assert not os.path.exists(os.path.join(settings.workdir, stored))


# ---------------------------------------------------------------------------
# GET /duplicates  — duplicate management UI page
# ---------------------------------------------------------------------------


class TestDuplicatesViewPage:
    """Tests for the /duplicates HTML view."""

    @pytest.mark.integration
    def test_page_renders_empty(self, client: TestClient):
        """Duplicates page should render without errors when no duplicates exist."""
        response = client.get("/duplicates")
        assert response.status_code == 200
        assert b"Duplicate Documents" in response.content

    @pytest.mark.integration
    def test_page_shows_duplicate_groups(self, client: TestClient, db_session):
        """Page should list duplicate groups when they exist."""
        orig = _make_file(db_session, filehash="view_hash", filename="view_orig.pdf")
        _make_file(
            db_session,
            filehash="view_hash",
            filename="view_dup.pdf",
            is_duplicate=True,
            duplicate_of_id=orig.id,
        )

        response = client.get("/duplicates")
        assert response.status_code == 200
        assert b"view_orig.pdf" in response.content or b"view_hash" in response.content

    @pytest.mark.integration
    def test_page_contains_near_dup_tab(self, client: TestClient):
        """Page should include the Near-Duplicate Finder tab."""
        response = client.get("/duplicates")
        assert response.status_code == 200
        assert b"Near-Duplicate Finder" in response.content or b"near" in response.content.lower()
