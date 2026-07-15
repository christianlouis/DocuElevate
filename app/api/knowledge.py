"""Authenticated retrieval API for chunk-level document knowledge."""

import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import FileRecord
from app.utils.user_scope import apply_owner_filter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])
DbSession = Annotated[Session, Depends(get_db)]

_SEARCH_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_METADATA_CANDIDATE_LIMIT = 250
_METADATA_EXCERPT_CHARS = 2_400


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    limit: int = Field(default=8, ge=1, le=50)
    score_threshold: float | None = Field(default=0.25, ge=0.0, le=1.0)


def _require_enabled() -> None:
    if not settings.vector_index_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vector knowledge index is disabled",
        )


def _accessible_records(db: Session, request: Request, document_ids: list[int]) -> dict[int, FileRecord]:
    if not document_ids:
        return {}
    query = db.query(FileRecord).filter(FileRecord.id.in_(document_ids))
    records = apply_owner_filter(query, request).all()
    return {record.id: record for record in records}


def _normalized_search_text(value: str | None) -> str:
    """Return comparable Unicode words without punctuation or filename separators."""
    return " ".join(_SEARCH_TOKEN_RE.findall((value or "").casefold()))


def _search_token_weight(token: str) -> float:
    """Give dates, identifiers, and distinctive long terms more lexical weight."""
    if any(character.isdigit() for character in token):
        return 3.0
    if len(token) >= 7:
        return 2.0
    return 1.0


def _escaped_like_pattern(token: str) -> str:
    """Return a literal SQL LIKE substring pattern for user-provided text."""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _metadata_candidates(db: Session, request: Request, query: str) -> list[FileRecord]:
    """Find owner-scoped exact metadata candidates outside Qdrant's semantic window."""
    normalized_query = _normalized_search_text(query)
    query_tokens = sorted(
        set(normalized_query.split()),
        key=lambda token: (_search_token_weight(token), len(token), token),
        reverse=True,
    )[:12]
    if not query_tokens:
        return []

    # Rank metadata candidates by weighted query-term coverage. Using an OR
    # here deliberately supports natural questions such as "summarize X.pdf";
    # the bounded limit and weighted SQL ordering keep the scan selective.
    weighted_clauses = []
    for token in query_tokens:
        pattern = _escaped_like_pattern(token)
        clause = or_(
            FileRecord.document_title.ilike(pattern, escape="\\"),
            FileRecord.original_filename.ilike(pattern, escape="\\"),
        )
        weighted_clauses.append((clause, _search_token_weight(token)))
    raw_query = query.strip().lower()
    exact_match = or_(
        func.lower(FileRecord.document_title) == raw_query,
        func.lower(FileRecord.original_filename) == raw_query,
    )
    metadata_match = or_(
        exact_match,
        *(clause for clause, _weight in weighted_clauses),
    )
    match_weight = sum(
        (case((clause, weight), else_=0.0) for clause, weight in weighted_clauses),
        start=0.0,
    )
    records = db.query(FileRecord).filter(
        metadata_match,
        FileRecord.ocr_text.isnot(None),
        func.length(func.trim(FileRecord.ocr_text)) > 0,
    )
    return (
        apply_owner_filter(records, request)
        .order_by(case((exact_match, 1), else_=0).desc(), match_weight.desc(), FileRecord.id.asc())
        .limit(_METADATA_CANDIDATE_LIMIT)
        .all()
    )


def _metadata_hit(record: FileRecord) -> dict[str, Any]:
    """Build a bounded, source-backed fallback passage for a metadata match."""
    text = (record.ocr_text or "").strip()[:_METADATA_EXCERPT_CHARS]
    return {
        "score": 0.0,
        "payload": {
            "document_id": record.id,
            "text": text,
            "chunk_index": None,
            "chunk_count": None,
            "token_start": None,
            "token_end": None,
        },
    }


def _hybrid_search_score(query: str, hit: dict[str, Any], record: FileRecord) -> tuple[float, float]:
    """Blend semantic similarity with exact evidence from authoritative metadata."""
    try:
        semantic_score = float(hit.get("score") or 0.0)
    except (TypeError, ValueError):
        semantic_score = 0.0

    normalized_query = _normalized_search_text(query)
    query_tokens = set(normalized_query.split())
    metadata_text = _normalized_search_text(f"{record.document_title or ''} {record.original_filename or ''}")
    metadata_tokens = set(metadata_text.split())
    query_weight = sum(_search_token_weight(token) for token in query_tokens)
    matched_weight = sum(_search_token_weight(token) for token in query_tokens & metadata_tokens)
    token_coverage = matched_weight / query_weight if query_weight else 0.0

    normalized_title = _normalized_search_text(record.document_title)
    normalized_filename = _normalized_search_text(record.original_filename)
    exact_title_bonus = 0.60 if normalized_query and normalized_title and normalized_title in normalized_query else 0.0
    exact_filename_bonus = (
        0.65 if normalized_query and normalized_filename and normalized_filename in normalized_query else 0.0
    )
    phrase_bonus = (
        0.15
        if normalized_query
        and not (exact_title_bonus or exact_filename_bonus)
        and (normalized_query in normalized_title or normalized_query in normalized_filename)
        else 0.0
    )
    hybrid_score = min(
        1.0,
        semantic_score + (0.30 * token_coverage) + exact_title_bonus + exact_filename_bonus + phrase_bonus,
    )
    return hybrid_score, semantic_score


