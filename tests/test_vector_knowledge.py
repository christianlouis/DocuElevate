"""Tests for chunk-level vector indexing and authorized retrieval."""

from types import SimpleNamespace
from unittest.mock import patch

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
        "POST",
        "/collections/docuelevate_documents/points/delete?wait=true",
    )
    upsert = request.call_args_list[1].args[2]
    assert [point["payload"]["text"] for point in upsert["points"]] == ["first", "second"]
    assert all(point["payload"]["document_id"] == 7 for point in upsert["points"])


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
