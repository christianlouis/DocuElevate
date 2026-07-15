"""Deterministic controls for exhaustive corpus research."""

from types import SimpleNamespace
from unittest.mock import patch

from app.tasks.knowledge_research import (
    _candidate_ids,
    _contextual_research_question,
    _deduplicate_evidence,
    _no_evidence_answer,
)


def test_candidate_retrieval_pages_every_authorized_match():
    def search(query, *, file_ids, page, per_page):
        assert file_ids == [1, 2, 3]
        if query == "":
            return {"results": [], "total": 3, "pages": 3}
        if page == 1:
            return {"results": [{"file_id": 1}, {"file_id": 2}], "total": 3, "pages": 2}
        return {"results": [{"file_id": 3}], "total": 3, "pages": 2}

    with (
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=[]),
    ):
        candidates, indexed = _candidate_ids([1, 2, 3], "Wie oft war ich in London per Flugzeug?")

    assert candidates == [1, 2, 3]
    assert indexed == 3


def test_deduplication_merges_transport_legs_and_duplicate_documents():
    evidence = [
        {"document_id": 1, "evidence_type": "flight_trip", "event_key": "BA-ABC123", "claim": "Outbound"},
        {"document_id": 2, "evidence_type": "flight_trip", "event_key": "ba abc123", "claim": "Return itinerary"},
        {"document_id": 3, "evidence_type": "flight_trip", "event_key": "LH-XYZ", "claim": "Another trip"},
    ]

    reduced = _deduplicate_evidence(evidence)

    assert len(reduced) == 2
    first = next(item for item in reduced if item["event_key"] == "ba abc123")
    assert first["document_ids"] == [1, 2]


def test_map_batch_rejects_evidence_for_documents_outside_batch():
    from app.tasks.knowledge_research import _map_batch

    record = SimpleNamespace(id=7, document_title="Lab", original_filename="lab.pdf", ocr_text="HbA1c 5.8 %")
    provider = SimpleNamespace(
        chat_completion=lambda **_kwargs: (
            '{"evidence":[{"document_id":7,"event_key":"lab-1"},{"document_id":99,"event_key":"leak"}]}'
        )
    )
    with patch("app.utils.ai_provider.get_ai_provider", return_value=provider):
        result = _map_batch("HbA1c trend", [record], "gpt-5-nano")

    assert [item["document_id"] for item in result] == [7]


def test_follow_up_research_includes_bounded_conversation_context():
    history = '[{"role":"user","content":"How many London trips?"},{"role":"assistant","content":"Two."}]'

    contextual = _contextual_research_question("How many of those were in 2024?", history)

    assert "How many London trips?" in contextual
    assert "How many of those were in 2024?" in contextual
    from app.api.knowledge import _research_keyword_query

    assert _research_keyword_query(contextual) == "london trips 2024"


def test_empty_research_answer_is_localized_and_qualifies_incomplete_index():
    answer = _no_evidence_answer("Wie oft war ich in London?", index_complete=False)

    assert "noch unvollständig" in answer
    assert "nicht abschließend" in answer
    assert _no_evidence_answer("How many London trips?", index_complete=True).startswith("I could not")
