"""API endpoints for human review queue items."""

import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user_id, require_login
from app.database import get_db
from app.models import DocumentReviewItem, FileRecord
from app.utils.user_scope import apply_owner_filter

router = APIRouter(prefix="/review-queue", tags=["review-queue"])

DbSession = Annotated[Session, Depends(get_db)]


class ReviewResolution(BaseModel):
    status: Literal["resolved", "dismissed"] = "resolved"
    metadata: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=2000)


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


@router.post("/{item_id}/resolve", summary="Edit metadata and resolve a review item")
@require_login
def resolve_review_item(item_id: int, body: ReviewResolution, request: Request, db: DbSession) -> dict[str, Any]:
    row = (
        db.query(DocumentReviewItem, FileRecord)
        .join(FileRecord, DocumentReviewItem.file_id == FileRecord.id)
        .filter(DocumentReviewItem.id == item_id)
    )
    row = apply_owner_filter(row, request).first()
    if not row:
        raise HTTPException(status_code=404, detail="Review item not found")
    item, file_record = row
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Review item has already been resolved")
    if body.metadata is not None:
        current = json.loads(file_record.ai_metadata or "{}")
        current.update(body.metadata)
        file_record.ai_metadata = json.dumps(current, ensure_ascii=False)
    item.status = body.status
    item.resolved_by = get_current_user_id(request)
    item.resolution_note = body.note
    item.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _to_review_response(item, file_record)


def enqueue_low_confidence_review(
    db: Session, file_record: FileRecord, metadata: dict[str, Any], threshold: int
) -> DocumentReviewItem | None:
    """Queue a document once when extraction confidence is below the threshold."""
    try:
        confidence = int(metadata.get("confidence_score"))
    except (TypeError, ValueError):
        return None
    if confidence >= threshold:
        return None
    existing = (
        db.query(DocumentReviewItem)
        .filter(DocumentReviewItem.file_id == file_record.id, DocumentReviewItem.status == "pending")
        .first()
    )
    if existing:
        return existing
    item = DocumentReviewItem(
        file_id=file_record.id,
        reason=f"Extraction confidence {confidence} is below threshold {threshold}",
        confidence_score=confidence,
        status="pending",
        created_by="system",
    )
    db.add(item)
    return item
