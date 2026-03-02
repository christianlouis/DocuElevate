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


def generate_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Generate a text embedding vector using the OpenAI-compatible API.

    Args:
        text: The input text to embed.  Truncated to ~8000 tokens worth of
            characters to stay within model limits.
        model: The embedding model to use.  Defaults to ``text-embedding-3-small``.

    Returns:
        A list of floats representing the embedding vector.

    Raises:
        RuntimeError: If the OpenAI client cannot be created.
        Exception: If the API call fails.
    """
    # Truncate very long texts to stay within token limits (~4 chars per token)
    max_chars = 30000
    if len(text) > max_chars:
        text = text[:max_chars]

    client = _get_embedding_client()
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


def _get_or_compute_embedding(db: Session, file_record: Any) -> list[float] | None:
    """Retrieve a cached embedding or compute and store a new one.

    Args:
        db: Active database session.
        file_record: A ``FileRecord`` instance.

    Returns:
        The embedding vector, or ``None`` if the document has no OCR text
        or embedding generation fails.
    """
    # Return cached embedding if available
    if file_record.embedding:
        try:
            return json.loads(file_record.embedding)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Invalid cached embedding for file {file_record.id}, recomputing")

    # Need OCR text to generate an embedding
    if not file_record.ocr_text or not file_record.ocr_text.strip():
        return None

    try:
        embedding = generate_embedding(file_record.ocr_text)
        # Cache the embedding in the database
        file_record.embedding = json.dumps(embedding)
        db.commit()
        return embedding
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate embedding for file {file_record.id}: {e}")
        return None


def find_similar_documents(
    db: Session,
    file_id: int,
    limit: int = 5,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Find documents similar to the given file.

    Computes cosine similarity between the target document's embedding and
    all other documents that have OCR text.  Results are sorted by descending
    similarity score.

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

    # Get the target document
    target = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not target:
        return []

    # Get the target embedding
    target_embedding = _get_or_compute_embedding(db, target)
    if not target_embedding:
        return []

    # Get candidate documents (those with OCR text, excluding the target)
    candidates = (
        db.query(FileRecord)
        .filter(
            FileRecord.id != file_id,
            FileRecord.ocr_text.isnot(None),
            FileRecord.ocr_text != "",
        )
        .all()
    )

    results = []
    for candidate in candidates:
        candidate_embedding = _get_or_compute_embedding(db, candidate)
        if not candidate_embedding:
            continue

        score = cosine_similarity(target_embedding, candidate_embedding)
        if score >= threshold:
            results.append(
                {
                    "file_id": candidate.id,
                    "original_filename": candidate.original_filename,
                    "document_title": candidate.document_title,
                    "similarity_score": round(score, 4),
                    "mime_type": candidate.mime_type,
                    "created_at": candidate.created_at.isoformat() if candidate.created_at else None,
                }
            )

    # Sort by similarity score descending
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:limit]
