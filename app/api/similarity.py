"""Document similarity API endpoints.

Provides endpoints to find documents similar to a given file based on
text embeddings and cosine similarity scoring, plus debug/diagnostic
endpoints for inspecting and triggering embedding computation.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import FileRecord

logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/files/{file_id}/similar")
@require_login
def get_similar_documents(
    request: Request,
    file_id: int,
    db: DbSession,
    limit: int = Query(5, ge=1, le=20, description="Maximum number of similar documents to return"),
    threshold: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity score (0–1)"),
):
    """Find documents similar to the specified file.

    Uses text embeddings generated from OCR-extracted text and cosine
    similarity to rank documents by relevance.  Similarity scores range
    from 0 (completely different) to 1 (identical content).

    Embeddings are generated on first access and cached for subsequent
    requests.  Documents without OCR text are excluded.

    Query Parameters:
        - limit: Maximum results to return (default: 5, max: 20)
        - threshold: Minimum similarity score to include (default: 0.3)

    Example:
    ```
    GET /api/files/42/similar?limit=5&threshold=0.5
    ```

    Response:
    ```json
    {
      "file_id": 42,
      "similar_documents": [
        {
          "file_id": 15,
          "original_filename": "Invoice_2026-01.pdf",
          "document_title": "January Invoice",
          "similarity_score": 0.8934,
          "mime_type": "application/pdf",
          "created_at": "2026-01-15T10:30:00+00:00"
        }
      ],
      "count": 1
    }
    ```
    """
    # Verify the file exists
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not file_record.ocr_text or not file_record.ocr_text.strip():
        return {
            "file_id": file_id,
            "similar_documents": [],
            "count": 0,
            "message": "No OCR text available for similarity comparison",
        }

    try:
        from app.utils.similarity import find_similar_documents

        similar = find_similar_documents(db, file_id, limit=limit, threshold=threshold)

        return {
            "file_id": file_id,
            "similar_documents": similar,
            "count": len(similar),
        }
    except Exception as e:
        logger.error(f"Error finding similar documents for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute document similarity",
        )


# ---------------------------------------------------------------------------
# Debug / diagnostic endpoints
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/embedding-status")
@require_login
def get_embedding_status(
    request: Request,
    file_id: int,
    db: DbSession,
):
    """Return the embedding status for a single file.

    Useful for debugging whether the embedding has been computed
    and cached for a given document.

    Response:
    ```json
    {
      "file_id": 42,
      "has_embedding": true,
      "embedding_dimensions": 1536,
      "has_ocr_text": true,
      "ocr_text_length": 4200,
      "embedding_model": "text-embedding-3-small"
    }
    ```
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    has_embedding = False
    embedding_dimensions = None
    if file_record.embedding:
        try:
            parsed = json.loads(file_record.embedding)
            has_embedding = True
            embedding_dimensions = len(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

    has_ocr_text = bool(file_record.ocr_text and file_record.ocr_text.strip())

    return {
        "file_id": file_id,
        "has_embedding": has_embedding,
        "embedding_dimensions": embedding_dimensions,
        "has_ocr_text": has_ocr_text,
        "ocr_text_length": len(file_record.ocr_text) if file_record.ocr_text else 0,
        "embedding_model": settings.embedding_model,
    }


@router.post("/files/{file_id}/compute-embedding")
@require_login
def trigger_compute_embedding(
    request: Request,
    file_id: int,
    db: DbSession,
):
    """Trigger embedding computation for a single file.

    If the file already has a cached embedding it will be recomputed.
    The computation happens synchronously so the caller receives the
    result immediately.

    Response:
    ```json
    {
      "file_id": 42,
      "status": "success",
      "embedding_dimensions": 1536
    }
    ```
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not file_record.ocr_text or not file_record.ocr_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has no OCR text — cannot generate embedding",
        )

    try:
        from app.utils.similarity import generate_embedding

        # Clear cached embedding to force recomputation
        file_record.embedding = None
        db.flush()

        embedding = generate_embedding(file_record.ocr_text)
        file_record.embedding = json.dumps(embedding)
        db.commit()

        return {
            "file_id": file_id,
            "status": "success",
            "embedding_dimensions": len(embedding),
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to compute embedding for file {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding computation failed: {e}",
        )


@router.get("/diagnostic/embeddings")
@require_login
def get_embeddings_overview(
    request: Request,
    db: DbSession,
):
    """Return an overview of embedding status across all files.

    Provides aggregate counts as well as a per-file breakdown so an
    administrator can quickly identify documents that are missing
    embeddings.

    Response:
    ```json
    {
      "total_files": 120,
      "files_with_ocr_text": 95,
      "files_with_embedding": 42,
      "files_missing_embedding": 53,
      "embedding_model": "text-embedding-3-small",
      "files": [
        {
          "file_id": 1,
          "original_filename": "invoice.pdf",
          "has_ocr_text": true,
          "has_embedding": true,
          "embedding_dimensions": 1536
        }
      ]
    }
    ```
    """
    all_files = db.query(FileRecord).order_by(FileRecord.id.desc()).all()

    files_info = []
    total_with_ocr = 0
    total_with_embedding = 0

    for f in all_files:
        has_ocr = bool(f.ocr_text and f.ocr_text.strip())
        has_emb = False
        emb_dims = None

        if f.embedding:
            try:
                parsed = json.loads(f.embedding)
                has_emb = True
                emb_dims = len(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        if has_ocr:
            total_with_ocr += 1
        if has_emb:
            total_with_embedding += 1

        files_info.append(
            {
                "file_id": f.id,
                "original_filename": f.original_filename,
                "has_ocr_text": has_ocr,
                "has_embedding": has_emb,
                "embedding_dimensions": emb_dims,
            }
        )

    return {
        "total_files": len(all_files),
        "files_with_ocr_text": total_with_ocr,
        "files_with_embedding": total_with_embedding,
        "files_missing_embedding": total_with_ocr - total_with_embedding,
        "embedding_model": settings.embedding_model,
        "files": files_info,
    }


@router.post("/diagnostic/compute-all-embeddings")
@require_login
def trigger_compute_all_embeddings(
    request: Request,
    db: DbSession,
):
    """Queue embedding computation for all files that have OCR text but no embedding.

    Each file is processed as a separate Celery task so the endpoint
    returns immediately.

    Response:
    ```json
    {
      "status": "queued",
      "files_queued": 53
    }
    ```
    """
    candidates = (
        db.query(FileRecord)
        .filter(
            FileRecord.ocr_text.isnot(None),
            FileRecord.ocr_text != "",
            (FileRecord.embedding.is_(None)) | (FileRecord.embedding == ""),
        )
        .all()
    )

    queued = 0
    for f in candidates:
        try:
            from app.tasks.compute_embedding import compute_document_embedding

            compute_document_embedding.delay(f.id)
            queued += 1
        except Exception as e:
            logger.warning(f"Could not queue embedding for file {f.id}: {e}")

    return {
        "status": "queued",
        "files_queued": queued,
    }
