"""Durable, bounded bulk-upload intake."""
from __future__ import annotations

import os
import shutil
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.intake import _authenticate_intake
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import FileRecord, UploadBatch, UploadCapacity, UploadItem, UploadOutbox
from app.utils.allowed_types import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
from app.utils.bulk_upload import safe_path, sniff_mime, stream_to_file
from app.utils.filename_utils import sanitize_filename
from app.utils.tribe_scope import ensure_document_scope

router = APIRouter(prefix="/uploads", tags=["bulk-uploads"])
Db = Annotated[Session, Depends(get_db)]
MAX_ACTIVE_FILES = 1000
MAX_PREFLIGHT_FILES = 200


def _principal(request: Request, secret: str | None = None) -> tuple[str, str | None]:
    return _authenticate_intake(request, secret)


def _capacity_limit() -> int:
    return min(int(settings.max_upload_size) * 10, 10 * 1024 * 1024 * 1024)


def _batch(db: Session, batch_id: str, principal: str) -> UploadBatch:
    row = db.query(UploadBatch).filter(UploadBatch.id == batch_id, UploadBatch.principal_id == principal).one_or_none()
    if row is None:
        raise HTTPException(404, "upload batch not found")
    return row


def _snapshot(db: Session, batch: UploadBatch, cursor: int | None = None, limit: int = 100) -> dict[str, Any]:
    """Return one bounded page plus server-side aggregates, never a 40k list."""
    limit = min(max(limit, 1), MAX_PREFLIGHT_FILES)
    query = db.query(UploadItem).filter(UploadItem.batch_id == batch.id)
    if cursor is not None:
        query = query.filter(UploadItem.id > max(cursor, 0))
    rows = query.order_by(UploadItem.id.asc()).limit(limit + 1).all()
    more, items = len(rows) > limit, rows[:limit]
    aggregates = dict(db.query(UploadItem.state, func.count(UploadItem.id)).filter(UploadItem.batch_id == batch.id).group_by(UploadItem.state).all())
    return {
        "batch_id": batch.id, "state": batch.state, "total_files": batch.total_files, "total_bytes": batch.total_bytes,
        "aggregates": aggregates,
        "accepted": sum(aggregates.get(state, 0) for state in ("accepted", "duplicate", "queued", "processing", "complete")),
        "items": [{"id": item.id, "client_id": item.client_id, "file_id": item.file_id, "state": item.state, "sha256": item.sha256, "size": item.size, "filename": item.filename} for item in items],
        "next_cursor": items[-1].id if more and items else None,
    }


def _capacity(db: Session) -> UploadCapacity:
    ledger = db.get(UploadCapacity, 1)
    if ledger is None:  # migration seeds this; needed by metadata-created test DBs
        ledger = UploadCapacity(id=1, reserved_files=0, reserved_bytes=0)
        db.add(ledger)
        db.flush()
    return ledger


def _reserve_capacity(db: Session, size: int) -> bool:
    """Atomically reserve global backlog capacity in the acceptance transaction."""
    _capacity(db)
    result = db.execute(update(UploadCapacity).where(
        UploadCapacity.id == 1,
        UploadCapacity.reserved_files < MAX_ACTIVE_FILES,
        UploadCapacity.reserved_bytes <= _capacity_limit() - size,
    ).values(
        reserved_files=UploadCapacity.reserved_files + 1,
        reserved_bytes=UploadCapacity.reserved_bytes + size,
    ))
    return result.rowcount == 1


def _owner_file_query(db: Session, owner: str | None, sha256: str):
    query = db.query(FileRecord).filter(FileRecord.filehash == sha256, FileRecord.is_duplicate.is_(False))
    return query.filter(FileRecord.owner_id == owner) if settings.multi_user_enabled else query


