"""Tests for the human review queue API."""

import pytest
from fastapi.testclient import TestClient

from app.models import DocumentReviewItem, FileRecord


@pytest.mark.unit
class TestReviewQueueAPI:
    """Tests for /api/review-queue endpoints."""

    def test_list_review_queue_returns_pending_items(self, client: TestClient, db_session):
        """The review queue returns pending items with file context."""
        file_record = FileRecord(
            filehash="review-hash",
            original_filename="needs-review.pdf",
            local_filename="/tmp/needs-review.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        item = DocumentReviewItem(
            file_id=file_record.id,
            reason="Low extraction confidence",
            confidence_score=42,
            status="pending",
        )
        db_session.add(item)
        db_session.commit()

        response = client.get("/api/review-queue/")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["status"] == "pending"
        assert data["items"][0]["reason"] == "Low extraction confidence"
        assert data["items"][0]["confidence_score"] == 42
        assert data["items"][0]["file"]["original_filename"] == "needs-review.pdf"

    def test_list_review_queue_all_includes_resolved_items(self, client: TestClient, db_session):
        """The all filter includes non-pending review items."""
        file_record = FileRecord(
            filehash="review-resolved-hash",
            original_filename="resolved.pdf",
            local_filename="/tmp/resolved.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.add(
            DocumentReviewItem(
                file_id=file_record.id,
                reason="Manual check complete",
                confidence_score=91,
                status="resolved",
            )
        )
        db_session.commit()

        response = client.get("/api/review-queue/?status=all")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["status"] == "all"
        assert data["items"][0]["status"] == "resolved"

    def test_resolve_review_updates_metadata_and_prevents_second_resolution(self, client: TestClient, db_session):
        file_record = FileRecord(
            filehash="review-edit",
            original_filename="edit.pdf",
            local_filename="/tmp/edit.pdf",
            file_size=10,
            mime_type="application/pdf",
            ai_metadata='{"sender":"Old"}',
        )
        db_session.add(file_record)
        db_session.commit()
        item = DocumentReviewItem(file_id=file_record.id, reason="Low confidence", confidence_score=30)
        db_session.add(item)
        db_session.commit()

        response = client.post(
            f"/api/review-queue/{item.id}/resolve", json={"metadata": {"sender": "Correct"}, "note": "Checked"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "resolved"
        db_session.refresh(file_record)
        assert "Correct" in file_record.ai_metadata
        assert client.post(f"/api/review-queue/{item.id}/resolve", json={}).status_code == 409
