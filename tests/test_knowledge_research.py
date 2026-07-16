"""Deterministic controls for exhaustive corpus research."""

from datetime import datetime, timedelta, timezone
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.knowledge import _research_cache_is_complete, _research_job_payload
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
    _plan_research,
    _should_stop_mapping,
    _synthesize,
    cleanup_knowledge_research_jobs,
    run_knowledge_research,
)

pytestmark = pytest.mark.unit


def test_research_retries_transient_database_disconnect():
    job = SimpleNamespace(
        state="queued",
        error=None,
        question="Wie oft war ich in London?",
        history_json="[]",
        accessible_file_ids_json="[]",
    )
    session = MagicMock(spec=Session)
    session.query.return_value.filter.return_value.first.return_value = job
    session_context = MagicMock()
    session_context.__enter__.return_value = session
    disconnect = OperationalError("UPDATE knowledge_research_jobs", {}, Exception("unexpected eof"))
    session.commit.side_effect = disconnect

    with (
        patch("app.tasks.knowledge_research.SessionLocal", return_value=session_context),
        patch.object(run_knowledge_research, "retry", side_effect=RuntimeError("retry scheduled")) as retry,
        pytest.raises(RuntimeError, match="retry scheduled"),
    ):
        run_knowledge_research.run("job-1")

    session.invalidate.assert_called_once_with()
    assert retry.call_args.kwargs["countdown"] == 1
    assert retry.call_args.kwargs["max_retries"] == 2


def test_candidate_retrieval_pages_qualified_matches_per_scope():
    calls = []

    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        calls.append((query, page, per_page))
        assert file_ids == [1, 2, 3]
        assert matching_strategy == (None if query == "" else "all")
        if query == "":
            return {"results": [], "total": 3, "pages": 3}
        if page == 1:
            return {
                "results": [
                    {"file_id": 1, "ranking_score": 0.9},
                    {"file_id": 2, "ranking_score": 0.8},
                ],
                "total": 3,
                "pages": 2,
            }
        return {"results": [{"file_id": 3, "ranking_score": 0.7}], "total": 3, "pages": 2}

    with (
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=[]),
    ):
        candidates, indexed, retrieval_truncated = _candidate_ids([1, 2, 3], "Wie oft war ich in London per Flugzeug?")

    assert candidates == [1, 2, 3]
    assert indexed == 3
    assert retrieval_truncated is False
    assert [page for query, page, _per_page in calls if query] == [1, 2]


def test_research_planner_keeps_exact_entity_and_returns_small_plan():
    calls = []
    provider = SimpleNamespace(
        chat_completion=lambda **kwargs: (
            calls.append(kwargs)
            or (
                '{"hard_entities":["Motel One"],'
                '"lexical_queries":["Motel One Buchungen Aufenthalte Nächte",'
                '"\\"Motel One\\" Buchungen Belege"],'
                '"semantic_query":"Motel One booking confirmation hotel stay",'
                '"aggregation":"count stays and nights","evidence_types":["hotel_booking"],'
                '"exclude_terms":["advertising"]}'
            )
        ),
    )

    with patch("app.utils.ai_provider.get_ai_provider", return_value=provider):
        plan = _plan_research(
            "Wie oft war ich auf Basis der Buchungsdaten in einem Motel One Hotel?",
            "gpt-5-nano",
        )

    assert plan["lexical_queries"][0] == '"Motel One"'
    assert plan["lexical_queries"][1:] == [
        "Motel One Buchungen Aufenthalte Nächte",
        '"Motel One" Buchungen Belege',
    ]
    assert plan["aggregation"] == "count stays and nights"
    assert len(plan["lexical_queries"]) == 3
    assert calls[0]["reasoning_effort"] == "minimal"
    assert calls[0]["max_completion_tokens"] == 300


def test_research_planner_omits_gpt5_only_kwargs_for_other_models():
    calls = []
    provider = SimpleNamespace(
        chat_completion=lambda **kwargs: (
            calls.append(kwargs) or '{"lexical_queries":["invoice"],"semantic_query":"invoice"}'
        )
    )

    with patch("app.utils.ai_provider.get_ai_provider", return_value=provider):
        _plan_research("Find invoices", "gpt-4o-mini")

    assert "reasoning_effort" not in calls[0]
    assert "max_completion_tokens" not in calls[0]


def test_candidate_retrieval_uses_adaptive_relevance_threshold():
    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        return {
            "results": [{"file_id": file_id, "ranking_score": file_id / 10} for file_id in file_ids],
            "total": len(file_ids),
            "pages": 1,
        }

    with (
        patch("app.tasks.knowledge_research.settings.rag_research_lexical_min_score", 0.15),
        patch("app.tasks.knowledge_research.settings.rag_research_semantic_min_score", 0.35),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=[]),
    ):
        candidates, indexed, retrieval_truncated = _candidate_ids(
            [1, 2, 3],
            "Motel One",
            plan={"lexical_queries": ['"Motel One"'], "semantic_query": "Motel One stay"},
        )

    assert candidates == [3, 2]
    assert indexed == 3
    assert retrieval_truncated is False


