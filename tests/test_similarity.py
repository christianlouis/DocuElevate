"""Tests for document similarity detection.

Tests the similarity utility functions and the API endpoint
``GET /api/files/{file_id}/similar``.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord
from app.utils.similarity import (
    _get_cached_embedding,
    compute_and_store_embedding,
    cosine_similarity,
    find_similar_documents,
    generate_embedding,
)

# ---------------------------------------------------------------------------
# Unit tests for cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Unit tests for the cosine_similarity function."""

    @pytest.mark.unit
    def test_identical_vectors_return_one(self):
        """Identical vectors should have similarity of 1.0."""
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    @pytest.mark.unit
    def test_orthogonal_vectors_return_zero(self):
        """Orthogonal vectors should have similarity of 0.0."""
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    @pytest.mark.unit
    def test_opposite_vectors_clamped_to_zero(self):
        """Opposite vectors would give negative cosine; clamp to 0."""
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert cosine_similarity(a, b) == 0.0

    @pytest.mark.unit
    def test_different_length_vectors_return_zero(self):
        """Vectors of different lengths should return 0.0."""
        a = [1.0, 2.0, 3.0]
        b = [1.0, 2.0]
        assert cosine_similarity(a, b) == 0.0

    @pytest.mark.unit
    def test_zero_vector_returns_zero(self):
        """Zero-magnitude vector should return 0.0."""
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    @pytest.mark.unit
    def test_similar_vectors_high_score(self):
        """Similar (but not identical) vectors should have a high score."""
        a = [1.0, 2.0, 3.0]
        b = [1.1, 2.1, 3.1]
        score = cosine_similarity(a, b)
        assert 0.99 < score <= 1.0

    @pytest.mark.unit
    def test_score_between_zero_and_one(self):
        """All scores should be in [0, 1]."""
        a = [1.0, 0.5, 0.0]
        b = [0.0, 0.5, 1.0]
        score = cosine_similarity(a, b)
        assert 0.0 <= score <= 1.0

    @pytest.mark.unit
    def test_empty_vectors_return_zero(self):
        """Empty vectors should return 0.0."""
        assert cosine_similarity([], []) == 0.0


# ---------------------------------------------------------------------------
# Unit tests for find_similar_documents
# ---------------------------------------------------------------------------


