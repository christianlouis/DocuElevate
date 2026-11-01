"""Contract tests for durable bulk-upload acceptance."""

from __future__ import annotations

import hashlib

from app.config import settings
from app.models import UploadItem, UploadOutbox


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
