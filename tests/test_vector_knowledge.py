"""Tests for chunk-level vector indexing and authorized retrieval."""

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
import requests
from starlette.requests import Request

from app.models import FileRecord


def _file(file_id: int = 7, owner_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=file_id,
        owner_id=owner_id,
        filehash="file-hash",
        original_filename="project-plan.pdf",
        document_title="Project plan",
        mime_type="application/pdf",
        created_at=None,
        ocr_text="alpha beta gamma delta epsilon zeta eta theta",
    )


def test_chunk_fallback_preserves_overlap():
    from app.utils.vector_index import chunk_text

    text = "0123456789" * 5
    with patch("app.utils.vector_index._token_chunks", side_effect=RuntimeError("no tokenizer")):
        chunks = chunk_text(text, size=5, overlap=2)

    assert len(chunks) == 4
    assert chunks[0].text[-8:] == chunks[1].text[:8]
    assert chunks[0].token_end == 5
    assert chunks[1].token_start == 3


def test_index_replaces_document_after_embeddings_are_ready():
    record = _file()
    vectors = [[1.0, 0.0], [0.0, 1.0]]
    with (
        patch("app.utils.vector_index.chunk_text") as chunker,
        patch("app.utils.vector_index.generate_embeddings", return_value=vectors),
        patch("app.utils.vector_index.QdrantVectorIndex.ensure_collection") as ensure,
        patch("app.utils.vector_index.QdrantVectorIndex._request") as request,
    ):
        from app.utils.vector_index import QdrantVectorIndex, TextChunk

        chunker.return_value = [TextChunk(0, "first", 0, 5), TextChunk(1, "second", 4, 9)]
        assert QdrantVectorIndex().index_document(record) == 2

    ensure.assert_called_once_with(2)
    assert request.call_args_list[0].args[0:2] == (
        "PUT",
        "/collections/docuelevate_documents/points?wait=true",
    )
    upsert = request.call_args_list[0].args[2]
    assert [point["payload"]["text"] for point in upsert["points"]] == ["first", "second"]
    assert all(point["payload"]["document_id"] == 7 for point in upsert["points"])
    index_version = upsert["points"][0]["payload"]["index_version"]
    cleanup = request.call_args_list[1].args[2]["filter"]
    assert cleanup["must_not"] == [{"key": "index_version", "match": {"value": index_version}}]


def test_index_batches_large_embedding_requests_without_reordering_chunks():
    from app.utils.vector_index import QdrantVectorIndex, TextChunk

    record = _file()
    chunks = [
        TextChunk(0, "first", 0, 600),
        TextChunk(1, "second", 520, 1120),
        TextChunk(2, "third", 1040, 1640),
    ]
    with (
        patch("app.utils.vector_index.chunk_text", return_value=chunks),
        patch(
            "app.utils.vector_index.generate_embeddings",
            side_effect=[[[1.0, 0.0], [2.0, 0.0]], [[3.0, 0.0]]],
        ) as embed,
        patch("app.utils.vector_index.settings.vector_embedding_batch_tokens", 1200),
        patch("app.utils.vector_index.QdrantVectorIndex.ensure_collection"),
        patch("app.utils.vector_index.QdrantVectorIndex._request") as request,
    ):
        assert QdrantVectorIndex().index_document(record) == 3

    assert embed.call_args_list == [call(["first", "second"]), call(["third"])]
    points = request.call_args_list[0].args[2]["points"]
    assert [point["vector"] for point in points] == [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]


def test_index_batches_qdrant_upserts_without_reordering_points():
    from app.utils.vector_index import QdrantVectorIndex, TextChunk

    chunks = [
        TextChunk(0, "first", 0, 5),
        TextChunk(1, "second", 5, 10),
        TextChunk(2, "third", 10, 15),
    ]
    with (
        patch("app.utils.vector_index.chunk_text", return_value=chunks),
        patch(
            "app.utils.vector_index.generate_embeddings",
            return_value=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
        ),
        patch("app.utils.vector_index.settings.vector_upsert_batch_size", 2),
        patch("app.utils.vector_index.QdrantVectorIndex.ensure_collection"),
        patch("app.utils.vector_index.QdrantVectorIndex._request") as request,
    ):
        assert QdrantVectorIndex().index_document(_file()) == 3

    assert [call.args[0] for call in request.call_args_list] == ["PUT", "PUT", "POST"]
    assert [
        point["payload"]["text"]
        for upsert_call in request.call_args_list[:2]
        for point in upsert_call.args[2]["points"]
    ] == ["first", "second", "third"]


