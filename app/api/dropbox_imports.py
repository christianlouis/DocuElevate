"""Authenticated control plane for resumable Dropbox corpus imports."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import DropboxImportJob, IntegrationDirection, IntegrationType, UserIntegration
from app.utils.user_scope import get_current_owner_id

router = APIRouter(prefix="/dropbox-imports", tags=["dropbox-imports"])
DbSession = Annotated[Session, Depends(get_db)]


class DropboxImportCreate(BaseModel):
    integration_id: int = Field(..., ge=1)
    root_path: str | None = Field(default=None, max_length=2000)


def _job_response(job: DropboxImportJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "integration_id": job.integration_id,
        "root_path": job.root_path,
        "mode": "backfill" if job.is_backfill else "incremental",
        "state": job.state,
        "discovered": job.discovered,
        "downloaded": job.downloaded,
        "queued": job.queued,
        "skipped": job.skipped,
        "failed": job.failed,
        "has_checkpoint": bool(job.cursor),
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _request_owner(request: Request) -> str | None:
    owner_id = get_current_owner_id(request)
    if owner_id:
        return owner_id
    if not settings.auth_enabled:
        return None
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


@router.post("/", status_code=status.HTTP_202_ACCEPTED)
@require_login
def start_dropbox_import(request: Request, body: DropboxImportCreate, db: DbSession) -> dict[str, Any]:
    """Start a non-destructive recursive import for a Dropbox SOURCE integration."""
    owner_id = _request_owner(request)
    query = db.query(UserIntegration).filter(UserIntegration.id == body.integration_id)
    if owner_id is not None:
        query = query.filter(UserIntegration.owner_id == owner_id)
    integration = query.first()
    if not integration or not integration.is_active or integration.direction != IntegrationDirection.SOURCE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dropbox source integration not found")

    try:
        config = json.loads(integration.config or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integration configuration is invalid",
        ) from exc
    if not isinstance(config, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Integration configuration is invalid",
        )
    is_dropbox = integration.integration_type == IntegrationType.DROPBOX or (
        integration.integration_type == IntegrationType.WATCH_FOLDER and config.get("source_type") == "dropbox"
    )
    if not is_dropbox:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration is not a Dropbox source")

    root_path = body.root_path if body.root_path is not None else config.get("folder_path", "")
    job = DropboxImportJob(
        id=str(uuid.uuid4()),
        integration_id=integration.id,
        owner_id=integration.owner_id,
        root_path=root_path or "",
        is_backfill=True,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    from app.tasks.dropbox_corpus_import import schedule_dropbox_corpus_import

    task = schedule_dropbox_corpus_import(job.id)
    response = _job_response(job)
    response["task_id"] = task.id
    return response


@router.get("/{job_id}")
@require_login
def get_dropbox_import(request: Request, job_id: str, db: DbSession) -> dict[str, Any]:
    """Return durable progress for a caller-owned corpus import."""
    owner_id = _request_owner(request)
    query = db.query(DropboxImportJob).filter(DropboxImportJob.id == job_id)
    if owner_id is not None:
        query = query.filter(DropboxImportJob.owner_id == owner_id)
    job = query.first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dropbox import not found")
    return _job_response(job)
