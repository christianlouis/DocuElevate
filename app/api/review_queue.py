"""API endpoints for human review queue items."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.models import DocumentReviewItem, FileRecord
from app.utils.user_scope import apply_owner_filter

router = APIRouter(prefix="/review-queue", tags=["review-queue"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_review_response(item: DocumentReviewItem, file_record: FileRecord) -> dict[str, Any]:
    """Convert a review queue row and file record to an API response."""
    return {
        "id": item.id,
        "file_id": item.file_id,
        "status": item.status,
        "reason": item.reason,
        "confidence_score": item.confidence_score,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "file": {
            "id": file_record.id,
            "original_filename": file_record.original_filename,
            "mime_type": file_record.mime_type,
            "owner_id": file_record.owner_id,
            "created_at": file_record.created_at,
        },
    }


@router.get("/", summary="List documents queued for human review")
@require_login
def list_review_queue(
    request: Request,
    db: DbSession,
    status: str = Query(default="pending", pattern="^(pending|resolved|dismissed|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Return review queue items visible to the current user."""
    query = db.query(DocumentReviewItem, FileRecord).join(FileRecord, DocumentReviewItem.file_id == FileRecord.id)
    query = apply_owner_filter(query, request)
    if status != "all":
        query = query.filter(DocumentReviewItem.status == status)
    rows = query.order_by(DocumentReviewItem.created_at.desc(), DocumentReviewItem.id.desc()).limit(limit).all()
    items = [_to_review_response(item, file_record) for item, file_record in rows]
    return {"items": items, "total": len(items), "status": status}