def test_index_keeps_old_points_when_a_later_qdrant_upsert_fails():
    from app.utils.vector_index import QdrantVectorIndex, TextChunk

    chunks = [
        TextChunk(0, "first", 0, 5),
        TextChunk(1, "second", 5, 10),
        TextChunk(2, "third", 10, 15),
    ]
    with (
        patch("app.utils.vector_index.chunk_text", return_value=chunks),
        patch(
            "app.utils.vector_index.generate_embeddings",
            return_value=[[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
        ),
        patch("app.utils.vector_index.settings.vector_upsert_batch_size", 2),
        patch("app.utils.vector_index.QdrantVectorIndex.ensure_collection"),
        patch(
            "app.utils.vector_index.QdrantVectorIndex._request",
            side_effect=[SimpleNamespace(), RuntimeError("qdrant unavailable")],
        ) as request,
    ):
        with pytest.raises(RuntimeError, match="qdrant unavailable"):
            QdrantVectorIndex().index_document(_file())

    assert [call.args[0] for call in request.call_args_list] == ["PUT", "PUT"]


def test_index_keeps_old_points_when_a_later_embedding_batch_fails():
    from app.utils.vector_index import QdrantVectorIndex, TextChunk

    chunks = [TextChunk(0, "first", 0, 600), TextChunk(1, "second", 600, 1200)]
    with (
        patch("app.utils.vector_index.chunk_text", return_value=chunks),
        patch(
            "app.utils.vector_index.generate_embeddings",
            side_effect=[[[1.0, 0.0]], RuntimeError("provider unavailable")],
        ),
        patch("app.utils.vector_index.settings.vector_embedding_batch_tokens", 600),
        patch("app.utils.vector_index.QdrantVectorIndex._request") as request,
    ):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            QdrantVectorIndex().index_document(_file())

    request.assert_not_called()


def test_index_skips_empty_text_and_rejects_incomplete_embedding_batches():
    from app.utils.vector_index import QdrantVectorIndex, TextChunk, VectorIndexError

    empty = _file()
    empty.ocr_text = "  "
    assert QdrantVectorIndex().index_document(empty) == 0

    with (
        patch(
            "app.utils.vector_index.chunk_text",
            return_value=[TextChunk(0, "first", 0, 5), TextChunk(1, "second", 4, 9)],
        ),
        patch("app.utils.vector_index.generate_embeddings", return_value=[[1.0, 0.0]]),
    ):
        with pytest.raises(VectorIndexError, match="unexpected number"):
            QdrantVectorIndex().index_document(_file())


def test_qdrant_request_wraps_transport_and_http_errors():
    from app.utils.vector_index import QdrantVectorIndex, VectorIndexError

    index = QdrantVectorIndex()
    response = SimpleNamespace(status_code=201, text="", json=lambda: {})
    with patch("app.utils.vector_index.requests.request", return_value=response) as request:
        assert index._request("PUT", "/collections/test", {"value": 1}, expected=(201,)) is response
    request.assert_called_once_with(
        "PUT",
        f"{index.base_url}/collections/test",
        headers=index.headers,
        json={"value": 1},
        timeout=index.timeout,
    )

    with patch(
        "app.utils.vector_index.requests.request",
        side_effect=requests.ConnectionError("offline"),
    ):
        with pytest.raises(VectorIndexError, match="request failed"):
            index._request("GET", "/collections/test")

    failure = SimpleNamespace(status_code=503, text="unavailable", json=lambda: {})
    with patch("app.utils.vector_index.requests.request", return_value=failure):
        with pytest.raises(VectorIndexError, match="returned 503"):
            index._request("GET", "/collections/test")


def test_qdrant_collection_creation_and_dimension_guard():
    from app.utils.vector_index import QdrantVectorIndex, VectorIndexError

    missing = SimpleNamespace(status_code=404)
    with patch.object(
        QdrantVectorIndex, "_request", side_effect=[missing, SimpleNamespace(status_code=201)]
    ) as request:
        QdrantVectorIndex().ensure_collection(1536)
    assert request.call_args_list == [
        call("GET", "/collections/docuelevate_documents", expected=(200, 404)),
        call(
            "PUT",
            "/collections/docuelevate_documents",
            {"vectors": {"size": 1536, "distance": "Cosine"}},
            expected=(200, 201),
        ),
    ]

    existing = SimpleNamespace(
        status_code=200,
        json=lambda: {"result": {"config": {"params": {"vectors": {"size": 768}}}}},
    )
    with patch.object(QdrantVectorIndex, "_request", return_value=existing):
        with pytest.raises(VectorIndexError, match="uses 768 dimensions"):
            QdrantVectorIndex().ensure_collection(1536)


def test_qdrant_search_uses_legacy_fallback_and_normalizes_results():
    from app.utils.vector_index import QdrantVectorIndex

    missing = SimpleNamespace(status_code=404, json=lambda: {})
    legacy = SimpleNamespace(
        status_code=200,
        json=lambda: {"result": {"points": [{"id": "point-1", "score": 0.9}]}},
    )
    with (
        patch("app.utils.vector_index.generate_embeddings", return_value=[[0.1, 0.2]]),
        patch.object(QdrantVectorIndex, "_request", side_effect=[missing, legacy]) as request,
    ):
        result = QdrantVectorIndex().search("query", limit=3, score_threshold=0.4)

    assert result == [{"id": "point-1", "score": 0.9}]
    assert request.call_args_list[0].args[2]["query"] == [0.1, 0.2]
    assert request.call_args_list[0].args[2]["score_threshold"] == 0.4
    assert request.call_args_list[1].args[2]["vector"] == [0.1, 0.2]
    assert "query" not in request.call_args_list[1].args[2]


def test_qdrant_status_handles_missing_and_existing_collection():
    from app.utils.vector_index import QdrantVectorIndex

    missing = SimpleNamespace(status_code=404)
    with patch.object(QdrantVectorIndex, "_request", return_value=missing):
        assert QdrantVectorIndex().status() == {
            "available": True,
            "collection_exists": False,
            "points_count": 0,
        }

    existing = SimpleNamespace(
        status_code=200,
        json=lambda: {"result": {"points_count": 12, "status": "green"}},
    )
    with patch.object(QdrantVectorIndex, "_request", return_value=existing):
        assert QdrantVectorIndex().status() == {
            "available": True,
            "collection_exists": True,
            "points_count": 12,
            "status": "green",
        }


def test_owner_filter_removes_unauthorized_vector_hits(db_session):
    own = FileRecord(
        id=1,
        owner_id="alice@example.com",
        filehash="a",
        original_filename="own.pdf",
        local_filename="/tmp/own.pdf",
        file_size=1,
        mime_type="application/pdf",
    )
    other = FileRecord(
        id=2,
        owner_id="bob@example.com",
        filehash="b",
        original_filename="other.pdf",
        local_filename="/tmp/other.pdf",
        file_size=1,
        mime_type="application/pdf",
    )
    db_session.add_all([own, other])
    db_session.commit()
    request = Request({"type": "http", "headers": []})
    request.scope["session"] = {"user": {"email": "alice@example.com"}}

    with patch("app.utils.user_scope.settings.multi_user_enabled", True):
        from app.api.knowledge import _accessible_records

        accessible = _accessible_records(db_session, request, [1, 2])

    assert list(accessible) == [1]


def test_search_returns_cited_authoritative_document(client, db_session):
    record = FileRecord(
        id=3,
        owner_id=None,
        filehash="c",
        original_filename="calendar.pdf",
        document_title="Calendar constraints",
        local_filename="/tmp/calendar.pdf",
        file_size=1,
        mime_type="application/pdf",
        ocr_text="The appointment is Tuesday at 10.",
    )
    db_session.add(record)
    db_session.commit()
    hits = [
        {
            "score": 0.91,
            "payload": {
                "document_id": 3,
                "text": "The appointment is Tuesday at 10.",
                "chunk_index": 0,
                "chunk_count": 1,
            },
        }
    ]
    with (
        patch("app.api.knowledge.settings.vector_index_enabled", True),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=hits),
    ):
        response = client.post("/api/knowledge/search", json={"query": "When is the appointment?"})

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["document_id"] == 3
    assert result["title"] == "Calendar constraints"
    assert result["source_url"] == "/files/3"


def test_search_reranks_exact_metadata_and_deduplicates_documents(client, db_session):
    exact = FileRecord(
        id=10,
        owner_id=None,
        filehash="exact",
        original_filename="Posteingang_0012.pdf",
        document_title="Deutsche Bank Kontoauszug Dezember 2010",
        local_filename="/tmp/exact.pdf",
        file_size=1,
        mime_type="application/pdf",
        ocr_text="Account details",
    )
    similar = FileRecord(
        id=11,
        owner_id=None,
        filehash="similar",
        original_filename="statement.pdf",
        document_title="Kontoauszug Deutsche Bank Christian Louis",
        local_filename="/tmp/similar.pdf",
        file_size=1,
        mime_type="application/pdf",
        ocr_text="Similar account details",
    )
    other = FileRecord(
        id=12,
        owner_id=None,
        filehash="other",
        original_filename="other.pdf",
        document_title="Kontoauszug einer anderen Bank",
        local_filename="/tmp/other.pdf",
        file_size=1,
        mime_type="application/pdf",
        ocr_text="Other account details",
    )
    db_session.add_all([exact, similar, other])
    db_session.commit()
    hits = [
        {"score": 0.74, "payload": {"document_id": 11, "text": "similar first", "chunk_index": 0}},
        {"score": 0.73, "payload": {"document_id": 11, "text": "similar second", "chunk_index": 1}},
        {"score": 0.66, "payload": {"document_id": 10, "text": "exact passage", "chunk_index": 0}},
        {"score": 0.65, "payload": {"document_id": 12, "text": "other passage", "chunk_index": 0}},
    ]
    with (
        patch("app.api.knowledge.settings.vector_index_enabled", True),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=hits) as search,
    ):
        response = client.post(
            "/api/knowledge/search",
            json={"query": "Deutsche Bank Kontoauszug Dezember 2010", "limit": 2},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [result["document_id"] for result in results] == [10, 11]
    assert results[0]["semantic_score"] == pytest.approx(0.66)
    assert results[0]["score"] > results[0]["semantic_score"]
    search.assert_called_once_with(
        "Deutsche Bank Kontoauszug Dezember 2010",
        limit=50,
        score_threshold=0.25,
    )
