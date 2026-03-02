"""Document similarity detection using text embeddings and cosine similarity.

Provides functions to generate text embeddings via the configured AI provider
(OpenAI-compatible) and compute cosine similarity scores between documents.
Embeddings are cached in the ``FileRecord.embedding`` column to avoid
redundant API calls.
"""

import json
import logging
import math
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


def _get_embedding_client() -> Any:
    """Create an OpenAI client for embedding generation.

    Returns:
        An ``openai.OpenAI`` client instance configured from application settings.

    Raises:
        RuntimeError: If the ``openai`` package is not installed.
    """
    try:
        import openai
    except ImportError as exc:
        raise RuntimeError("The 'openai' package is required for embedding generation") from exc

    return openai.OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def generate_embedding(text: str, model: str | None = None) -> list[float]:
    """Generate a text embedding vector using the OpenAI-compatible API.

    Args:
        text: The input text to embed.  Truncated to stay within the
            model's context window based on ``settings.embedding_max_tokens``
            (default 8 000 tokens ≈ 24 000 characters).
        model: The embedding model to use.  When ``None`` (the default), the
            value of ``settings.embedding_model`` is used.

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        RuntimeError: If the OpenAI client cannot be created.
        Exception: If the API call fails.
    """
    if model is None:
        model = settings.embedding_model

    # Truncate to stay within the model's context window.
    # Conservative 3 chars/token estimate (actual ratio varies by language;
    # English averages ~4 chars/token but 3 gives a safety margin).
    max_chars = settings.embedding_max_tokens * 3
    if len(text) > max_chars:
        logger.debug(
            "Truncating text from %d to %d chars (~%d tokens) for model %s",
            len(text),
            max_chars,
            settings.embedding_max_tokens,
            model,
        )
        text = text[:max_chars]

    client = _get_embedding_client()
    logger.debug("Generating embedding for %d chars using model=%s", len(text), model)
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        A similarity score between 0 and 1.  Returns 0.0 if either vector
        has zero magnitude.
    """
    if len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)
    # Clamp to [0, 1] to handle floating-point drift
    return max(0.0, min(1.0, similarity))


def _get_cached_embedding(file_record: Any) -> list[float] | None:
    """Return the cached embedding for a file record, or ``None``.

    This is a **read-only** helper — it never triggers an API call.  Use
    :func:`compute_and_store_embedding` when you need to generate a new
    embedding.

    Args:
        file_record: A ``FileRecord`` instance (or any object with ``id``
            and ``embedding`` attributes).

    Returns:
        The parsed embedding vector, or ``None`` if no valid cached
        embedding exists.
    """
    raw = file_record.embedding if hasattr(file_record, "embedding") else None
    if not raw:
        return None
    try:
        cached = json.loads(raw)
        logger.debug("Using cached embedding for file %s (%d dimensions)", file_record.id, len(cached))
        return cached
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid cached embedding for file %s", file_record.id)
        return None


def compute_and_store_embedding(db: Session, file_record: Any) -> list[float] | None:
    """Generate an embedding for a file and persist it in the database.

    Called during document ingestion (Celery task) or via the manual
    ``POST /api/files/{id}/compute-embedding`` debug endpoint.  The
    similarity query path (:func:`find_similar_documents`) intentionally
    does **not** call this — it only reads pre-computed embeddings so
    that it returns instantly without blocking on external API calls.

    Args:
        db: Active database session.
        file_record: A ``FileRecord`` instance.

    Returns:
        The embedding vector, or ``None`` if the document has no OCR text
        or embedding generation fails.
    """
    # Return cached embedding if already present
    if file_record.embedding:
        try:
            cached = json.loads(file_record.embedding)
            logger.debug("Embedding already cached for file %s (%d dims)", file_record.id, len(cached))
            return cached
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid cached embedding for file %s, recomputing", file_record.id)

    # Need OCR text to generate an embedding
    if not file_record.ocr_text or not file_record.ocr_text.strip():
        logger.debug("No OCR text for file %s, cannot generate embedding", file_record.id)
        return None

    try:
        logger.info("Computing embedding for file %s (%d chars of OCR text)", file_record.id, len(file_record.ocr_text))
        embedding = generate_embedding(file_record.ocr_text)
        # Persist in the database
        file_record.embedding = json.dumps(embedding)
        db.commit()
        logger.info("Embedding computed and cached for file %s (%d dimensions)", file_record.id, len(embedding))
        return embedding
    except Exception as e:
        db.rollback()
        logger.error("Failed to generate embedding for file %s: %s", file_record.id, e)
        return None


# Keep the legacy alias so that existing callers (e.g. tests) keep working.
_get_or_compute_embedding = compute_and_store_embedding


def find_similar_documents(
    db: Session,
    file_id: int,
    limit: int = 5,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Find documents similar to the given file using **pre-computed** embeddings.

    Only documents whose embeddings were already generated (during
    ingestion or via the debug endpoint) are considered.  No external API
    calls are made — the function reads cached vectors from the database
    and computes cosine similarity in-process.

    To keep memory usage bounded for large corpora (100 k+ documents) the
    candidate query fetches only the columns needed for scoring and
    iterates in chunks via ``yield_per``.

    Args:
        db: Active database session.
        file_id: The ID of the target ``FileRecord``.
        limit: Maximum number of similar documents to return.
        threshold: Minimum similarity score (0–1) to include in results.

    Returns:
        A list of dicts, each containing:
        - ``file_id``: The similar document's ID.
        - ``original_filename``: The document's original filename.
        - ``document_title``: The document's AI-extracted title (may be None).
        - ``similarity_score``: Cosine similarity (0–1, rounded to 4 decimals).
        - ``mime_type``: The document's MIME type.
        - ``created_at``: ISO-formatted creation timestamp.
    """
    from app.models import FileRecord

    # Get the target document's cached embedding (read-only, no API call)
    target = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not target:
        return []

    target_embedding = _get_cached_embedding(target)
    if not target_embedding:
        logger.info("No cached embedding for target file %s — skipping similarity search", file_id)
        return []

    # Query only candidates that already have a pre-computed embedding.
    # Fetch only the columns needed for scoring to minimise memory use.
    # yield_per streams rows in chunks so we never materialise all 100k+
    # records at once.
    candidates = (
        db.query(
            FileRecord.id,
            FileRecord.original_filename,
            FileRecord.document_title,
            FileRecord.mime_type,
            FileRecord.created_at,
            FileRecord.embedding,
        )
        .filter(
            FileRecord.id != file_id,
            FileRecord.embedding.isnot(None),
            FileRecord.embedding != "",
        )
        .yield_per(500)
    )

    results: list[dict[str, Any]] = []
    for row in candidates:
        try:
            candidate_embedding: list[float] = json.loads(row.embedding)
        except (json.JSONDecodeError, TypeError):
            continue

        score = cosine_similarity(target_embedding, candidate_embedding)
        if score >= threshold:
            results.append(
                {
                    "file_id": row.id,
                    "original_filename": row.original_filename,
                    "document_title": row.document_title,
                    "similarity_score": round(score, 4),
                    "mime_type": row.mime_type,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )

    # Sort by similarity score descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:limit]
