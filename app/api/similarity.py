"""Document similarity API endpoints.

Provides an endpoint to find documents similar to a given file based on
text embeddings and cosine similarity scoring.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import require_login
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
