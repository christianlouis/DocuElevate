"""Contract tests for durable bulk-upload acceptance."""

from __future__ import annotations

import hashlib
import io
import zipfile
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models import FileProcessingStep, FileRecord, UploadBatch, UploadCapacity, UploadItem, UploadOutbox
from app.tasks import dispatch_uploads
from app.utils.bulk_upload import sniff_mime, stream_to_file


def _batch(client, key: str = "queue-owner:batch") -> str:
    response = client.post("/api/uploads/batches", json={"client_batch_id": key, "total_files": 2, "total_bytes": 64})
    assert response.status_code == 201, response.text
    return response.json()["batch_id"]


def test_accept_is_durable_and_idempotent(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client)
    content = b"%PDF-1.4 durable bulk upload"
    sha = hashlib.sha256(content).hexdigest()
    fields = {"batch_id": batch_id, "client_id": "client-file-1", "sha256": sha}
    first = client.post("/api/uploads/files", data=fields, files={"file": ("invoice.pdf", content, "application/pdf")})
    assert first.status_code == 202, first.text
    assert db_session.query(UploadItem).count() == 1
    assert db_session.query(UploadOutbox).count() == 1
    record = db_session.query(UploadItem).one()
    assert record.file_id == first.json()["file_id"]
    assert list((tmp_path / "bulk_uploads" / batch_id).glob("*.pdf"))
    replay = client.post("/api/uploads/files", data=fields, files={"file": ("invoice.pdf", content, "application/pdf")})
    assert replay.status_code == 202
    assert replay.json()["file_id"] == first.json()["file_id"]
    conflict = client.post(
        "/api/uploads/files",
        data={**fields, "sha256": "0" * 64},
        files={"file": ("invoice.pdf", b"other", "application/pdf")},
    )
    assert conflict.status_code == 409


def test_preflight_and_snapshot_are_bounded(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:page")
    too_many = client.post("/api/uploads/preflight", json={"batch_id": batch_id, "files": [{}] * 201})
    assert too_many.status_code == 422
    bad = client.post(
        "/api/uploads/preflight", json={"batch_id": batch_id, "files": [{"client_id": "a", "sha256": "bad"}]}
    )
    assert bad.status_code == 200
    assert bad.json()["files"][0]["state"] == "invalid_hash"
    snapshot = client.get(f"/api/uploads/batches/{batch_id}?limit=999")
    assert snapshot.status_code == 200
    assert snapshot.json()["items"] == []
    assert snapshot.json()["aggregates"] == {}


def test_rejects_mime_mismatch_before_writing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:mime")
    content = b"not a PDF"
    response = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "x", "sha256": hashlib.sha256(content).hexdigest()},
        files={"file": ("bad.pdf", content, "application/pdf")},
    )
    assert response.status_code == 422


def test_ooxml_signature_and_generic_browser_mime_are_compatible(tmp_path):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    assert sniff_mime("report.docx", "application/octet-stream", b"PK\x03\x04") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert sniff_mime("report.docx", "application/octet-stream", b"not-zip") == "application/octet-stream"


def test_stream_to_file_is_atomic_and_rejects_bad_hash(tmp_path):
    from types import SimpleNamespace

    payload = b"durable bytes"
    target = tmp_path / "upload.pdf"
    size, digest = stream_to_file(SimpleNamespace(file=io.BytesIO(payload)), target, hashlib.sha256(payload).hexdigest(), 100)
    assert (size, digest) == (len(payload), hashlib.sha256(payload).hexdigest())
    assert target.read_bytes() == payload
    with pytest.raises(ValueError, match="sha256"):
        stream_to_file(SimpleNamespace(file=io.BytesIO(payload)), tmp_path / "bad.pdf", "0" * 64, 100)
    assert not (tmp_path / "bad.pdf").exists()


def test_dispatch_claims_aged_work_before_new_small_batch(db_session, monkeypatch):
    now = datetime.now(timezone.utc)
    old = UploadBatch(
        id="old",
        principal_id="p",
        client_batch_id="old",
        total_files=1000,
        total_bytes=1,
        created_at=now - timedelta(hours=1),
    )
    small = UploadBatch(
        id="small", principal_id="p", client_batch_id="small", total_files=1, total_bytes=1, created_at=now
    )
    db_session.add_all((old, small))
    db_session.flush()
    old_item = UploadItem(
        batch_id=old.id, client_id="old", principal_id="p", sha256="a" * 64, filename="old.pdf", size=1
    )
    small_item = UploadItem(
        batch_id=small.id, client_id="small", principal_id="p", sha256="b" * 64, filename="small.pdf", size=1
    )
    leased_item = UploadItem(
        batch_id=old.id, client_id="leased", principal_id="p", sha256="c" * 64, filename="leased.pdf", size=1
    )
    db_session.add_all((old_item, small_item, leased_item))
    db_session.flush()
    db_session.add_all(
        (
            UploadOutbox(item_id=old_item.id),
            UploadOutbox(item_id=small_item.id),
            UploadOutbox(item_id=leased_item.id, claim_token="live", claim_expires_at=now + timedelta(seconds=30)),
        )
    )
    db_session.commit()
    submitted = []
    monkeypatch.setattr(dispatch_uploads, "SessionLocal", lambda: nullcontext(db_session))
    monkeypatch.setattr(dispatch_uploads.dispatch_upload_item, "delay", lambda *args: submitted.append(args))
    assert dispatch_uploads.dispatch_upload_outbox.run(limit=2) == 2
    assert [entry[0] for entry in submitted] == [1, 2]