@router.post("/search")
@require_login
def search_knowledge(request: Request, body: KnowledgeSearchRequest, db: DbSession) -> dict[str, Any]:
    """Return source-backed document passages visible to the caller."""
    _require_enabled()
    try:
        from app.utils.vector_index import QdrantVectorIndex

        # Over-fetch because Qdrant ranks globally; DocuElevate applies its
        # authoritative owner/share checks before returning any payload.
        raw_hits = QdrantVectorIndex().search(
            body.query,
            limit=min(max(body.limit * 10, 50), 250),
            score_threshold=body.score_threshold,
        )
    except Exception as exc:
        logger.exception("Knowledge search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Vector knowledge index is unavailable",
        ) from exc

    document_ids: list[int] = []
    for hit in raw_hits:
        value = (hit.get("payload") or {}).get("document_id")
        if isinstance(value, int):
            document_ids.append(value)
    accessible = _accessible_records(db, request, list(set(document_ids)))
    metadata_records = _metadata_candidates(db, request, body.query)
    for record in metadata_records:
        accessible[record.id] = record

    ranked_hits = []
    for original_rank, hit in enumerate(raw_hits):
        payload = hit.get("payload") or {}
        document_id = payload.get("document_id")
        record = accessible.get(document_id)
        if record is None:
            continue
        hybrid_score, semantic_score = _hybrid_search_score(body.query, hit, record)
        ranked_hits.append((hybrid_score, semantic_score, -original_rank, hit, record, "semantic"))

    semantic_document_ids = set(document_ids)
    for metadata_rank, record in enumerate(metadata_records):
        if record.id in semantic_document_ids:
            continue
        hit = _metadata_hit(record)
        hybrid_score, semantic_score = _hybrid_search_score(body.query, hit, record)
        ranked_hits.append((hybrid_score, semantic_score, -metadata_rank, hit, record, "metadata"))

    ranked_hits.sort(key=lambda item: item[:3], reverse=True)
    results = []
    seen_documents: set[int] = set()
    for hybrid_score, semantic_score, _original_rank, hit, record, match_source in ranked_hits:
        if record.id in seen_documents:
            continue
        seen_documents.add(record.id)
        payload = hit.get("payload") or {}
        results.append(
            {
                "document_id": record.id,
                "score": hybrid_score,
                "semantic_score": semantic_score,
                "match_source": match_source,
                "text": payload.get("text", ""),
                "chunk_index": payload.get("chunk_index"),
                "chunk_count": payload.get("chunk_count"),
                "token_start": payload.get("token_start"),
                "token_end": payload.get("token_end"),
                "title": record.document_title,
                "filename": record.original_filename,
                "mime_type": record.mime_type,
                "created_at": record.created_at,
                "source_url": f"/files/{record.id}",
            }
        )
        if len(results) >= body.limit:
            break
    return {"query": body.query, "count": len(results), "results": results}


@router.get("/documents/{file_id}")
@require_login
def get_knowledge_document(request: Request, file_id: int, db: DbSession) -> dict[str, Any]:
    """Fetch the complete OCR text for a cited, accessible document."""
    query = db.query(FileRecord).filter(FileRecord.id == file_id)
    record = apply_owner_filter(query, request).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {
        "document_id": record.id,
        "title": record.document_title,
        "filename": record.original_filename,
        "mime_type": record.mime_type,
        "created_at": record.created_at,
        "text": record.ocr_text or "",
        "source_url": f"/files/{record.id}",
    }


@router.post("/documents/{file_id}/index", status_code=status.HTTP_202_ACCEPTED)
@require_login
def index_knowledge_document(request: Request, file_id: int, db: DbSession) -> dict[str, Any]:
    """Queue an idempotent vector-index refresh for one accessible document."""
    _require_enabled()
    query = db.query(FileRecord).filter(FileRecord.id == file_id)
    record = apply_owner_filter(query, request).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if not record.ocr_text or not record.ocr_text.strip():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document has no OCR text")

    from app.tasks.vector_index import index_document_vectors

    task = index_document_vectors.delay(record.id)
    return {"status": "queued", "document_id": record.id, "task_id": task.id}


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
@require_login
def reindex_knowledge(
    request: Request,
    db: DbSession,
    limit: int = Query(1000, ge=1, le=100000),
) -> dict[str, Any]:
    """Queue accessible OCR-backed documents for idempotent indexing."""
    _require_enabled()
    query = (
        db.query(FileRecord).filter(FileRecord.ocr_text.isnot(None), FileRecord.ocr_text != "").order_by(FileRecord.id)
    )
    records = apply_owner_filter(query, request).limit(limit).all()

    from app.tasks.vector_index import index_document_vectors

    for record in records:
        index_document_vectors.delay(record.id)
    return {"status": "queued", "documents_queued": len(records)}


@router.get("/status")
@require_login
def knowledge_status(request: Request) -> dict[str, Any]:
    """Report configuration and Qdrant collection health without secrets."""
    if not settings.vector_index_enabled:
        return {"enabled": False, "collection": settings.vector_index_collection}
    try:
        from app.utils.vector_index import QdrantVectorIndex

        index_status = QdrantVectorIndex().status()
    except Exception as exc:
        logger.warning("Vector index status check failed: %s", exc)
        index_status = {"available": False, "collection_exists": False, "points_count": 0}
    return {
        "enabled": True,
        "collection": settings.vector_index_collection,
        "embedding_model": settings.embedding_model,
        "chunk_tokens": settings.vector_chunk_tokens,
        "chunk_overlap_tokens": settings.vector_chunk_overlap_tokens,
        **index_status,
    }
