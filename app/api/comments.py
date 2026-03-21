"""Document comments and annotations API endpoints.

Provides CRUD operations for threaded comments on documents,
text annotations on PDF pages, and a list of mentionable users
for the @mention feature.
"""

import json
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user_id, require_login
from app.database import get_db
from app.models import DocumentAnnotation, DocumentComment, FileRecord, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["comments"])

DbSession = Annotated[Session, Depends(get_db)]

# Constraints
MAX_COMMENT_BODY_LENGTH = 10_000
MAX_ANNOTATION_CONTENT_LENGTH = 5_000

# Allowed annotation types
ALLOWED_ANNOTATION_TYPES = frozenset({"note", "highlight", "underline", "strikethrough"})

# Simple pattern for @mentions – matches @username tokens inside comment body
_MENTION_PATTERN = re.compile(r"@([\w.\-]+)")


def _extract_mentions(body: str) -> list[str]:
    """Extract unique @mentioned usernames from a comment body.

    Args:
        body: The raw comment text.

    Returns:
        A deduplicated list of mentioned usernames (without the ``@`` prefix).
    """
    return list(dict.fromkeys(_MENTION_PATTERN.findall(body)))


def _serialize_comment(c: DocumentComment) -> dict[str, Any]:
    """Serialize a DocumentComment to a JSON-friendly dict.

    Args:
        c: The comment model instance.

    Returns:
        A dictionary representation of the comment.
    """
    mentions: list[str] = []
    if c.mentions:
        try:
            mentions = json.loads(c.mentions)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "id": c.id,
        "file_id": c.file_id,
        "user_id": c.user_id,
        "parent_id": c.parent_id,
        "body": c.body,
        "mentions": mentions,
        "is_resolved": c.is_resolved,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _serialize_annotation(a: DocumentAnnotation) -> dict[str, Any]:
    """Serialize a DocumentAnnotation to a JSON-friendly dict.

    Args:
        a: The annotation model instance.

    Returns:
        A dictionary representation of the annotation.
    """
    return {
        "id": a.id,
        "file_id": a.file_id,
        "user_id": a.user_id,
        "page": a.page,
        "x": a.x,
        "y": a.y,
        "width": a.width,
        "height": a.height,
        "content": a.content,
        "annotation_type": a.annotation_type,
        "color": a.color,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


def _build_thread_tree(comments: list[DocumentComment]) -> list[dict[str, Any]]:
    """Organize a flat list of comments into a threaded tree structure.

    Top-level comments (``parent_id is None``) appear as root nodes.
    Replies are nested inside their parent's ``replies`` list.

    Args:
        comments: All comments for a given document, ordered by ``created_at``.

    Returns:
        A list of root-level comment dicts, each with a ``replies`` key.
    """
    by_id: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []

    for c in comments:
        node = _serialize_comment(c)
        node["replies"] = []
        by_id[c.id] = node

    for c in comments:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["replies"].append(node)
        else:
            roots.append(node)

    return roots


# ---------------------------------------------------------------------------
# Comments endpoints
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/comments")
@require_login
def list_comments(request: Request, file_id: int, db: DbSession):
    """List all comments for a document, organised into threads.

    Returns a threaded tree where top-level comments contain nested
    ``replies``.

    Path Parameters:
        file_id: The ID of the document.

    Returns:
        A dict with ``file_id``, ``comments`` (threaded), and ``total``.
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    comments = (
        db.query(DocumentComment).filter(DocumentComment.file_id == file_id).order_by(DocumentComment.created_at).all()
    )

    return {
        "file_id": file_id,
        "comments": _build_thread_tree(comments),
        "total": len(comments),
    }


@router.post("/files/{file_id}/comments", status_code=status.HTTP_201_CREATED)
@require_login
def create_comment(
    request: Request,
    file_id: int,
    db: DbSession,
    body: str = Body(..., embed=True),
    parent_id: int | None = Body(None, embed=True),
):
    """Create a new comment on a document.

    Automatically extracts @mentions from the comment body and stores
    them for later notification or UI highlighting.

    Path Parameters:
        file_id: The ID of the document to comment on.

    Request body (JSON):
        body: Comment text (required, max 10 000 characters).
        parent_id: ID of the parent comment for threaded replies (optional).

    Returns:
        The created comment object.
    """
    user_id = get_current_user_id(request)

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not isinstance(body, str) or not body.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="body is required and must be non-empty",
        )
    body = body.strip()
    if len(body) > MAX_COMMENT_BODY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body must be at most {MAX_COMMENT_BODY_LENGTH} characters",
        )

    if parent_id is not None:
        parent = (
            db.query(DocumentComment)
            .filter(DocumentComment.id == parent_id, DocumentComment.file_id == file_id)
            .first()
        )
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found",
            )

    mentions = _extract_mentions(body)

    comment = DocumentComment(
        file_id=file_id,
        user_id=user_id,
        parent_id=parent_id,
        body=body,
        mentions=json.dumps(mentions) if mentions else None,
    )

    try:
        db.add(comment)
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        logger.exception("Failed to create comment on file_id=%s", file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create comment",
        )

    logger.info("Comment created: id=%s, file_id=%s, user=%s", comment.id, file_id, user_id)
    return _serialize_comment(comment)


@router.put("/files/{file_id}/comments/{comment_id}")
@require_login
def update_comment(
    request: Request,
    file_id: int,
    comment_id: int,
    db: DbSession,
    body: str = Body(..., embed=True),
):
    """Update the body of an existing comment.

    Only the comment author may update the comment.  Mentions are
    re-extracted from the updated body.

    Path Parameters:
        file_id: The ID of the document.
        comment_id: The ID of the comment to update.

    Request body (JSON):
        body: New comment text (required).

    Returns:
        The updated comment object.
    """
    user_id = get_current_user_id(request)

    comment = (
        db.query(DocumentComment).filter(DocumentComment.id == comment_id, DocumentComment.file_id == file_id).first()
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if comment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own comments")

    if not isinstance(body, str) or not body.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="body is required and must be non-empty",
        )
    body = body.strip()
    if len(body) > MAX_COMMENT_BODY_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"body must be at most {MAX_COMMENT_BODY_LENGTH} characters",
        )

    mentions = _extract_mentions(body)
    comment.body = body
    comment.mentions = json.dumps(mentions) if mentions else None

    try:
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        logger.exception("Failed to update comment id=%s", comment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update comment",
        )

    logger.info("Comment updated: id=%s, user=%s", comment_id, user_id)
    return _serialize_comment(comment)


@router.delete("/files/{file_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_comment(request: Request, file_id: int, comment_id: int, db: DbSession):
    """Delete a comment.

    Only the comment author may delete the comment.  Replies to the
    deleted comment are **not** removed — they become orphaned root
    comments so that conversation context is preserved.

    Path Parameters:
        file_id: The ID of the document.
        comment_id: The ID of the comment to delete.
    """
    user_id = get_current_user_id(request)

    comment = (
        db.query(DocumentComment).filter(DocumentComment.id == comment_id, DocumentComment.file_id == file_id).first()
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if comment.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own comments")

    try:
        db.delete(comment)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete comment id=%s", comment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete comment",
        )

    logger.info("Comment deleted: id=%s, user=%s", comment_id, user_id)


@router.patch("/files/{file_id}/comments/{comment_id}/resolve")
@require_login
def resolve_comment(
    request: Request,
    file_id: int,
    comment_id: int,
    db: DbSession,
    is_resolved: bool = Body(..., embed=True),
):
    """Mark a top-level comment thread as resolved or unresolved.

    Path Parameters:
        file_id: The ID of the document.
        comment_id: The ID of the comment to resolve / unresolve.

    Request body (JSON):
        is_resolved: ``true`` to resolve, ``false`` to unresolve.

    Returns:
        The updated comment object.
    """
    comment = (
        db.query(DocumentComment).filter(DocumentComment.id == comment_id, DocumentComment.file_id == file_id).first()
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment.is_resolved = is_resolved

    try:
        db.commit()
        db.refresh(comment)
    except Exception:
        db.rollback()
        logger.exception("Failed to resolve comment id=%s", comment_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update comment",
        )

    logger.info("Comment %s: id=%s", "resolved" if is_resolved else "unresolved", comment_id)
    return _serialize_comment(comment)


# ---------------------------------------------------------------------------
# Annotations endpoints
# ---------------------------------------------------------------------------


@router.get("/files/{file_id}/annotations")
@require_login
def list_annotations(request: Request, file_id: int, db: DbSession):
    """List all annotations for a document.

    Path Parameters:
        file_id: The ID of the document.

    Returns:
        A dict with ``file_id``, ``annotations``, and ``total``.
    """
    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    annotations = (
        db.query(DocumentAnnotation)
        .filter(DocumentAnnotation.file_id == file_id)
        .order_by(DocumentAnnotation.page, DocumentAnnotation.created_at)
        .all()
    )

    return {
        "file_id": file_id,
        "annotations": [_serialize_annotation(a) for a in annotations],
        "total": len(annotations),
    }


@router.post("/files/{file_id}/annotations", status_code=status.HTTP_201_CREATED)
@require_login
def create_annotation(
    request: Request,
    file_id: int,
    db: DbSession,
    page: int = Body(..., embed=True),
    x: float = Body(..., embed=True),
    y: float = Body(..., embed=True),
    content: str = Body(..., embed=True),
    width: float = Body(0, embed=True),
    height: float = Body(0, embed=True),
    annotation_type: str = Body("note", embed=True),
    color: str | None = Body(None, embed=True),
):
    """Create a new annotation on a PDF page.

    Path Parameters:
        file_id: The ID of the document.

    Request body (JSON):
        page: Page number (1-based, required).
        x: Horizontal position on the page (required).
        y: Vertical position on the page (required).
        content: Annotation text (required, max 5 000 characters).
        width: Width of the annotation bounding box (default 0).
        height: Height of the annotation bounding box (default 0).
        annotation_type: One of ``note``, ``highlight``, ``underline``,
            ``strikethrough`` (default ``note``).
        color: Optional CSS colour string (e.g. ``#ff0000``).

    Returns:
        The created annotation object.
    """
    user_id = get_current_user_id(request)

    file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content is required and must be non-empty",
        )
    content = content.strip()
    if len(content) > MAX_ANNOTATION_CONTENT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"content must be at most {MAX_ANNOTATION_CONTENT_LENGTH} characters",
        )

    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page must be >= 1",
        )

    if annotation_type not in ALLOWED_ANNOTATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"annotation_type must be one of: {', '.join(sorted(ALLOWED_ANNOTATION_TYPES))}",
        )

    annotation = DocumentAnnotation(
        file_id=file_id,
        user_id=user_id,
        page=page,
        x=x,
        y=y,
        width=width,
        height=height,
        content=content,
        annotation_type=annotation_type,
        color=color,
    )

    try:
        db.add(annotation)
        db.commit()
        db.refresh(annotation)
    except Exception:
        db.rollback()
        logger.exception("Failed to create annotation on file_id=%s", file_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create annotation",
        )

    logger.info("Annotation created: id=%s, file_id=%s, user=%s", annotation.id, file_id, user_id)
    return _serialize_annotation(annotation)


@router.put("/files/{file_id}/annotations/{annotation_id}")
@require_login
def update_annotation(
    request: Request,
    file_id: int,
    annotation_id: int,
    db: DbSession,
    content: str | None = Body(None, embed=True),
    x: float | None = Body(None, embed=True),
    y: float | None = Body(None, embed=True),
    width: float | None = Body(None, embed=True),
    height: float | None = Body(None, embed=True),
    annotation_type: str | None = Body(None, embed=True),
    color: str | None = Body(None, embed=True),
):
    """Update an existing annotation.

    Only the annotation author may update the annotation.

    Path Parameters:
        file_id: The ID of the document.
        annotation_id: The ID of the annotation to update.

    Request body (JSON):
        Any subset of ``content``, ``x``, ``y``, ``width``, ``height``,
        ``annotation_type``, and ``color``.

    Returns:
        The updated annotation object.
    """
    user_id = get_current_user_id(request)

    annotation = (
        db.query(DocumentAnnotation)
        .filter(DocumentAnnotation.id == annotation_id, DocumentAnnotation.file_id == file_id)
        .first()
    )
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if annotation.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own annotations")

    if content is not None:
        content = content.strip() if isinstance(content, str) else ""
        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="content must be non-empty",
            )
        if len(content) > MAX_ANNOTATION_CONTENT_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"content must be at most {MAX_ANNOTATION_CONTENT_LENGTH} characters",
            )
        annotation.content = content

    if x is not None:
        annotation.x = x
    if y is not None:
        annotation.y = y
    if width is not None:
        annotation.width = width
    if height is not None:
        annotation.height = height
    if annotation_type is not None:
        if annotation_type not in ALLOWED_ANNOTATION_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"annotation_type must be one of: {', '.join(sorted(ALLOWED_ANNOTATION_TYPES))}",
            )
        annotation.annotation_type = annotation_type
    if color is not None:
        annotation.color = color

    try:
        db.commit()
        db.refresh(annotation)
    except Exception:
        db.rollback()
        logger.exception("Failed to update annotation id=%s", annotation_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update annotation",
        )

    logger.info("Annotation updated: id=%s, user=%s", annotation_id, user_id)
    return _serialize_annotation(annotation)


@router.delete("/files/{file_id}/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_login
def delete_annotation(request: Request, file_id: int, annotation_id: int, db: DbSession):
    """Delete an annotation.

    Only the annotation author may delete the annotation.

    Path Parameters:
        file_id: The ID of the document.
        annotation_id: The ID of the annotation to delete.
    """
    user_id = get_current_user_id(request)

    annotation = (
        db.query(DocumentAnnotation)
        .filter(DocumentAnnotation.id == annotation_id, DocumentAnnotation.file_id == file_id)
        .first()
    )
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if annotation.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own annotations")

    try:
        db.delete(annotation)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to delete annotation id=%s", annotation_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete annotation",
        )

    logger.info("Annotation deleted: id=%s, user=%s", annotation_id, user_id)


# ---------------------------------------------------------------------------
# Mentionable users endpoint
# ---------------------------------------------------------------------------


@router.get("/users/mentionable")
@require_login
def list_mentionable_users(request: Request, db: DbSession):
    """List users that can be @mentioned in comments.

    Returns all user profiles that are not blocked, sorted by
    ``display_name``.

    Returns:
        A list of ``{user_id, display_name}`` objects.
    """
    profiles = (
        db.query(UserProfile)
        .filter(UserProfile.is_blocked == False)  # noqa: E712
        .order_by(UserProfile.display_name)
        .all()
    )

    return [
        {
            "user_id": p.user_id,
            "display_name": p.display_name or p.user_id,
        }
        for p in profiles
    ]