def test_broker_outage_releases_claim_for_bounded_recovery(db_session, monkeypatch):
    """A publish failure must leave durable work eligible for the next tick."""
    batch = UploadBatch(id="broker", principal_id="p", client_batch_id="broker", total_files=1, total_bytes=42)
    record = FileRecord(
        filehash="d" * 64,
        original_filename="a.pdf",
        local_filename="/tmp/a.pdf",
        file_size=42,
        mime_type="application/pdf",
    )
    db_session.add_all((batch, record))
    db_session.flush()
    item = UploadItem(
        batch_id=batch.id,
        client_id="broker",
        principal_id="p",
        file_id=record.id,
        sha256="d" * 64,
        filename="a.pdf",
        size=42,
    )
    db_session.add(item)
    db_session.flush()
    outbox = UploadOutbox(
        item_id=item.id,
        claim_token="claimed",
        claim_expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )
    db_session.add(outbox)
    db_session.commit()

    monkeypatch.setattr(dispatch_uploads, "SessionLocal", lambda: nullcontext(db_session))
    monkeypatch.setattr(
        dispatch_uploads.process_document,
        "apply_async",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("broker unavailable")),
    )
    with pytest.raises(ConnectionError, match="broker unavailable"):
        dispatch_uploads.dispatch_upload_item.run(outbox.id, "claimed")

    db_session.refresh(outbox)
    assert outbox.dispatched_at is None
    assert outbox.claim_token is None
    assert outbox.claim_expires_at is None
    assert "broker unavailable" in outbox.last_error

    submitted = []
    monkeypatch.setattr(dispatch_uploads.dispatch_upload_item, "delay", lambda *args: submitted.append(args))
    assert dispatch_uploads.dispatch_upload_outbox.run(limit=1) == 1
    assert submitted[0][0] == outbox.id


def test_reconcile_uses_terminal_step_and_atomic_ledger_decrement(db_session, monkeypatch):
    batch = UploadBatch(id="terminal", principal_id="p", client_batch_id="terminal", total_files=1, total_bytes=42)
    record = FileRecord(
        filehash="c" * 64,
        original_filename="a.pdf",
        local_filename="/tmp/a.pdf",
        processed_file_path="/tmp/processed.pdf",
        file_size=42,
        mime_type="application/pdf",
    )
    db_session.add_all((batch, record, UploadCapacity(id=1, reserved_files=1, reserved_bytes=42)))
    db_session.flush()
    item = UploadItem(
        batch_id=batch.id,
        client_id="terminal",
        principal_id="p",
        file_id=record.id,
        sha256="c" * 64,
        filename="a.pdf",
        size=42,
        state="queued",
    )
    db_session.add(item)
    db_session.commit()
    monkeypatch.setattr(dispatch_uploads, "SessionLocal", lambda: nullcontext(db_session))
    # Metadata embedding persists the file before destination dispatch; that
    # alone must not release global admission capacity.
    assert dispatch_uploads.reconcile_upload_states.run() == 0
    db_session.add(FileProcessingStep(file_id=record.id, step_name="send_to_all_destinations", status="success"))
    db_session.commit()
    assert dispatch_uploads.reconcile_upload_states.run() == 1
    db_session.refresh(item)
    ledger = db_session.get(UploadCapacity, 1)
    assert item.state == "complete"
    assert (ledger.reserved_files, ledger.reserved_bytes) == (0, 0)


def test_websocket_capacity_uses_browser_origin_and_session_auth(client, db_session, monkeypatch):
    from app.api import bulk_upload

    monkeypatch.setattr(bulk_upload, "SessionLocal", lambda: db_session)
    batch_id = _batch(client, "queue-owner:websocket")
    with client.websocket_connect(
        f"ws://localhost/api/uploads/events?batch_id={batch_id}", headers={"origin": "http://localhost"}
    ) as socket:
        capacity = socket.receive_json()
        assert capacity["type"] == "capacity"
        assert capacity["slots"] > 0
        assert socket.receive_json()["type"] == "snapshot"
        socket.send_text("capacity")
        assert socket.receive_json()["type"] == "capacity"


def test_batches_are_scoped_to_authenticated_principal(client, monkeypatch):
    from app.api import bulk_upload

    monkeypatch.setattr(bulk_upload, "_principal", lambda *args: ("alice", None))
    batch_id = _batch(client, "alice:private-batch")
    monkeypatch.setattr(bulk_upload, "_principal", lambda *args: ("bob", None))
    assert client.get(f"/api/uploads/batches/{batch_id}").status_code == 404
    assert client.get(f"/api/uploads/capacity?batch_id={batch_id}").status_code == 404
