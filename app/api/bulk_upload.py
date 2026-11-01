"""Reload-safe, idempotent bulk upload API."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.intake import _authenticate_intake
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import FileRecord, UploadBatch, UploadItem, UploadOutbox
from app.tasks.dispatch_uploads import dispatch_upload_item
from app.utils.allowed_types import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
from app.utils.bulk_upload import safe_path, sniff_mime, stream_to_file
from app.utils.filename_utils import sanitize_filename
from app.utils.tribe_scope import ensure_document_scope
from app.utils.user_scope import get_current_owner_id

router = APIRouter(prefix="/uploads", tags=["bulk-uploads"])
Db = Annotated[Session, Depends(get_db)]


def _principal(request: Request, secret: str | None = None) -> tuple[str, str | None]:
    return _authenticate_intake(request, secret)


def _batch(db: Session, batch_id: str, principal: str) -> UploadBatch:
    row = db.query(UploadBatch).filter(UploadBatch.id == batch_id, UploadBatch.principal_id == principal).one_or_none()
    if row is None:
        raise HTTPException(404, "upload batch not found")
    return row


def _snapshot(db: Session, batch: UploadBatch, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    items = db.query(UploadItem).filter(UploadItem.batch_id == batch.id).order_by(UploadItem.id.asc()).offset(max(offset, 0)).limit(limit).all()
    accepted = db.query(UploadItem).filter(UploadItem.batch_id == batch.id, UploadItem.state.in_({"accepted", "duplicate", "queued", "processing", "complete"})).count()
    return {"batch_id": batch.id, "state": batch.state, "total_files": batch.total_files, "total_bytes": batch.total_bytes,
            "accepted": accepted,
            "items": [{"client_id": i.client_id, "file_id": i.file_id, "state": i.state, "sha256": i.sha256, "size": i.size, "filename": i.filename} for i in items]}


@router.post("/batches", status_code=201)
def create_batch(request: Request, db: Db, payload: dict[str, Any] = Body(...), x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, owner = _principal(request, x_docuelevate_intake_secret)
    client_batch_id = str(payload.get("client_batch_id", ""))
    total_files = int(payload.get("total_files", 0))
    total_bytes = int(payload.get("total_bytes", 0))
    if total_files < 0 or total_bytes < 0 or total_files > 100_000:
        raise HTTPException(422, "invalid batch totals")
    existing = db.query(UploadBatch).filter(UploadBatch.principal_id == principal, UploadBatch.client_batch_id == client_batch_id).one_or_none()
    if existing:
        return _snapshot(db, existing)
    batch = UploadBatch(id=str(uuid.uuid4()), principal_id=principal, owner_id=owner, client_batch_id=client_batch_id, total_files=total_files, total_bytes=total_bytes)
    db.add(batch)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        batch = db.query(UploadBatch).filter(UploadBatch.principal_id == principal, UploadBatch.client_batch_id == client_batch_id).one()
    return _snapshot(db, batch)


@router.post("/preflight")
def preflight(request: Request, db: Db, payload: dict[str, Any], x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, _ = _principal(request, x_docuelevate_intake_secret)
    batch = _batch(db, payload.get("batch_id", ""), principal)
    result = []
    for entry in payload.get("files", []):
        sha = str(entry.get("sha256", "")).lower()
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            result.append({"client_id": entry.get("client_id"), "state": "invalid_hash"})
            continue
        found = db.query(FileRecord).filter(FileRecord.filehash == sha, FileRecord.is_duplicate.is_(False), FileRecord.owner_id == batch.owner_id if settings.multi_user_enabled else True).order_by(FileRecord.id.asc()).first()
        result.append({"client_id": entry.get("client_id"), "sha256": sha, "state": "duplicate" if found else "new", "file_id": found.id if found else None})
    return {"batch_id": batch.id, "files": result}


@router.get("/capacity")
def capacity(request: Request, db: Db, batch_id: str, x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, _ = _principal(request, x_docuelevate_intake_secret)
    batch = _batch(db, batch_id, principal)
    used = db.query(UploadItem).filter(UploadItem.principal_id == principal, UploadItem.state.in_(["accepted", "queued", "processing"])).with_entities(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(UploadItem.size), 0)).scalar() or 0
    max_bytes = min(int(settings.max_upload_size) * 10, 10 * 1024 * 1024 * 1024)
    return {"batch_id": batch.id, "slots": max(0, 1000 - db.query(UploadItem).filter(UploadItem.principal_id == principal, UploadItem.state.in_(["accepted", "queued", "processing"])).count()), "max_bytes": max_bytes, "used_bytes": int(used), "retry_after": 1 if used >= max_bytes else 0}


@router.post("/files", status_code=202)
def upload_file(request: Request, db: Db, file: UploadFile = File(...), batch_id: str = Form(...), client_id: str = Form(...), sha256: str = Form(...), x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, owner = _principal(request, x_docuelevate_intake_secret)
    batch = _batch(db, batch_id, principal)
    sha256 = sha256.lower().strip()
    existing = db.query(UploadItem).filter(UploadItem.batch_id == batch.id, UploadItem.client_id == client_id).one_or_none()
    if existing:
        return {"file_id": existing.file_id, "state": existing.state, "duplicate": existing.state == "duplicate", "client_id": client_id}
    filename = sanitize_filename(file.filename or "document") or "document"
    ext = __import__("os").path.splitext(filename)[1].lower()
    supplied = (file.content_type or "").split(";", 1)[0].lower()
    if ext not in ALLOWED_EXTENSIONS and supplied not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, "unsupported document type")
    if len(sha256) != 64:
        raise HTTPException(422, "sha256 is required")
    active_count = db.query(UploadItem).filter(UploadItem.principal_id == principal, UploadItem.state.in_(["accepted", "queued", "processing"])).count()
    active_bytes = db.query(UploadItem).filter(UploadItem.principal_id == principal, UploadItem.state.in_(["accepted", "queued", "processing"])).with_entities(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(UploadItem.size), 0)).scalar() or 0
    max_bytes = min(int(settings.max_upload_size) * 10, 10 * 1024 * 1024 * 1024)
    if active_count >= 1000 or int(active_bytes) >= max_bytes:
        raise HTTPException(429, "upload capacity exhausted", headers={"Retry-After": "5"})
    item = UploadItem(batch_id=batch.id, client_id=client_id, principal_id=principal, sha256=sha256, filename=filename, mime_type=supplied, size=0)
    db.add(item)
    db.flush()
    target = safe_path(batch.id, item.id, filename)
    try:
        size, actual = stream_to_file(file, target, sha256, settings.max_upload_size)
        with target.open("rb") as probe:
            mime = sniff_mime(filename, supplied, probe.read(16))
        if ext not in ALLOWED_EXTENSIONS and mime not in ALLOWED_MIME_TYPES:
            raise ValueError("unsupported content type")
        duplicate = db.query(FileRecord).filter(FileRecord.filehash == actual, FileRecord.is_duplicate.is_(False), FileRecord.owner_id == owner if settings.multi_user_enabled else True).order_by(FileRecord.id.asc()).first()
        tenant_id, tribe_id = ensure_document_scope(db, owner)
        record = FileRecord(filehash=actual, original_filename=filename, local_filename=str(target), original_file_path=str(target), file_size=size, mime_type=mime, owner_id=owner, tenant_id=tenant_id, tribe_id=tribe_id, is_duplicate=bool(duplicate), duplicate_of_id=duplicate.id if duplicate else None)
        db.add(record)
        db.flush()
        item.file_id = record.id
        item.size = size
        item.mime_type = mime
        item.state = "duplicate" if duplicate else "accepted"
        db.add(UploadOutbox(item_id=item.id))
        db.commit()
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise HTTPException(422, "upload failed validation")
    return {"file_id": record.id, "state": item.state, "duplicate": bool(duplicate), "client_id": client_id}


@router.get("/batches/{batch_id}")
def get_batch(request: Request, db: Db, batch_id: str, offset: int = 0, limit: int = 100, x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, _ = _principal(request, x_docuelevate_intake_secret)
    return _snapshot(db, _batch(db, batch_id, principal), offset, limit)


@router.websocket("/events")
async def events(websocket: WebSocket):
    origin = websocket.headers.get("origin", "")
    configured = settings.cors_allowed_origins
    if isinstance(configured, str):
        configured = [x.strip() for x in configured.split(",") if x.strip()]
    allowed = {str(x).rstrip("/") for x in configured}
    if origin and allowed and origin.rstrip("/") not in allowed:
        await websocket.close(code=1008)
        return
    batch_id = websocket.query_params.get("batch_id")
    if not batch_id:
        await websocket.close(code=1008)
        return
    secret = websocket.headers.get("x-docuelevate-intake-secret")
    if settings.auth_enabled and not (settings.document_intake_shared_secret and secret and secret == settings.document_intake_shared_secret):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    db = SessionLocal()
    try:
        batch = db.query(UploadBatch).filter(UploadBatch.id == batch_id).one_or_none()
        if batch is None:
            await websocket.close(code=1008)
            return
        await websocket.send_json({"type": "capacity", "batch_id": batch_id, "retry_after": 0})
        await websocket.send_json({"type": "snapshot", **_snapshot(db, batch, 0, 100)})
        while True:
            await websocket.receive_text()
            db.expire_all()
            await websocket.send_json({"type": "snapshot", **_snapshot(db, batch, 0, 100)})
    except WebSocketDisconnect:
        return
    finally:
        db.close()
