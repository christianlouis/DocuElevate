"""Tests for hybrid search ranking."""

from app.utils.hybrid_search import hybrid_rank


def test_hybrid_rank_combines_keyword_and_semantic_signals():
    keyword = [{"file_id": 1, "ranking_score": 0.9}, {"file_id": 2, "ranking_score": 0.8}]
    semantic = [{"file_id": 2, "semantic_score": 0.95}, {"file_id": 3, "semantic_score": 0.7}]

    ranked = hybrid_rank(keyword, semantic)

    assert ranked[0]["file_id"] == 2
    assert ranked[0]["ranking_explanation"]["source"] == "hybrid"
    assert set(ranked[0]["ranking_components"]) == {"keyword", "semantic"}
