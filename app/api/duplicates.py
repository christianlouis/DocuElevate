"""Duplicate document detection and management API endpoints.

Provides endpoints for listing all duplicate groups (exact SHA-256 duplicates) and
for retrieving both exact and near-duplicate matches for a specific document.

Near-duplicate detection is powered by the same text-embedding cosine-similarity
engine used by the ``/api/files/{id}/similar`` endpoint
(see ``app/utils/similarity.py``).
"""

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


@router.get("/duplicates")
@require_login
def list_duplicate_groups(
    request: Request,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=200, description="Items per page"),
):
    """List all groups of exact-duplicate documents (same SHA-256 hash).

    Returns one entry per duplicate group showing the original document and all
    files that were detected as copies of it.  Groups are sorted by descending
    duplicate count.

    Example:
    ```
    GET /api/duplicates
    ```

    Response:
    ```json
    {
      "groups": [
        {
          "filehash": "abc123...",
          "original": {"id": 1, "original_filename": "invoice.pdf", ...},
          "duplicates": [{"id": 5, "original_filename": "invoice_copy.pdf", ...}],
          "duplicate_count": 1
        }
      ],
      "total_groups": 1,
      "total_duplicate_files": 1,
      "pagination": {...}
    }
    ```
    """
    # Find all hashes that have at least one duplicate record
    dup_hashes_query = db.query(FileRecord.filehash).filter(FileRecord.is_duplicate.is_(True)).distinct()
    total_groups = dup_hashes_query.count()

    # Paginate hash groups
    offset = (page - 1) * per_page
    dup_hashes = [row.filehash for row in dup_hashes_query.offset(offset).limit(per_page).all()]

    groups = []
    total_duplicate_files = 0

    for filehash in dup_hashes:
        # Find the original (non-duplicate) record with this hash
        original = (
            db.query(FileRecord)
            .filter(FileRecord.filehash == filehash, FileRecord.is_duplicate.is_(False))
            .order_by(FileRecord.id.asc())
            .first()
        )

        # Find all duplicate records for this hash
        duplicates = (
            db.query(FileRecord)
            .filter(FileRecord.filehash == filehash, FileRecord.is_duplicate.is_(True))
            .order_by(FileRecord.id.asc())
            .all()
        )

        total_duplicate_files += len(duplicates)

        groups.append(
            {
                "filehash": filehash,
                "original": _file_record_to_dict(original) if original else None,
                "duplicates": [_file_record_to_dict(d) for d in duplicates],
                "duplicate_count": len(duplicates),
            }
        )

    total_pages = (total_groups + per_page - 1) // per_page if total_groups > 0 else 1

    return {
        "groups": groups,
        "total_groups": total_groups,
        "total_duplicate_files": total_duplicate_files,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_groups,
            "pages": total_pages,
            "next": str(request.url.include_query_params(page=page + 1)) if page < total_pages else None,
            "previous": str(request.url.include_query_params(page=page - 1)) if page > 1 else None,
        },
    }


@router.get("/files/{file_id}/duplicates")
@require_login
def get_file_duplicates(
    request: Request,
    file_id: int,
    db: DbSession,
    near_duplicate_limit: int = Query(5, ge=1, le=20, description="Maximum near-duplicates to return"),
    near_duplicate_threshold: float = Query(
        -1.0,
        ge=-1.0,
        le=1.0,
        description="Minimum similarity score for near-duplicates; -1 uses the configured default",
    ),
):
    """Get exact and near-duplicate documents for the specified file.

    **Exact duplicates** share the same SHA-256 hash.
    **Near-duplicates** have a text-embedding cosine similarity score ≥
    ``NEAR_DUPLICATE_THRESHOLD`` (configurable; default 0.85).

    Near-duplicate detection requires OCR text to be available for both the
    target file and candidate files.  Files without OCR text are excluded.

    Example:
    ```
    GET /api/files/42/duplicates
    ```

    Response:
    ```json
    {
      "file_id": 42,
      "exact_duplicates": [
        {"id": 7, "original_filename": "invoice.pdf", "is_duplicate": true, "duplicate_of_id": 42, ...}
      ],
      "near_duplicates": [
        {"file_id": 15, "original_filename": "invoice_jan.pdf", "similarity_score": 0.92, ...}
      ],
      "near_duplicate_threshold": 0.85
    }
    ```
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # --- Exact duplicates ---
    # Case 1: This file is the original — find all records that are duplicates of it
    exact_duplicates_of_this = (
        db.query(FileRecord)
        .filter(FileRecord.filehash == file_record.filehash, FileRecord.id != file_id)
        .order_by(FileRecord.id.asc())
        .all()
    )

    # Case 2: This file itself is a duplicate — find the original
    is_self_duplicate = file_record.is_duplicate
    duplicate_of_original: FileRecord | None = None
    if is_self_duplicate and file_record.duplicate_of_id:
        duplicate_of_original = db.query(FileRecord).filter(FileRecord.id == file_record.duplicate_of_id).first()

    exact_duplicate_dicts = [_file_record_to_dict(f) for f in exact_duplicates_of_this]

    # --- Near-duplicates (embedding-based) ---
    effective_threshold = (
        near_duplicate_threshold if near_duplicate_threshold >= 0.0 else settings.near_duplicate_threshold
    )

    near_duplicates: list[dict] = []
    if file_record.ocr_text and file_record.ocr_text.strip():
        try:
            from app.utils.similarity import find_similar_documents

            near_duplicates = find_similar_documents(
                db,
                file_id,
                limit=near_duplicate_limit,
                threshold=effective_threshold,
            )
        except Exception as e:
            logger.warning(f"Near-duplicate detection failed for file {file_id}: {e}")
            near_duplicates = []

    return {
        "file_id": file_id,
        "is_duplicate": is_self_duplicate,
        "duplicate_of": _file_record_to_dict(duplicate_of_original) if duplicate_of_original else None,
        "exact_duplicates": exact_duplicate_dicts,
        "near_duplicates": near_duplicates,
        "near_duplicate_threshold": effective_threshold,
        "exact_duplicate_count": len(exact_duplicate_dicts),
        "near_duplicate_count": len(near_duplicates),
    }


def _file_record_to_dict(file_record: FileRecord | None) -> dict | None:
    """Serialise a ``FileRecord`` to a plain dict for JSON responses."""
    if file_record is None:
        return None
    return {
        "id": file_record.id,
        "original_filename": file_record.original_filename,
        "filehash": file_record.filehash,
        "file_size": file_record.file_size,
        "mime_type": file_record.mime_type,
        "is_duplicate": file_record.is_duplicate,
        "duplicate_of_id": file_record.duplicate_of_id,
        "document_title": file_record.document_title,
        "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
    }
