"""Semantic and hybrid ranking over cached document embeddings."""

import json
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import FileRecord
from app.utils.similarity import cosine_similarity, generate_embedding
from app.utils.user_scope import apply_owner_filter


def semantic_candidates(
    db: Session,
    request: Request,
    query: str,
    *,
    mime_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Rank accessible documents using their cached embeddings."""
    query_vector = generate_embedding(query)
    rows = db.query(FileRecord).filter(FileRecord.embedding.isnot(None), FileRecord.embedding != "")
    rows = apply_owner_filter(rows, request)
    if mime_type:
        rows = rows.filter(FileRecord.mime_type == mime_type)
    ranked: list[dict[str, Any]] = []
    for file_record in rows.limit(limit).all():
        try:
            score = cosine_similarity(query_vector, json.loads(file_record.embedding))
        except (TypeError, json.JSONDecodeError):
            continue
        metadata = json.loads(file_record.ai_metadata or "{}")
        ranked.append(
            {
                "file_id": file_record.id,
                "original_filename": file_record.original_filename,
                "document_title": file_record.document_title,
                "document_type": metadata.get("document_type"),
                "tags": metadata.get("tags", []),
                "semantic_score": round(score, 6),
                "ranking_explanation": {
                    "source": "embedding",
                    "summary": "Cosine similarity between the query and cached document embedding.",
                },
            }
        )
    return sorted(ranked, key=lambda item: item["semantic_score"], reverse=True)


def hybrid_rank(keyword_results: list[dict[str, Any]], semantic_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine keyword and semantic ranks using weighted reciprocal rank fusion."""
    combined: dict[int, dict[str, Any]] = {}
    for source, weight, results in (("keyword", 0.55, keyword_results), ("semantic", 0.45, semantic_results)):
        for rank, item in enumerate(results, start=1):
            file_id = int(item["file_id"])
            entry = combined.setdefault(file_id, dict(item))
            entry["hybrid_score"] = entry.get("hybrid_score", 0.0) + weight / (60 + rank)
            entry.setdefault("ranking_components", {})[source] = {
                "rank": rank,
                "raw_score": item.get("ranking_score", item.get("semantic_score")),
            }
            for key, value in item.items():
                entry.setdefault(key, value)
    ranked = sorted(combined.values(), key=lambda item: item["hybrid_score"], reverse=True)
    for item in ranked:
        item["hybrid_score"] = round(item["hybrid_score"], 8)
        item["ranking_explanation"] = {
            "source": "hybrid",
            "summary": "Weighted reciprocal-rank fusion: 55% keyword and 45% semantic.",
            "components": item["ranking_components"],
        }
    return ranked
