"""Tests for document similarity detection.

Tests the similarity utility functions and the API endpoint
``GET /api/files/{file_id}/similar``.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord
from app.utils.similarity import cosine_similarity, find_similar_documents

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
    @patch("app.utils.similarity.generate_embedding")
    def test_finds_similar_documents(self, mock_embed, db_session):
        """Should find similar documents based on embedding similarity."""
        # Create a target file with OCR text
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/target.pdf",
            file_size=1024,
            original_filename="target.pdf",
            ocr_text="This is an invoice from Amazon for January 2026",
        )
        # Create a similar file
        similar = FileRecord(
            filehash="hash2",
            local_filename="/tmp/similar.pdf",
            file_size=2048,
            original_filename="similar.pdf",
            ocr_text="This is an invoice from Amazon for February 2026",
            document_title="Amazon Invoice Feb",
            mime_type="application/pdf",
        )
        # Create a different file
        different = FileRecord(
            filehash="hash3",
            local_filename="/tmp/different.pdf",
            file_size=512,
            original_filename="different.pdf",
            ocr_text="Recipe for chocolate cake with detailed instructions",
            document_title="Chocolate Cake Recipe",
            mime_type="application/pdf",
        )

        db_session.add_all([target, similar, different])
        db_session.commit()

        # Mock embeddings that reflect similarity
        target_embedding = [1.0, 0.0, 0.0]
        similar_embedding = [0.95, 0.05, 0.0]
        different_embedding = [0.0, 0.0, 1.0]

        def mock_embed_side_effect(text):
            if "January" in text or "invoice" in text.lower()[:30]:
                return target_embedding
            elif "February" in text:
                return similar_embedding
            else:
                return different_embedding

        mock_embed.side_effect = mock_embed_side_effect

        result = find_similar_documents(db_session, file_id=target.id, threshold=0.3)

        assert len(result) == 1
        assert result[0]["file_id"] == similar.id
        assert result[0]["similarity_score"] > 0.9
        assert result[0]["original_filename"] == "similar.pdf"

    @pytest.mark.unit
    @patch("app.utils.similarity.generate_embedding")
    def test_respects_threshold(self, mock_embed, db_session):
        """Should filter out documents below the threshold."""
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="target text",
        )
        candidate = FileRecord(
            filehash="hash2",
            local_filename="/tmp/c.pdf",
            file_size=100,
            original_filename="candidate.pdf",
            ocr_text="different text",
        )
        db_session.add_all([target, candidate])
        db_session.commit()

        # Return nearly orthogonal vectors -> low similarity
        mock_embed.side_effect = lambda text: [1.0, 0.0] if "target" in text else [0.1, 0.99]

        result = find_similar_documents(db_session, file_id=target.id, threshold=0.9)
        assert len(result) == 0

    @pytest.mark.unit
    @patch("app.utils.similarity.generate_embedding")
    def test_respects_limit(self, mock_embed, db_session):
        """Should respect the limit parameter."""
        target = FileRecord(
            filehash="hash0",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="target text",
        )
        db_session.add(target)

        for i in range(5):
            f = FileRecord(
                filehash=f"hash{i + 1}",
                local_filename=f"/tmp/c{i}.pdf",
                file_size=100,
                original_filename=f"candidate_{i}.pdf",
                ocr_text=f"similar text {i}",
            )
            db_session.add(f)
        db_session.commit()

        mock_embed.return_value = [1.0, 0.0, 0.0]

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
    @patch("app.utils.similarity.generate_embedding")
    def test_returns_similar_documents(self, mock_embed, client: TestClient, db_session):
        """Should return similar documents with scores."""
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/target.pdf",
            file_size=1024,
            original_filename="target.pdf",
            ocr_text="Invoice from Amazon January 2026",
        )
        similar = FileRecord(
            filehash="hash2",
            local_filename="/tmp/similar.pdf",
            file_size=2048,
            original_filename="similar_invoice.pdf",
            ocr_text="Invoice from Amazon February 2026",
            document_title="Amazon Invoice",
            mime_type="application/pdf",
        )
        db_session.add_all([target, similar])
        db_session.commit()

        mock_embed.return_value = [1.0, 0.0, 0.0]

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
    @patch("app.utils.similarity.generate_embedding")
    def test_query_parameters(self, mock_embed, client: TestClient, db_session):
        """Should respect limit and threshold query parameters."""
        target = FileRecord(
            filehash="hash1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="t.pdf",
            ocr_text="test",
        )
        db_session.add(target)

        for i in range(5):
            f = FileRecord(
                filehash=f"h{i}",
                local_filename=f"/tmp/c{i}.pdf",
                file_size=100,
                original_filename=f"c{i}.pdf",
                ocr_text=f"text {i}",
            )
            db_session.add(f)
        db_session.commit()

        mock_embed.return_value = [1.0, 0.0]

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
    @patch("app.utils.similarity.generate_embedding")
    def test_response_structure(self, mock_embed, client: TestClient, db_session):
        """Should return proper response structure for each similar document."""
        target = FileRecord(
            filehash="h1",
            local_filename="/tmp/t.pdf",
            file_size=100,
            original_filename="target.pdf",
            ocr_text="Some text content here",
        )
        other = FileRecord(
            filehash="h2",
            local_filename="/tmp/o.pdf",
            file_size=200,
            original_filename="other.pdf",
            ocr_text="Some similar text content",
            document_title="Other Doc",
            mime_type="application/pdf",
        )
        db_session.add_all([target, other])
        db_session.commit()

        mock_embed.return_value = [1.0, 0.0]

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