def test_candidate_retrieval_prioritizes_documents_matching_qualified_queries():
    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        if query == '"Motel One"':
            return {
                "results": [
                    {"file_id": 1, "ranking_score": 0.99},  # broad mention only
                    {"file_id": 2, "ranking_score": 0.80},
                ],
                "total": 2,
                "pages": 1,
            }
        return {
            "results": [{"file_id": 2, "ranking_score": 0.75}],
            "total": 1,
            "pages": 1,
        }

    with (
        patch("app.tasks.knowledge_research.settings.vector_index_enabled", False),
        patch("app.tasks.knowledge_research.settings.rag_research_lexical_min_score", 0.65),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
    ):
        candidates, _indexed, _truncated = _candidate_ids(
            [1, 2],
            "Motel One",
            plan={
                "lexical_queries": ['"Motel One"', '"Motel One" Buchung Aufenthalt'],
                "semantic_query": "Motel One stay",
            },
        )

    assert candidates == [2, 1]


def test_candidate_retrieval_runs_qualified_query_after_broad_query_saturates():
    queries = []

    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        queries.append((query, page))
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        if query == '"Motel One"':
            return {
                "results": [
                    {"file_id": 1, "ranking_score": 0.99},
                    {"file_id": 2, "ranking_score": 0.98},
                ],
                "total": 20,
                "pages": 10,
            }
        return {
            "results": [{"file_id": 2, "ranking_score": 0.99}],
            "total": 1,
            "pages": 1,
        }

    with (
        patch("app.tasks.knowledge_research._RETRIEVAL_SAFETY_LIMIT", 2),
        patch("app.tasks.knowledge_research.settings.vector_index_enabled", False),
        patch("app.tasks.knowledge_research.settings.rag_research_lexical_min_score", 0.65),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
    ):
        candidates, _indexed, truncated = _candidate_ids(
            [1, 2],
            "Motel One",
            plan={
                "lexical_queries": ['"Motel One"', '"Motel One" Buchung Aufenthalt'],
                "semantic_query": "Motel One stay",
            },
        )

    assert ('"Motel One" Buchung Aufenthalt', 1) in queries
    assert candidates == [2, 1]
    assert truncated is True


def test_candidate_retrieval_uses_relative_semantic_threshold():
    vector_hits = [
        {"score": 0.90, "payload": {"document_id": 1}},
        {"score": 0.80, "payload": {"document_id": 2}},
        {"score": 0.60, "payload": {"document_id": 3}},
    ]

    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        return {"results": [], "total": 0, "pages": 1}

    with (
        patch("app.tasks.knowledge_research.settings.vector_index_enabled", True),
        patch("app.tasks.knowledge_research.settings.rag_research_semantic_min_score", 0.35),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=vector_hits) as vector_search,
    ):
        candidates, _indexed, retrieval_truncated = _candidate_ids(
            [1, 2, 3],
            "Motel One",
            plan={"lexical_queries": [], "semantic_query": "Motel One stay"},
        )

    assert candidates == [1, 2]
    assert retrieval_truncated is False
    vector_search.assert_called_once_with(
        "Motel One stay",
        limit=250,
        score_threshold=0.35,
        document_ids=[1, 2, 3],
    )


def test_candidate_retrieval_reports_technical_safety_truncation():
    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        return {
            "results": [{"file_id": file_id, "ranking_score": 0.9} for file_id in file_ids[page - 1 : page]],
            "total": len(file_ids),
            "pages": len(file_ids),
        }

    with (
        patch("app.tasks.knowledge_research._RETRIEVAL_SAFETY_LIMIT", 2),
        patch("app.tasks.knowledge_research.settings.vector_index_enabled", False),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
    ):
        candidates, indexed, retrieval_truncated = _candidate_ids(
            [1, 2, 3, 4],
            "Motel One",
            plan={"lexical_queries": ['"Motel One"'], "semantic_query": "Motel One stay"},
        )

    assert candidates == [1, 2]
    assert indexed == 4
    assert retrieval_truncated is True


def test_research_target_is_not_a_hard_timeout_without_evidence():
    assert _should_stop_mapping(48, 60, has_evidence=True) is True
    assert _should_stop_mapping(60, 60, has_evidence=False) is False