@router.post("/batches", status_code=201)
def create_batch(request: Request, db: Db, payload: dict[str, Any] = Body(...), x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, owner = _principal(request, x_docuelevate_intake_secret)
    client_batch_id = str(payload.get("client_batch_id", "")).strip()
    try:
        total_files, total_bytes = int(payload.get("total_files")), int(payload.get("total_bytes"))
    except (TypeError, ValueError):
        raise HTTPException(422, "batch totals are required integers")
    if not client_batch_id or total_files <= 0 or total_bytes < 0 or total_files > 100_000:
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
    batch = _batch(db, str(payload.get("batch_id", "")), principal)
    files = payload.get("files")
    if not isinstance(files, list) or len(files) > MAX_PREFLIGHT_FILES:
        raise HTTPException(422, f"preflight accepts at most {MAX_PREFLIGHT_FILES} files")
    result = []
    for entry in files:
        if not isinstance(entry, dict):
            raise HTTPException(422, "invalid preflight entry")
        sha = str(entry.get("sha256", "")).lower()
        if len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha):
            result.append({"client_id": entry.get("client_id"), "state": "invalid_hash"})
            continue
        found = _owner_file_query(db, batch.owner_id, sha).order_by(FileRecord.id.asc()).first()
        result.append({"client_id": entry.get("client_id"), "sha256": sha, "state": "duplicate" if found else "new", "file_id": found.id if found else None})
    return {"batch_id": batch.id, "files": result}