class TestFindSimilarDocuments:
    """Unit tests for the find_similar_documents function."""

    @pytest.mark.unit
    def test_returns_empty_for_missing_file(self, db_session):
        """Should return empty list when file ID does not exist."""
        result = find_similar_documents(db_session, file_id=9999)
        assert result == []

    @pytest.mark.unit
    def test_returns_empty_when_no_ocr_text(self, db_session):
        """Should return empty list when target file has no OCR text."""
        file_record = FileRecord(
            filehash="abc123",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            original_filename="test.pdf",
            ocr_text=None,
        )
        db_session.add(file_record)
        db_session.commit()

        result = find_similar_documents(db_session, file_id=file_record.id)
        assert result == []

    @pytest.mark.unit
    def test_finds_similar_documents(self, db_session):
        """Should find similar documents based on pre-computed embedding similarity."""
        # Pre-computed embeddings that reflect similarity
        target_embedding = [1.0, 0.0, 0.0]
        similar_embedding = [0.95, 0.05, 0.0]
        different_embedding = [0.0, 0.0, 1.0]

        # Create a target file with pre-computed embedding
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/target.pdf",
            file_size=1024,
            original_filename="target.pdf",
            ocr_text="This is an invoice from Amazon for January 2026",
            embedding=json.dumps(target_embedding),
        )
        # Create a similar file with pre-computed embedding
        similar = FileRecord(
            filehash="hash2",
            local_filename="/tmp/similar.pdf",
            file_size=2048,
            original_filename="similar.pdf",
            ocr_text="This is an invoice from Amazon for February 2026",
            document_title="Amazon Invoice Feb",
            mime_type="application/pdf",
            embedding=json.dumps(similar_embedding),
        )
        # Create a different file with pre-computed embedding
        different = FileRecord(
            filehash="hash3",
            local_filename="/tmp/different.pdf",
            file_size=512,
            original_filename="different.pdf",
            ocr_text="Recipe for chocolate cake with detailed instructions",
            document_title="Chocolate Cake Recipe",
            mime_type="application/pdf",
            embedding=json.dumps(different_embedding),
        )

        db_session.add_all([target, similar, different])
        db_session.commit()

        result = find_similar_documents(db_session, file_id=target.id, threshold=0.3)

        assert len(result) == 1
        assert result[0]["file_id"] == similar.id
        assert result[0]["similarity_score"] > 0.9
        assert result[0]["original_filename"] == "similar.pdf"

    @pytest.mark.unit
    def test_respects_threshold(self, db_session):
        """Should filter out documents below the threshold."""
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="target text",
            embedding=json.dumps([1.0, 0.0]),
        )
        candidate = FileRecord(
            filehash="hash2",
            local_filename="/tmp/c.pdf",
            file_size=100,
            original_filename="candidate.pdf",
            ocr_text="different text",
            embedding=json.dumps([0.1, 0.99]),
        )
        db_session.add_all([target, candidate])
        db_session.commit()

        result = find_similar_documents(db_session, file_id=target.id, threshold=0.9)
        assert len(result) == 0

    @pytest.mark.unit
    def test_respects_limit(self, db_session):
        """Should respect the limit parameter."""
        embedding = [1.0, 0.0, 0.0]
        target = FileRecord(
            filehash="hash0",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="target text",
            embedding=json.dumps(embedding),
        )
        db_session.add(target)

        for i in range(5):
            f = FileRecord(
                filehash=f"hash{i + 1}",
                local_filename=f"/tmp/c{i}.pdf",
                file_size=100,
                original_filename=f"candidate_{i}.pdf",
                ocr_text=f"similar text {i}",
                embedding=json.dumps(embedding),
            )
            db_session.add(f)
        db_session.commit()

        result = find_similar_documents(db_session, file_id=target.id, limit=2, threshold=0.0)
        assert len(result) <= 2

    @pytest.mark.unit
    def test_uses_cached_embedding(self, db_session):
        """Should use cached embeddings from the database."""
        cached_embedding = [0.5, 0.5, 0.5]

        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="some text",
            embedding=json.dumps(cached_embedding),
        )
        candidate = FileRecord(
            filehash="hash2",
            local_filename="/tmp/c.pdf",
            file_size=100,
            original_filename="candidate.pdf",
            ocr_text="some text too",
            embedding=json.dumps(cached_embedding),
        )
        db_session.add_all([target, candidate])
        db_session.commit()

        # No mock needed — cached embeddings should be used
        result = find_similar_documents(db_session, file_id=target.id, threshold=0.0)
        assert len(result) == 1
        assert result[0]["similarity_score"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Integration tests for the API endpoint
# ---------------------------------------------------------------------------


class TestSimilarDocumentsAPI:
    """Integration tests for GET /api/files/{file_id}/similar."""

    @pytest.mark.integration
    def test_file_not_found(self, client: TestClient):
        """Should return 404 for non-existent file."""
        response = client.get("/api/files/9999/similar")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_no_ocr_text(self, client: TestClient, db_session):
        """Should return empty results when file has no OCR text."""
        file_record = FileRecord(
            filehash="abc123",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            original_filename="test.pdf",
            ocr_text=None,
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/similar")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["similar_documents"] == []
        assert "message" in data

    @pytest.mark.integration
    def test_returns_similar_documents(self, client: TestClient, db_session):
        """Should return similar documents with scores."""
        embedding = [1.0, 0.0, 0.0]
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/target.pdf",
            file_size=1024,
            original_filename="target.pdf",
            ocr_text="Invoice from Amazon January 2026",
            embedding=json.dumps(embedding),
        )
        similar = FileRecord(
            filehash="hash2",
            local_filename="/tmp/similar.pdf",
            file_size=2048,
            original_filename="similar_invoice.pdf",
            ocr_text="Invoice from Amazon February 2026",
            document_title="Amazon Invoice",
            mime_type="application/pdf",
            embedding=json.dumps(embedding),
        )
        db_session.add_all([target, similar])
        db_session.commit()

        response = client.get(f"/api/files/{target.id}/similar")
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == target.id
        assert data["count"] >= 1
        assert len(data["similar_documents"]) >= 1

        doc = data["similar_documents"][0]
        assert "file_id" in doc
        assert "similarity_score" in doc
        assert 0 <= doc["similarity_score"] <= 1
        assert "original_filename" in doc

    @pytest.mark.integration
    def test_query_parameters(self, client: TestClient, db_session):
        """Should respect limit and threshold query parameters."""
        embedding = [1.0, 0.0]
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="t.pdf",
            ocr_text="test",
            embedding=json.dumps(embedding),
        )
        db_session.add(target)

        for i in range(5):
            f = FileRecord(
                filehash=f"h{i}",
                local_filename=f"/tmp/c{i}.pdf",
                file_size=100,
                original_filename=f"c{i}.pdf",
                ocr_text=f"text {i}",
                embedding=json.dumps(embedding),
            )
            db_session.add(f)
        db_session.commit()

        response = client.get(f"/api/files/{target.id}/similar?limit=2&threshold=0.0")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] <= 2

    @pytest.mark.integration
    def test_invalid_limit(self, client: TestClient, db_session):
        """Should reject invalid limit values."""
        file_record = FileRecord(
            filehash="abc",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="t.pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/similar?limit=0")
        assert response.status_code == 422

    @pytest.mark.integration
    def test_invalid_threshold(self, client: TestClient, db_session):
        """Should reject threshold values outside [0, 1]."""
        file_record = FileRecord(
            filehash="abc",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="t.pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/similar?threshold=1.5")
        assert response.status_code == 422

    @pytest.mark.integration
    def test_empty_ocr_text(self, client: TestClient, db_session):
        """Should return empty results when OCR text is empty string."""
        file_record = FileRecord(
            filehash="abc",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="t.pdf",
            ocr_text="",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/similar")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0

    @pytest.mark.integration
    def test_embedding_not_computed_message(self, client: TestClient, db_session):
        """Should return a message when OCR text exists but no embedding yet."""
        file_record = FileRecord(
            filehash="noembhash",
            local_filename="/tmp/noemb.pdf",
            file_size=100,
            original_filename="noemb.pdf",
            ocr_text="Some OCR text content",
            embedding=None,
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/similar")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert "message" in data
        assert "not yet computed" in data["message"].lower()

    def test_response_structure(self, client: TestClient, db_session):
        """Should return proper response structure for each similar document."""
        embedding = [1.0, 0.0]
        target = FileRecord(
            filehash="h1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="Some text content here",
            embedding=json.dumps(embedding),
        )
        other = FileRecord(
            filehash="h2",
            local_filename="/tmp/o.pdf",
            file_size=200,
            original_filename="other.pdf",
            ocr_text="Some similar text content",
            document_title="Other Doc",
            mime_type="application/pdf",
            embedding=json.dumps(embedding),
        )
        db_session.add_all([target, other])
        db_session.commit()

        response = client.get(f"/api/files/{target.id}/similar")
        assert response.status_code == 200
        data = response.json()

        assert "file_id" in data
        assert "similar_documents" in data
        assert "count" in data

        if data["count"] > 0:
            doc = data["similar_documents"][0]
            assert "file_id" in doc
            assert "original_filename" in doc
            assert "document_title" in doc
            assert "similarity_score" in doc
            assert "mime_type" in doc
            assert "created_at" in doc


# ---------------------------------------------------------------------------
# Tests for embedding status endpoint
# ---------------------------------------------------------------------------


class TestEmbeddingStatusAPI:
    """Integration tests for GET /api/files/{file_id}/embedding-status."""

    @pytest.mark.integration
    def test_file_not_found(self, client: TestClient):
        """Should return 404 for non-existent file."""
        response = client.get("/api/files/9999/embedding-status")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_file_without_embedding_or_ocr(self, client: TestClient, db_session):
        """Should report no embedding and no OCR text."""
        file_record = FileRecord(
            filehash="abc1",
            local_filename="/tmp/test.pdf",
            file_size=100,
            original_filename="test.pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/embedding-status")
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == file_record.id
        assert data["has_embedding"] is False
        assert data["embedding_dimensions"] is None
        assert data["has_ocr_text"] is False
        assert data["ocr_text_length"] == 0
        assert "embedding_model" in data

    @pytest.mark.integration
    def test_file_with_ocr_text_no_embedding(self, client: TestClient, db_session):
        """Should report OCR text present but no embedding."""
        file_record = FileRecord(
            filehash="abc2",
            local_filename="/tmp/test2.pdf",
            file_size=100,
            original_filename="test2.pdf",
            ocr_text="Some OCR text content",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/embedding-status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_embedding"] is False
        assert data["has_ocr_text"] is True
        assert data["ocr_text_length"] == 21

    @pytest.mark.integration
    def test_file_with_cached_embedding(self, client: TestClient, db_session):
        """Should report embedding present with correct dimensions."""
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        file_record = FileRecord(
            filehash="abc3",
            local_filename="/tmp/test3.pdf",
            file_size=100,
            original_filename="test3.pdf",
            ocr_text="Some text",
            embedding=json.dumps(embedding),
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.get(f"/api/files/{file_record.id}/embedding-status")
        assert response.status_code == 200
        data = response.json()
        assert data["has_embedding"] is True
        assert data["embedding_dimensions"] == 5
        assert data["has_ocr_text"] is True


# ---------------------------------------------------------------------------
# Tests for compute-embedding endpoint
# ---------------------------------------------------------------------------


class TestComputeEmbeddingAPI:
    """Integration tests for POST /api/files/{file_id}/compute-embedding."""

    @pytest.mark.integration
    def test_file_not_found(self, client: TestClient):
        """Should return 404 for non-existent file."""
        response = client.post("/api/files/9999/compute-embedding")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_no_ocr_text(self, client: TestClient, db_session):
        """Should return 400 when file has no OCR text."""
        file_record = FileRecord(
            filehash="emb1",
            local_filename="/tmp/emb1.pdf",
            file_size=100,
            original_filename="emb1.pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post(f"/api/files/{file_record.id}/compute-embedding")
        assert response.status_code == 400

    @pytest.mark.integration
    @patch("app.utils.similarity.generate_embedding")
    def test_computes_embedding(self, mock_embed, client: TestClient, db_session):
        """Should compute and store an embedding."""
        mock_embed.return_value = [0.1, 0.2, 0.3]

        file_record = FileRecord(
            filehash="emb2",
            local_filename="/tmp/emb2.pdf",
            file_size=100,
            original_filename="emb2.pdf",
            ocr_text="Some document text",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post(f"/api/files/{file_record.id}/compute-embedding")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["embedding_dimensions"] == 3

        # Verify embedding is stored
        db_session.refresh(file_record)
        assert file_record.embedding is not None
        stored = json.loads(file_record.embedding)
        assert len(stored) == 3

    @pytest.mark.integration
    @patch("app.utils.similarity.generate_embedding")
    def test_recomputes_existing_embedding(self, mock_embed, client: TestClient, db_session):
        """Should overwrite existing embedding when recomputing."""
        mock_embed.return_value = [0.9, 0.8, 0.7]

        file_record = FileRecord(
            filehash="emb3",
            local_filename="/tmp/emb3.pdf",
            file_size=100,
            original_filename="emb3.pdf",
            ocr_text="Some text",
            embedding=json.dumps([0.1, 0.2, 0.3]),
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post(f"/api/files/{file_record.id}/compute-embedding")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

        db_session.refresh(file_record)
        stored = json.loads(file_record.embedding)
        assert stored == [0.9, 0.8, 0.7]


# ---------------------------------------------------------------------------
# Tests for diagnostic embeddings overview endpoint
# ---------------------------------------------------------------------------


class TestEmbeddingsOverviewAPI:
    """Integration tests for GET /api/diagnostic/embeddings."""

    @pytest.mark.integration
    def test_empty_database(self, client: TestClient):
        """Should return zero counts on empty database."""
        response = client.get("/api/diagnostic/embeddings")
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0
        assert data["files_with_ocr_text"] == 0
        assert data["files_with_embedding"] == 0
        assert data["files_missing_embedding"] == 0
        assert "embedding_model" in data
        assert data["files"] == []

    @pytest.mark.integration
    def test_mixed_files(self, client: TestClient, db_session):
        """Should report correct counts for mixed embedding states."""
        # File with both OCR text and embedding
        f1 = FileRecord(
            filehash="diag1",
            local_filename="/tmp/d1.pdf",
            file_size=100,
            original_filename="d1.pdf",
            ocr_text="Some text",
            embedding=json.dumps([0.1, 0.2]),
        )
        # File with OCR text but no embedding
        f2 = FileRecord(
            filehash="diag2",
            local_filename="/tmp/d2.pdf",
            file_size=100,
            original_filename="d2.pdf",
            ocr_text="More text",
        )
        # File with no OCR text
        f3 = FileRecord(
            filehash="diag3",
            local_filename="/tmp/d3.pdf",
            file_size=100,
            original_filename="d3.pdf",
        )
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        response = client.get("/api/diagnostic/embeddings")
        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 3
        assert data["files_with_ocr_text"] == 2
        assert data["files_with_embedding"] == 1
        assert data["files_missing_embedding"] == 1
        assert len(data["files"]) == 3

        # Check per-file info
        files_by_id = {f["file_id"]: f for f in data["files"]}
        assert files_by_id[f1.id]["has_embedding"] is True
        assert files_by_id[f1.id]["embedding_dimensions"] == 2
        assert files_by_id[f2.id]["has_embedding"] is False
        assert files_by_id[f2.id]["has_ocr_text"] is True
        assert files_by_id[f3.id]["has_ocr_text"] is False


# ---------------------------------------------------------------------------
# Tests for compute-all-embeddings endpoint
# ---------------------------------------------------------------------------


class TestComputeAllEmbeddingsAPI:
    """Integration tests for POST /api/diagnostic/compute-all-embeddings."""

    @pytest.mark.integration
    @patch("app.tasks.compute_embedding.compute_document_embedding.delay")
    def test_queues_tasks_for_files_missing_embeddings(self, mock_delay, client: TestClient, db_session):
        """Should queue embedding tasks for files with OCR text but no embedding."""
        # File with OCR text but no embedding -> should be queued
        f1 = FileRecord(
            filehash="all1",
            local_filename="/tmp/a1.pdf",
            file_size=100,
            original_filename="a1.pdf",
            ocr_text="Text for embedding",
        )
        # File already with embedding -> should NOT be queued
        f2 = FileRecord(
            filehash="all2",
            local_filename="/tmp/a2.pdf",
            file_size=100,
            original_filename="a2.pdf",
            ocr_text="More text",
            embedding=json.dumps([0.1, 0.2]),
        )
        # File without OCR text -> should NOT be queued
        f3 = FileRecord(
            filehash="all3",
            local_filename="/tmp/a3.pdf",
            file_size=100,
            original_filename="a3.pdf",
        )
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        response = client.post("/api/diagnostic/compute-all-embeddings")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert data["files_queued"] == 1
        mock_delay.assert_called_once_with(f1.id)

    @pytest.mark.integration
    @patch("app.tasks.compute_embedding.compute_document_embedding.delay")
    def test_empty_database_queues_nothing(self, mock_delay, client: TestClient):
        """Should queue nothing when database is empty."""
        response = client.post("/api/diagnostic/compute-all-embeddings")
        assert response.status_code == 200
        data = response.json()
        assert data["files_queued"] == 0
        mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for compute_document_embedding Celery task
# ---------------------------------------------------------------------------


class TestComputeDocumentEmbeddingTask:
    """Unit tests for the compute_document_embedding Celery task."""

    @pytest.mark.unit
    @patch("app.utils.similarity.generate_embedding")
    def test_computes_embedding_for_file(self, mock_embed, db_session):
        """Should compute and store embedding when file has OCR text."""
        mock_embed.return_value = [0.1, 0.2, 0.3]

        file_record = FileRecord(
            filehash="task1",
            local_filename="/tmp/task1.pdf",
            file_size=100,
            original_filename="task1.pdf",
            ocr_text="Some document text",
        )
        db_session.add(file_record)
        db_session.commit()

        from app.tasks.compute_embedding import compute_document_embedding

        # Patch SessionLocal to return our test session
        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = compute_document_embedding(file_record.id)

        assert result["status"] == "success"
        assert "dimensions" in result["detail"]

    @pytest.mark.unit
    def test_skips_missing_file(self, db_session):
        """Should skip when file ID does not exist."""
        from app.tasks.compute_embedding import compute_document_embedding

        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = compute_document_embedding(9999)

        assert result["status"] == "skipped"

    @pytest.mark.unit
    def test_skips_file_without_ocr_text(self, db_session):
        """Should skip when file has no OCR text."""
        file_record = FileRecord(
            filehash="task2",
            local_filename="/tmp/task2.pdf",
            file_size=100,
            original_filename="task2.pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        from app.tasks.compute_embedding import compute_document_embedding

        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = compute_document_embedding(file_record.id)

        assert result["status"] == "skipped"

    @pytest.mark.unit
    def test_skips_file_with_existing_embedding(self, db_session):
        """Should skip when file already has a cached embedding."""
        file_record = FileRecord(
            filehash="task3",
            local_filename="/tmp/task3.pdf",
            file_size=100,
            original_filename="task3.pdf",
            ocr_text="Some text",
            embedding=json.dumps([0.1, 0.2]),
        )
        db_session.add(file_record)
        db_session.commit()

        from app.tasks.compute_embedding import compute_document_embedding

        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = compute_document_embedding(file_record.id)

        assert result["status"] == "skipped"
        assert "already cached" in result["detail"]


# ---------------------------------------------------------------------------
# Tests for similarity pairs endpoint
# ---------------------------------------------------------------------------


class TestSimilarityPairsAPI:
    """Integration tests for GET /api/similarity/pairs."""

    @pytest.mark.integration
    def test_empty_database(self, client: TestClient):
        """Should return zero pairs on empty database."""
        response = client.get("/api/similarity/pairs")
        assert response.status_code == 200
        data = response.json()
        assert data["total_pairs"] == 0
        assert data["pairs"] == []
        assert "embedding_coverage" in data

    @pytest.mark.integration
    def test_finds_similar_pairs(self, client: TestClient, db_session):
        """Should find and return pairs of similar files."""
        emb_a = [1.0, 0.0, 0.0]
        emb_b = [0.98, 0.02, 0.0]  # Very similar to A
        emb_c = [0.0, 0.0, 1.0]  # Different from A and B

        f1 = FileRecord(
            filehash="pairA",
            local_filename="/tmp/pA.pdf",
            file_size=100,
            original_filename="fileA.pdf",
            ocr_text="text A",
            embedding=json.dumps(emb_a),
        )
        f2 = FileRecord(
            filehash="pairB",
            local_filename="/tmp/pB.pdf",
            file_size=100,
            original_filename="fileB.pdf",
            ocr_text="text B",
            embedding=json.dumps(emb_b),
        )
        f3 = FileRecord(
            filehash="pairC",
            local_filename="/tmp/pC.pdf",
            file_size=100,
            original_filename="fileC.pdf",
            ocr_text="text C",
            embedding=json.dumps(emb_c),
        )
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        response = client.get("/api/similarity/pairs?threshold=0.9")
        assert response.status_code == 200
        data = response.json()

        # Only A-B pair should be above 0.9
        assert data["total_pairs"] == 1
        pair = data["pairs"][0]
        assert pair["similarity_score"] > 0.9
        pair_ids = {pair["file_a"]["file_id"], pair["file_b"]["file_id"]}
        assert pair_ids == {f1.id, f2.id}

    @pytest.mark.integration
    def test_respects_threshold(self, client: TestClient, db_session):
        """Should filter pairs below threshold."""
        emb = [1.0, 0.0]
        different_emb = [0.0, 1.0]

        f1 = FileRecord(
            filehash="thA",
            local_filename="/tmp/thA.pdf",
            file_size=100,
            original_filename="thA.pdf",
            ocr_text="a",
            embedding=json.dumps(emb),
        )
        f2 = FileRecord(
            filehash="thB",
            local_filename="/tmp/thB.pdf",
            file_size=100,
            original_filename="thB.pdf",
            ocr_text="b",
            embedding=json.dumps(different_emb),
        )
        db_session.add_all([f1, f2])
        db_session.commit()

        response = client.get("/api/similarity/pairs?threshold=0.9")
        assert response.status_code == 200
        data = response.json()
        assert data["total_pairs"] == 0

    @pytest.mark.integration
    def test_pagination(self, client: TestClient, db_session):
        """Should respect pagination parameters."""
        emb = [1.0, 0.0, 0.0]
        for i in range(5):
            f = FileRecord(
                filehash=f"pg{i}",
                local_filename=f"/tmp/pg{i}.pdf",
                file_size=100,
                original_filename=f"pg{i}.pdf",
                ocr_text=f"text {i}",
                embedding=json.dumps(emb),
            )
            db_session.add(f)
        db_session.commit()

        response = client.get("/api/similarity/pairs?threshold=0.0&limit=2&page=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["pairs"]) <= 2
        assert data["per_page"] == 2


# ---------------------------------------------------------------------------
# Tests for backfill_missing_embeddings task
# ---------------------------------------------------------------------------


class TestBackfillMissingEmbeddingsTask:
    """Unit tests for the backfill_missing_embeddings Celery task."""

    @pytest.mark.unit
    @patch("app.tasks.compute_embedding.compute_document_embedding.delay")
    def test_queues_files_without_embeddings(self, mock_delay, db_session):
        """Should queue tasks for files with OCR text but no embedding."""
        f1 = FileRecord(
            filehash="bf1",
            local_filename="/tmp/bf1.pdf",
            file_size=100,
            original_filename="bf1.pdf",
            ocr_text="Some text",
        )
        f2 = FileRecord(
            filehash="bf2",
            local_filename="/tmp/bf2.pdf",
            file_size=100,
            original_filename="bf2.pdf",
            ocr_text="More text",
            embedding=json.dumps([0.1]),
        )
        db_session.add_all([f1, f2])
        db_session.commit()

        from app.tasks.compute_embedding import backfill_missing_embeddings

        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = backfill_missing_embeddings()

        assert result["queued"] == 1
        mock_delay.assert_called_once_with(f1.id)

    @pytest.mark.unit
    @patch("app.tasks.compute_embedding.compute_document_embedding.delay")
    def test_empty_database(self, mock_delay, db_session):
        """Should queue nothing when no files need embeddings."""
        from app.tasks.compute_embedding import backfill_missing_embeddings

        with patch("app.tasks.compute_embedding.SessionLocal") as mock_session_local:
            mock_session_local.return_value.__enter__ = lambda self: db_session
            mock_session_local.return_value.__exit__ = lambda self, *args: None

            result = backfill_missing_embeddings()

        assert result["queued"] == 0
        mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests for _get_embedding_client
# ---------------------------------------------------------------------------


class TestGetEmbeddingClient:
    """Unit tests for the _get_embedding_client function."""

    @pytest.mark.unit
    def test_raises_runtime_error_when_openai_not_installed(self):
        """Should raise RuntimeError when openai package is not available."""
        from app.utils import similarity

        # Temporarily hide the openai module
        real_openai = sys.modules.get("openai")
        sys.modules["openai"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError, match="'openai' package is required"):
                similarity._get_embedding_client()
        finally:
            if real_openai is None:
                del sys.modules["openai"]
            else:
                sys.modules["openai"] = real_openai

    @pytest.mark.unit
    @patch("app.utils.similarity.settings")
    def test_returns_openai_client(self, mock_settings):
        """Should return an OpenAI client when openai is installed."""
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_base_url = "https://api.openai.com/v1"

        mock_client = MagicMock()
        mock_openai_class = MagicMock(return_value=mock_client)

        with patch.dict(sys.modules, {"openai": MagicMock(OpenAI=mock_openai_class)}):
            # Force re-import to pick up the patched module
            import importlib

            from app.utils import similarity

            importlib.reload(similarity)
            result = similarity._get_embedding_client()

        assert result is not None


# ---------------------------------------------------------------------------
# Unit tests for generate_embedding
# ---------------------------------------------------------------------------


class TestGenerateEmbedding:
    """Unit tests for the generate_embedding function."""

    @pytest.mark.unit
    @patch("app.utils.similarity._get_embedding_client")
    @patch("app.utils.similarity.settings")
    def test_uses_default_model_when_none(self, mock_settings, mock_get_client):
        """Should use settings.embedding_model when model=None is passed."""
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_max_tokens = 8000

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = generate_embedding("hello world", model=None)

        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once_with(input="hello world", model="text-embedding-3-small")

    @pytest.mark.unit
    @patch("app.utils.similarity._get_embedding_client")
    @patch("app.utils.similarity.settings")
    def test_truncates_long_text(self, mock_settings, mock_get_client):
        """Should truncate text that exceeds embedding_max_tokens * 3 characters."""
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_max_tokens = 10  # max_chars = 30

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.5])]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        long_text = "a" * 100  # 100 chars, well beyond the 30-char limit
        result = generate_embedding(long_text)

        assert result == [0.5]
        # Verify the text was truncated to 30 chars (max_tokens=10, 10*3=30)
        call_args = mock_client.embeddings.create.call_args
        actual_input = call_args.kwargs.get("input") or call_args[1].get("input") or call_args[0][0]
        assert len(actual_input) == 30

    @pytest.mark.unit
    @patch("app.utils.similarity._get_embedding_client")
    @patch("app.utils.similarity.settings")
    def test_explicit_model_used(self, mock_settings, mock_get_client):
        """Should use the provided model rather than settings.embedding_model."""
        mock_settings.embedding_model = "default-model"
        mock_settings.embedding_max_tokens = 8000

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.9])]
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        generate_embedding("some text", model="custom-model")

        mock_client.embeddings.create.assert_called_once_with(input="some text", model="custom-model")


# ---------------------------------------------------------------------------
# Unit tests for _get_cached_embedding (invalid JSON paths)
# ---------------------------------------------------------------------------


class TestGetCachedEmbeddingEdgeCases:
    """Edge-case tests for _get_cached_embedding."""

    @pytest.mark.unit
    def test_returns_none_for_invalid_json(self):
        """Should return None and log a warning for malformed JSON."""
        mock_record = MagicMock()
        mock_record.id = 42
        mock_record.embedding = "not-valid-json{"

        result = _get_cached_embedding(mock_record)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_non_string_embedding(self):
        """Should return None when json.loads raises TypeError."""
        mock_record = MagicMock()
        mock_record.id = 99
        # json.loads raises TypeError for non-string inputs other than bytes/bytearray
        mock_record.embedding = 12345  # int causes TypeError in json.loads

        result = _get_cached_embedding(mock_record)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_when_no_embedding_attr(self):
        """Should return None when file record has no embedding attribute."""

        class MinimalRecord:
            id = 1

        result = _get_cached_embedding(MinimalRecord())

        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for compute_and_store_embedding
# ---------------------------------------------------------------------------


class TestComputeAndStoreEmbedding:
    """Unit tests for compute_and_store_embedding."""

    @pytest.mark.unit
    def test_returns_cached_embedding_when_already_present(self, db_session):
        """Should return the existing embedding without calling the API."""
        cached = [0.1, 0.2, 0.3]
        file_record = FileRecord(
            filehash="cse1",
            local_filename="/tmp/cse1.pdf",
            file_size=100,
            original_filename="cse1.pdf",
            ocr_text="some text",
            embedding=json.dumps(cached),
        )
        db_session.add(file_record)
        db_session.commit()

        with patch("app.utils.similarity.generate_embedding") as mock_gen:
            result = compute_and_store_embedding(db_session, file_record)

        assert result == cached
        mock_gen.assert_not_called()

    @pytest.mark.unit
    def test_returns_none_when_no_ocr_text(self, db_session):
        """Should return None when file has no OCR text."""
        file_record = FileRecord(
            filehash="cse2",
            local_filename="/tmp/cse2.pdf",
            file_size=100,
            original_filename="cse2.pdf",
            ocr_text=None,
        )
        db_session.add(file_record)
        db_session.commit()

        result = compute_and_store_embedding(db_session, file_record)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_when_ocr_text_is_whitespace_only(self, db_session):
        """Should return None when OCR text is only whitespace."""
        file_record = FileRecord(
            filehash="cse3",
            local_filename="/tmp/cse3.pdf",
            file_size=100,
            original_filename="cse3.pdf",
            ocr_text="   \t\n  ",
        )
        db_session.add(file_record)
        db_session.commit()

        result = compute_and_store_embedding(db_session, file_record)

        assert result is None

    @pytest.mark.unit
    def test_returns_none_and_rolls_back_on_exception(self, db_session):
        """Should return None and rollback when generate_embedding raises."""
        file_record = FileRecord(
            filehash="cse4",
            local_filename="/tmp/cse4.pdf",
            file_size=100,
            original_filename="cse4.pdf",
            ocr_text="Some valid text",
        )
        db_session.add(file_record)
        db_session.commit()

        with patch("app.utils.similarity.generate_embedding", side_effect=RuntimeError("API error")):
            result = compute_and_store_embedding(db_session, file_record)

        assert result is None

    @pytest.mark.unit
    def test_handles_invalid_cached_json_and_recomputes(self, db_session):
        """Should recompute when cached embedding JSON is malformed."""
        file_record = FileRecord(
            filehash="cse5",
            local_filename="/tmp/cse5.pdf",
            file_size=100,
            original_filename="cse5.pdf",
            ocr_text="Some valid text",
            embedding="not-valid-json",
        )
        db_session.add(file_record)
        db_session.commit()

        new_embedding = [0.7, 0.8, 0.9]
        with patch("app.utils.similarity.generate_embedding", return_value=new_embedding):
            result = compute_and_store_embedding(db_session, file_record)

        assert result == new_embedding


# ---------------------------------------------------------------------------
# Unit tests for find_similar_documents (invalid candidate JSON)
# ---------------------------------------------------------------------------


class TestFindSimilarDocumentsEdgeCases:
    """Edge-case tests for find_similar_documents."""

    @pytest.mark.unit
    def test_skips_candidate_with_invalid_json_embedding(self, db_session):
        """Candidates with malformed embedding JSON should be silently skipped."""
        target_embedding = [1.0, 0.0, 0.0]
        target = FileRecord(
            filehash="fsd_t",
            local_filename="/tmp/fsd_t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="target text",
            embedding=json.dumps(target_embedding),
        )
        # This candidate has corrupt embedding JSON
        bad_candidate = FileRecord(
            filehash="fsd_b",
            local_filename="/tmp/fsd_b.pdf",
            file_size=100,
            original_filename="bad_candidate.pdf",
            ocr_text="some text",
            embedding="{invalid-json",
        )
        db_session.add_all([target, bad_candidate])
        db_session.commit()

        result = find_similar_documents(db_session, file_id=target.id, threshold=0.0)

        # bad_candidate should be skipped, not crash
        assert all(r["file_id"] != bad_candidate.id for r in result)

    @pytest.mark.unit
    def test_returns_empty_for_file_with_invalid_cached_embedding(self, db_session):
        """Should return empty list when target file's embedding is invalid JSON."""
        target = FileRecord(
            filehash="fsd_inv",
            local_filename="/tmp/fsd_inv.pdf",
            file_size=100,
            original_filename="inv.pdf",
            ocr_text="some text",
            embedding="{bad-json",
        )
        db_session.add(target)
        db_session.commit()

        result = find_similar_documents(db_session, file_id=target.id)

        assert result == []