def test_terminal_research_elapsed_time_does_not_keep_growing():
    created_at = datetime(2026, 7, 16, 8, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id="job-1",
        state="completed",
        total_documents=12,
        processed_documents=12,
        cancel_requested=False,
        error=None,
        result_json=None,
        created_at=created_at,
        updated_at=created_at + timedelta(seconds=42),
    )

    assert _research_job_payload(job)["elapsed_seconds"] == 42


def test_truncated_research_result_is_not_reused_as_complete():
    job = SimpleNamespace(result_json='{"coverage":{"index_complete":true,"truncated":true}}')

    assert _research_cache_is_complete(job) is False


def test_candidate_retrieval_splits_scopes_at_search_result_cap():
    scopes = []

    def search(query, *, file_ids, page, per_page, matching_strategy=None):
        scopes.append((query, file_ids, page, per_page))
        if query == "":
            return {"results": [], "total": len(file_ids), "pages": 1}
        return {
            "results": [{"file_id": file_id, "ranking_score": 0.9} for file_id in file_ids],
            "total": len(file_ids),
            "pages": 1,
        }

    with (
        patch("app.tasks.knowledge_research._SCOPE_BATCH", 2),
        patch("app.utils.meilisearch_client.search_documents", side_effect=search),
        patch("app.utils.vector_index.QdrantVectorIndex.search", return_value=[]),
    ):
        candidates, indexed, retrieval_truncated = _candidate_ids(
            [1, 2, 3, 4, 5],
            "Wie oft war ich in London per Flugzeug?",
        )

    assert candidates == [1, 2, 3, 4, 5]
    assert indexed == 5
    assert retrieval_truncated is False
    assert sorted(
        [file_ids for query, file_ids, _page, _per_page in scopes if query == ""], key=lambda ids: ids[0]
    ) == [
        [1, 2],
        [3, 4],
        [5],
    ]


def test_candidate_retrieval_searches_authorized_scopes_concurrently():
    """Large tenant scopes must not add one full search round-trip each."""
    barrier = Barrier(2)

    def search_scope(scope, _queries):
        barrier.wait(timeout=1)
        return len(scope), {scope[0]: 0.9}, False

    with (
        patch("app.tasks.knowledge_research._SCOPE_BATCH", 2),
        patch("app.tasks.knowledge_research._search_lexical_scope", side_effect=search_scope),
        patch("app.tasks.knowledge_research.settings.vector_index_enabled", False),
    ):
        candidates, indexed, retrieval_truncated = _candidate_ids(
            [1, 2, 3, 4],
            "Motel One",
            plan={"lexical_queries": ['"Motel One"'], "semantic_query": "Motel One stay"},
        )

    assert candidates == [1, 3]
    assert indexed == 4
    assert retrieval_truncated is False


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


def test_empty_research_answer_separates_complete_index_from_bounded_analysis():
    answer = _no_evidence_answer(
        "Wie oft war ich im Motel One?",
        index_complete=True,
        analysis_truncated=True,
    )

    assert "Index ist vollständig" in answer
    assert "begrenzte Textausschnitte" in answer
    assert "Index ist noch unvollständig" not in answer


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


def test_first_person_filter_keeps_aliases_and_rejects_other_people():
    evidence = [
        {"evidence_type": "hba1c_measurement", "subject": "Christian Louis", "claim": "6.0%"},
        {"evidence_type": "hba1c_measurement", "subject": "Louis, Christian", "claim": "6.2%"},
        {"evidence_type": "hba1c_measurement", "subject": "Krakau, Julia", "claim": "5.3%"},
        {"evidence_type": "hba1c_measurement", "subject": "Renate Louis", "claim": "5.8%"},
        {"evidence_type": "hba1c_measurement", "subject": "", "claim": "6.4%"},
    ]

    filtered = _filter_evidence_for_question(
        "Wie hat sich mein HbA1c verändert?",
        evidence,
        subject_hint="Christian Krakau-Louis",
    )

    assert filtered == [evidence[0], evidence[1], evidence[4]]


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
    assert "COMPLETE SET OF ALLOWED CITATION MARKERS IS: [1]" in prompts[0]


def test_synthesis_regenerates_answers_with_invented_citation_markers():
    record = SimpleNamespace(document_title="Ticket", original_filename="ticket.pdf")
    responses = iter(["Five trips plus another trip [0].", "Five proven trips [1]."])
    provider = SimpleNamespace(chat_completion=lambda **_kwargs: next(responses))

    with patch("app.utils.ai_provider.get_ai_provider", return_value=provider):
        result = _synthesize(
            "How many trips?",
            "How many trips?",
            [{"event_key": "trip-1", "document_ids": [7]}],
            {7: record},
            "gpt-5-nano",
        )

    assert result["answer"] == "Five proven trips [1]."
    assert [source["document_id"] for source in result["sources"]] == [7]


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
