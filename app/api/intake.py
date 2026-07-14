"""Authenticated, idempotent machine-to-machine document intake."""

import hmac
import json
import logging
import os
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.middleware.upload_rate_limit import require_upload_rate_limit
from app.models import DocumentIntake
from app.tasks.convert_to_pdf import convert_to_pdf
from app.tasks.process_document import process_document
from app.utils.allowed_types import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
from app.utils.filename_utils import sanitize_filename
from app.utils.user_scope import get_current_owner_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["document-intake"])
DbSession = Annotated[Session, Depends(get_db)]


def _authenticate_intake(request: Request, shared_secret: str | None) -> tuple[str, str | None]:
    """Return durable principal and optional FileRecord owner identifiers."""
    owner_id = get_current_owner_id(request)
    if owner_id:
        return owner_id, owner_id if settings.multi_user_enabled else None

    configured = settings.document_intake_shared_secret
    if configured and shared_secret and hmac.compare_digest(configured, shared_secret):
        principal = settings.document_intake_shared_owner_id
        return principal, principal if settings.multi_user_enabled else None

    if not settings.auth_enabled:
        return "single-user", None
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Document intake authentication required")


def _serialize_intake(intake: DocumentIntake, *, duplicate: bool = False) -> dict[str, Any]:
    return {
        "intake_id": intake.id,
        "idempotency_key": intake.idempotency_key,
        "source": intake.source,
        "filename": intake.original_filename,
        "state": intake.state,
        "task_id": intake.task_id,
        "duplicate": duplicate,
        "created_at": intake.created_at,
        "updated_at": intake.updated_at,
    }


async def _save_upload(file: UploadFile, target_path: str) -> int:
    temporary_path = f"{target_path}.part"
    written = 0
    try:
        with open(temporary_path, "wb") as output:
            while chunk := await file.read(64 * 1024):
                written += len(chunk)
                if written > settings.max_upload_size:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large")
                output.write(chunk)
        os.replace(temporary_path, target_path)
        return written
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def _queue_document(path: str, filename: str, content_type: str | None, owner_id: str | None):
    extension = os.path.splitext(filename)[1].lower()
    if content_type == "application/pdf" or extension == ".pdf":
        return process_document.delay(path, original_filename=filename, owner_id=owner_id)
    return convert_to_pdf.delay(path, original_filename=filename, owner_id=owner_id)


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def intake_document(
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
    source: str = Form(..., min_length=1, max_length=100),
    idempotency_key: str = Form(..., min_length=8, max_length=255),
    metadata_json: str | None = Form(default=None),
    x_docuelevate_intake_secret: str | None = Header(default=None),
    _rate_ok: None = Depends(require_upload_rate_limit),
) -> dict[str, Any]:
    """Store a document atomically and queue the normal ingestion pipeline."""
    principal_id, owner_id = _authenticate_intake(request, x_docuelevate_intake_secret)

    existing = (
        db.query(DocumentIntake)
        .filter(
            DocumentIntake.principal_id == principal_id,
            DocumentIntake.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return _serialize_intake(existing, duplicate=True)

    safe_filename = sanitize_filename(os.path.basename(file.filename or "document")) or "document"
    extension = os.path.splitext(safe_filename)[1].lower()
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if extension not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported document type")
    if metadata_json:
        try:
            parsed_metadata = json.loads(metadata_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="metadata_json is invalid"
            ) from exc
        if not isinstance(parsed_metadata, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="metadata_json must be an object"
            )

    intake = DocumentIntake(
        principal_id=principal_id,
        idempotency_key=idempotency_key,
        source=source,
        original_filename=safe_filename,
        metadata_json=metadata_json,
    )
    db.add(intake)
    try:
        db.commit()
        db.refresh(intake)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(DocumentIntake)
            .filter(
                DocumentIntake.principal_id == principal_id,
                DocumentIntake.idempotency_key == idempotency_key,
            )
            .one()
        )
        return _serialize_intake(existing, duplicate=True)

    target_name = f"intake_{intake.id}_{uuid.uuid4().hex}{extension}"
    target_path = os.path.join(settings.workdir, target_name)
    try:
        await _save_upload(file, target_path)
        task = _queue_document(target_path, safe_filename, content_type, owner_id)
        intake.local_path = target_path
        intake.task_id = task.id
        intake.state = "queued"
        db.commit()
        db.refresh(intake)
        logger.info("Document intake %s queued task %s from %s", intake.id, task.id, source)
        return _serialize_intake(intake)
    except Exception as exc:
        if os.path.exists(target_path):
            os.remove(target_path)
        intake.state = "failed"
        intake.error = type(exc).__name__
        db.commit()
        raise


@router.get("/documents/{intake_id}")
def get_intake_status(
    intake_id: int,
    request: Request,
    db: DbSession,
    x_docuelevate_intake_secret: str | None = Header(default=None),
) -> dict[str, Any]:
    principal_id, _owner_id = _authenticate_intake(request, x_docuelevate_intake_secret)
    intake = (
        db.query(DocumentIntake)
        .filter(DocumentIntake.id == intake_id, DocumentIntake.principal_id == principal_id)
        .first()
    )
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")
    return _serialize_intake(intake)