@router.get("/capacity")
def capacity(request: Request, db: Db, batch_id: str, x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, _ = _principal(request, x_docuelevate_intake_secret)
    batch, ledger, limit = _batch(db, batch_id, principal), _capacity(db), _capacity_limit()
    exhausted = ledger.reserved_files >= MAX_ACTIVE_FILES or ledger.reserved_bytes >= limit
    return {"batch_id": batch.id, "slots": max(0, MAX_ACTIVE_FILES - ledger.reserved_files), "max_bytes": limit, "used_bytes": ledger.reserved_bytes, "retry_after": 5 if exhausted else 0}


@router.post("/files", status_code=202)
def upload_file(request: Request, db: Db, file: UploadFile = File(...), batch_id: str = Form(...), client_id: str = Form(...), sha256: str = Form(...), x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, owner = _principal(request, x_docuelevate_intake_secret)
    batch, sha256 = _batch(db, batch_id, principal), sha256.lower().strip()
    if settings.multi_user_enabled and owner:
        from app.utils.subscription import QuotaExceeded, check_upload_allowed, get_user_tier_id
        try:
            check_upload_allowed(db, owner, get_user_tier_id(db, owner))
        except QuotaExceeded as exc:
            raise HTTPException(402, str(exc)) from exc
    if not client_id or len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise HTTPException(422, "client_id and sha256 are required")
    existing = db.query(UploadItem).filter(UploadItem.batch_id == batch.id, UploadItem.client_id == client_id).one_or_none()
    if existing:
        if existing.sha256 != sha256:
            raise HTTPException(409, "client_id was already used for different content")
        return {"file_id": existing.file_id, "state": existing.state, "duplicate": existing.state == "duplicate", "client_id": client_id}
    filename = sanitize_filename(file.filename or "document") or "document"
    ext, supplied = os.path.splitext(filename)[1].lower(), (file.content_type or "").split(";", 1)[0].lower()
    if ext not in ALLOWED_EXTENSIONS or (supplied and supplied not in ALLOWED_MIME_TYPES):
        raise HTTPException(415, "unsupported document type")
    # Do not hold a database transaction while bytes are streaming.  The
    # request body is already spooled by Starlette; a random staging name
    # avoids serialising large concurrent uploads merely to obtain an item id.
    target = safe_path(batch.id, str(uuid.uuid4()), filename)
    try:
        size, actual = stream_to_file(file, target, sha256, settings.max_upload_size)
        if shutil.disk_usage(target.parent).free < size:
            raise OSError("insufficient free disk space")
        with target.open("rb") as probe:
            header = probe.read(16)
            mime = sniff_mime(filename, supplied, header)
        # Never let a browser supplied MIME type turn arbitrary bytes into a
        # PDF.  OOXML containers are likewise checked by sniff_mime's ZIP
        # signature before their declared content type is retained.
        if ext == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValueError("PDF signature is missing")
        if mime not in ALLOWED_MIME_TYPES:
            raise ValueError("unsupported content type")
        duplicate = _owner_file_query(db, owner, actual).order_by(FileRecord.id.asc()).first()
        if not duplicate and not _reserve_capacity(db, size):
            raise HTTPException(429, "upload capacity exhausted", headers={"Retry-After": "5"})
        tenant_id, tribe_id = ensure_document_scope(db, owner)
        item = UploadItem(batch_id=batch.id, client_id=client_id, principal_id=principal, sha256=sha256, filename=filename, mime_type=mime, size=size, state="duplicate" if duplicate else "accepted")
        db.add(item)
        record = FileRecord(filehash=actual, original_filename=filename, local_filename=str(target), original_file_path=str(target), file_size=size, mime_type=mime, owner_id=owner, tenant_id=tenant_id, tribe_id=tribe_id, is_duplicate=bool(duplicate), duplicate_of_id=duplicate.id if duplicate else None)
        db.add(record)
        db.flush()
        item.file_id = record.id
        if not duplicate:
            db.add(UploadOutbox(item_id=item.id))
        db.commit()
    except HTTPException:
        db.rollback(); target.unlink(missing_ok=True); raise
    except IntegrityError:
        db.rollback(); target.unlink(missing_ok=True)
        existing = db.query(UploadItem).filter(UploadItem.batch_id == batch.id, UploadItem.client_id == client_id).one_or_none()
        if existing and existing.sha256 == sha256:
            return {"file_id": existing.file_id, "state": existing.state, "duplicate": existing.state == "duplicate", "client_id": client_id}
        raise HTTPException(409, "client_id was already used for different content")
    except OSError:
        db.rollback(); target.unlink(missing_ok=True)
        raise HTTPException(507, "insufficient storage")
    except Exception:
        db.rollback(); target.unlink(missing_ok=True)
        raise HTTPException(422, "upload failed validation")
    return {"file_id": record.id, "state": item.state, "duplicate": bool(duplicate), "client_id": client_id}


@router.get("/batches/{batch_id}")
def get_batch(request: Request, db: Db, batch_id: str, cursor: int | None = None, limit: int = 100, x_docuelevate_intake_secret: str | None = Header(default=None)):
    principal, _ = _principal(request, x_docuelevate_intake_secret)
    return _snapshot(db, _batch(db, batch_id, principal), cursor, limit)


@router.websocket("/events")
async def events(websocket: WebSocket):
    origin, host = websocket.headers.get("origin"), websocket.headers.get("host")
    scheme = websocket.headers.get("x-forwarded-proto", websocket.url.scheme)
    if not origin or not host or origin.rstrip("/") != f"{scheme}://{host}".rstrip("/"):
        await websocket.close(code=1008); return
    batch_id = websocket.query_params.get("batch_id")
    if not batch_id:
        await websocket.close(code=1008); return
    try:
        principal, _ = _principal(Request(websocket.scope))
    except HTTPException:
        await websocket.close(code=1008); return
    db = SessionLocal()
    try:
        batch = _batch(db, batch_id, principal)
        await websocket.accept()
        while True:
            ledger = _capacity(db)
            await websocket.send_json({"type": "capacity", "batch_id": batch_id, "slots": max(0, MAX_ACTIVE_FILES - ledger.reserved_files), "max_bytes": _capacity_limit(), "used_bytes": ledger.reserved_bytes, "retry_after": 5 if ledger.reserved_files >= MAX_ACTIVE_FILES else 0})
            await websocket.send_json({"type": "snapshot", **_snapshot(db, batch, None, 100)})
            await websocket.receive_text(); db.expire_all()
    except (WebSocketDisconnect, HTTPException):
        return
    finally:
        db.close()
