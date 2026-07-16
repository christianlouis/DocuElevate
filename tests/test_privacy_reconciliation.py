"""Privacy changes converge into derived indexes without re-embedding."""

from contextlib import nullcontext
from unittest.mock import patch

import pytest

from app.models import FileRecord


@pytest.mark.unit
def test_qdrant_privacy_update_is_owner_and_document_scoped():
    from app.utils.vector_index import QdrantVectorIndex

    with patch("app.utils.vector_index.QdrantVectorIndex._request") as request:
        request.return_value.status_code = 200
        assert QdrantVectorIndex().set_document_privacy(42, owner_id="alice", is_private=True) is True

    request.assert_called_once_with(
        "POST",
        "/collections/docuelevate_documents/points/payload?wait=true",
        {
            "payload": {"is_private": True},
            "filter": {
                "must": [
                    {"key": "document_id", "match": {"value": 42}},
                    {"key": "owner_id", "match": {"value": "alice"}},
                ]
            },
        },
        expected=(200, 201, 404),
    )


@pytest.mark.unit
def test_reconciliation_updates_search_payloads_without_embeddings(db_session):
    record = FileRecord(
        owner_id="alice",
        filehash="privacy-reconciliation",
        original_filename="private.pdf",
        local_filename="/tmp/private.pdf",
        file_size=10,
        mime_type="application/pdf",
        ocr_text="private source text",
        ai_metadata='{"title": "Private letter"}',
        is_private=True,
    )
    db_session.add(record)
    db_session.commit()

    with (
        patch("app.tasks.reconcile_file_privacy.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.tasks.reconcile_file_privacy.settings.vector_index_enabled", True),
        patch("app.utils.meilisearch_client.index_document", return_value=True) as meili,
        patch("app.utils.vector_index.QdrantVectorIndex.set_document_privacy", return_value=True) as qdrant,
        patch("app.utils.vector_index.generate_embeddings") as embeddings,
    ):
        from app.tasks.reconcile_file_privacy import reconcile_file_privacy

        result = reconcile_file_privacy.run(record.id)

    meili.assert_called_once_with(record, "private source text", {"title": "Private letter"})
    qdrant.assert_called_once_with(record.id, owner_id="alice", is_private=True)
    embeddings.assert_not_called()
    assert result["status"] == "success"
    assert result["is_private"] is True


@pytest.mark.unit
def test_missing_qdrant_collection_is_a_clean_noop():
    from types import SimpleNamespace

    from app.utils.vector_index import QdrantVectorIndex

    with patch(
        "app.utils.vector_index.QdrantVectorIndex._request",
        return_value=SimpleNamespace(status_code=404),
    ):
        assert QdrantVectorIndex().set_document_privacy(42, owner_id="alice", is_private=True) is False
