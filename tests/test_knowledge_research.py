"""Deterministic controls for exhaustive corpus research."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import KnowledgeResearchJob
from app.tasks.knowledge_research import (
    _bounded_synthesis_evidence,
    _candidate_ids,
    _chat_completion_with_retry,
    _contextual_research_question,
    _deduplicate_evidence,
    _excerpt,
    _filter_evidence_for_question,
    _no_evidence_answer,
    _numeric,
    _synthesize,
    cleanup_knowledge_research_jobs,
)

pytestmark = pytest.mark.unit


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
        result, truncated = _map_batch("HbA1c trend", [record], "gpt-5-nano")

    assert [item["document_id"] for item in result] == [7]
    assert truncated is False


def test_follow_up_research_includes_bounded_conversation_context():
    history = '[{"role":"user","content":"How many London trips?"},{"role":"assistant","content":"Two."}]'

    contextual = _contextual_research_question("How many of those were in 2024?", history)

    assert "How many London trips?" in contextual
    assert "How many of those were in 2024?" in contextual
    from app.api.knowledge import _research_keyword_query

    assert _research_keyword_query(contextual) == "london trips 2024"


def test_research_context_includes_bounded_authenticated_subject_hint():
    payload = '{"history":[],"subject_hint":"  Christian   Krakau-Louis  "}'

    contextual = _contextual_research_question("Wie oft war ich in London?", payload)

    assert "AUTHENTICATED USER DISPLAY NAME" in contextual
    assert "Christian Krakau-Louis" in contextual
    assert "CURRENT QUESTION" in contextual


def test_retrieval_context_excludes_authenticated_subject_hint():
    from app.api.knowledge import _research_keyword_query

    payload = '{"history":[],"subject_hint":"Christian Krakau-Louis"}'

    contextual = _contextual_research_question(
        "Wie oft war ich in London per Flugzeug?", payload, include_subject_hint=False
    )

    assert "AUTHENTICATED USER DISPLAY NAME" not in contextual
    assert _research_keyword_query(contextual) == "london flugzeug"


def test_empty_research_answer_is_localized_and_qualifies_incomplete_index():
    answer = _no_evidence_answer("Wie oft war ich in London?", index_complete=False)

    assert "noch unvollständig" in answer
    assert "nicht abschließend" in answer
    assert _no_evidence_answer("How many London trips?", index_complete=True).startswith("I could not")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1,234.56 USD", 1234.56),
        ("1.234,56 EUR", 1234.56),
        ("1234,56", 1234.56),
        ("1 234.56", 1234.56),
        ("1,234", 1234.0),
        (None, None),
    ],
)
def test_numeric_accepts_common_locale_formats(value, expected):
    assert _numeric(value) == expected


def test_deduplication_backfills_structured_fields_from_later_document():
    reduced = _deduplicate_evidence(
        [
            {"document_id": 1, "reference": "order-1", "claim": "Amazon order"},
            {
                "document_id": 2,
                "reference": "order-1",
                "claim": "Amazon order total 1,234.56 USD",
                "amount": "1,234.56",
                "currency": "USD",
                "event_date": "2025-01-02",
            },
        ]
    )

    assert reduced[0]["amount"] == "1,234.56"
    assert reduced[0]["currency"] == "USD"
    assert reduced[0]["event_date"] == "2025-01-02"


def test_occurrence_filter_rejects_promotions_and_schedules_but_keeps_proof():
    evidence = [
        {"evidence_type": "flight_promotion", "claim": "London from 49 EUR"},
        {"evidence_type": "route schedule", "claim": "Daily flights to Heathrow"},
        {"evidence_type": "boarding_pass", "claim": "Flew to London"},
        {"evidence_type": "hotel_booking", "claim": "Stayed at Motel One"},
    ]

    filtered = _filter_evidence_for_question("Wie oft war ich in London?", evidence)

    assert [item["evidence_type"] for item in filtered] == ["boarding_pass", "hotel_booking"]
    assert _filter_evidence_for_question("Wie viele Flüge hatte ich nach London?", evidence) == filtered
    assert _filter_evidence_for_question("Welche Flugpläne habe ich?", evidence) == evidence


def test_hba1c_filter_rejects_reference_ranges_but_keeps_patient_results():
    evidence = [
        {"evidence_type": "lab_reference_range", "numeric_value": "4.8-5.9", "claim": "HbA1c normal range"},
        {"evidence_type": "hba1c_measurement", "numeric_value": "6.4", "claim": "Patient result 6.4%"},
    ]

    assert _filter_evidence_for_question("Wie hat sich mein HbA1c verändert?", evidence) == [evidence[1]]


def test_occurrence_filter_requires_named_entity_in_cited_source():
    evidence = [
        {"document_id": 1, "evidence_type": "hotel_stay", "claim": "Motel One stay"},
        {"document_id": 2, "evidence_type": "hotel_stay", "claim": "Motel One stay"},
    ]
    records = {
        1: SimpleNamespace(document_title="OTTO delivery", original_filename="delivery.pdf", ocr_text="Hermes"),
        2: SimpleNamespace(
            document_title="Motel One invoice",
            original_filename="motel-one.pdf",
            ocr_text="Motel One München-Garching",
        ),
    }

    assert _filter_evidence_for_question("Wie oft war ich im Motel One?", evidence, records) == [evidence[1]]


def test_excerpt_samples_distributed_entity_occurrences_in_long_documents():
    sections = [f"AMAZON purchase {index} amount {index},00 EUR " + ("x" * 180) for index in range(80)]
    sections[10] = "AMZ expensive purchase amount 387,70 EUR " + ("y" * 180)
    text = "".join(sections)

    excerpt = _excerpt(text, "Was war der teuerste Amazon Kauf?")

    assert "387,70 EUR" in excerpt
    assert len(excerpt) <= 6_000


def test_excerpt_does_not_let_frequent_generic_terms_starve_entity_terms():
    generic = ("teuerste boilerplate " + ("x" * 180)) * 80
    text = generic + " AMAZON amount 387,70 EUR " + ("y" * 8_000)

    excerpt = _excerpt(text, "Was war der teuerste Amazon Kauf?")

    assert "AMAZON amount 387,70 EUR" in excerpt


def test_bounded_synthesis_reports_when_it_truncates():
    small, small_truncated = _bounded_synthesis_evidence([{"event_key": "one"}])
    large, large_truncated = _bounded_synthesis_evidence(
        [{"event_key": str(index), "claim": "x" * 2_000} for index in range(100)]
    )

    assert small == [{"event_key": "one"}]
    assert small_truncated is False
    assert len(large) < 100
    assert large_truncated is True


def test_model_call_retries_transient_failures_without_unbounded_loop():
    provider = SimpleNamespace(chat_completion=lambda **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with patch("app.tasks.knowledge_research.time.sleep") as sleep:
        with pytest.raises(TimeoutError):
            _chat_completion_with_retry(provider, messages=[], model="test")

    assert sleep.call_count == 2


def test_synthesis_returns_only_sources_cited_by_model():
    record = SimpleNamespace(document_title="Invoice", original_filename="invoice.pdf")
    prompts = []

    def complete(**kwargs):
        prompts.append(kwargs["messages"][1]["content"])
        return "The maximum was 42 EUR [1]."

    provider = SimpleNamespace(chat_completion=complete)
    with patch("app.utils.ai_provider.get_ai_provider", return_value=provider):
        result = _synthesize(
            "What was the maximum?",
            "What was the maximum?",
            [{"event_key": "order-1", "amount": 42, "document_ids": [7]}],
            {7: record},
            "gpt-5-nano",
        )

    assert result["answer"] == "The maximum was 42 EUR [1]."
    assert result["sources"][0]["document_id"] == 7
    assert result["truncated"] is False
    assert '"document_id"' not in prompts[0]
    assert '"document_ids"' not in prompts[0]
    assert '"citations": "[1]"' in prompts[0]
    assert "candidate count is not an answer" in prompts[0]
    assert "do not combine evidence explicitly belonging" in prompts[0]
    assert "primary hotel total must be labeled stays/Aufenthalte" in prompts[0]
    assert "exclude reference, normal and target ranges" in prompts[0]


def test_cleanup_removes_only_expired_terminal_jobs(db_session):
    old = datetime.now(timezone.utc) - timedelta(days=40)
    jobs = [
        KnowledgeResearchJob(
            id="expired",
            owner_id="owner",
            cache_key="a" * 64,
            question="sensitive",
            accessible_file_ids_json="[]",
            state="completed",
            updated_at=old,
        ),
        KnowledgeResearchJob(
            id="active",
            owner_id="owner",
            cache_key="b" * 64,
            question="still running",
            accessible_file_ids_json="[]",
            state="running",
            updated_at=old,
        ),
    ]
    db_session.add_all(jobs)
    db_session.commit()
    session_factory = lambda: db_session  # noqa: E731
    with (
        patch("app.tasks.knowledge_research.SessionLocal", session_factory),
        patch("app.tasks.knowledge_research.settings.knowledge_research_retention_days", 30),
    ):
        result = cleanup_knowledge_research_jobs.run()

    assert result == {"deleted": 1}
    assert db_session.query(KnowledgeResearchJob).filter_by(id="active").one().state == "running"
