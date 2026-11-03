"""Contract tests for durable bulk-upload acceptance."""

from __future__ import annotations

import hashlib
import io
import shutil
import zipfile
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.api import bulk_upload
from app.config import settings
from app.models import FileProcessingStep, FileRecord, UploadBatch, UploadCapacity, UploadItem, UploadOutbox
from app.tasks import dispatch_uploads
from app.utils.bulk_upload import sniff_mime, stream_to_file
from app.utils.upload_health import DISPATCHER_KEY


@pytest.fixture(autouse=True)
def _ample_upload_disk(monkeypatch):
    """Keep ordinary upload contracts independent of the host filesystem."""
    monkeypatch.setattr(
        bulk_upload.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(total=10**12, used=10**9, free=999 * 10**9),
    )


def _batch(client, key: str = "queue-owner:batch") -> str:
    response = client.post("/api/uploads/batches", json={"client_batch_id": key, "total_files": 2, "total_bytes": 64})
    assert response.status_code == 201, response.text
    return response.json()["batch_id"]


def test_inspect_content_recovers_renamed_pdf_but_rejects_binary(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    monkeypatch.setattr(bulk_upload.shutil, "disk_usage", lambda _path: shutil._ntuple_diskusage(10**9, 1, 9 * 10**8))
    batch_id = _batch(client, "queue-owner:inspect-content")
    pdf = b"%PDF-1.7 renamed"
    fields = {
        "batch_id": batch_id,
        "client_id": "renamed",
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "inspect_content": "true",
    }
    response = client.post(
        "/api/uploads/files", data=fields, files={"file": ("renamed.docx", pdf, "application/octet-stream")}
    )
    assert response.status_code == 202, response.text
    assert list((tmp_path / "bulk_uploads" / batch_id).glob("*.pdf"))
    binary = b"not a document"
    rejected = client.post(
        "/api/uploads/files",
        data={**fields, "client_id": "binary", "sha256": hashlib.sha256(binary).hexdigest()},
        files={"file": ("binary.pdf", binary, "application/pdf")},
    )
    assert rejected.status_code == 415
    for client_id, name, content in (
        ("archive", "archive.pdf", b"PK\x03\x04not-a-document"),
        ("video", "video.pdf", b"\x00\x00\x00\x18ftypmp42not-a-document"),
    ):
        rejected = client.post(
            "/api/uploads/files",
            data={**fields, "client_id": client_id, "sha256": hashlib.sha256(content).hexdigest()},
            files={"file": (name, content, "application/pdf")},
        )
        assert rejected.status_code == 415, rejected.text
        assert len(list((tmp_path / "bulk_uploads" / batch_id).iterdir())) == 1
    assert db_session.query(UploadItem).count() == 1


def test_conversion_uses_detected_suffix_for_recovered_name():
    from app.tasks.convert_to_pdf import _build_filename

    assert _build_filename("/tmp/id.pdf", "renamed.docx", ".pdf") == "renamed.pdf"


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


def test_idempotent_replay_is_returned_even_after_capacity_is_exhausted(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:quota-replay")
    content = b"%PDF-1.4 replay"
    sha = hashlib.sha256(content).hexdigest()
    fields = {"batch_id": batch_id, "client_id": "replay", "sha256": sha}
    first = client.post("/api/uploads/files", data=fields, files={"file": ("replay.pdf", content, "application/pdf")})
    assert first.status_code == 202
    ledger = db_session.get(UploadCapacity, 1)
    ledger.reserved_files = 1000
    db_session.commit()
    replay = client.post("/api/uploads/files", data=fields, files={"file": ("replay.pdf", content, "application/pdf")})
    assert replay.status_code == 202
    assert replay.json()["file_id"] == first.json()["file_id"]


def test_legacy_reserved_file_counter_does_not_reject_new_upload(client, db_session, monkeypatch, tmp_path):
    """Ingest admission is byte/disk based, not coupled to processing counters."""
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:legacy-counter")
    ledger = UploadCapacity(id=1, reserved_files=0, reserved_bytes=0)
    db_session.add(ledger)
    db_session.flush()
    ledger.reserved_files = 1001
    ledger.reserved_bytes = 0
    db_session.commit()
    content = b"%PDF-1.4 counter-is-not-admission"
    response = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "counter", "sha256": hashlib.sha256(content).hexdigest()},
        files={"file": ("counter.pdf", content, "application/pdf")},
    )
    assert response.status_code == 202, response.text
    assert db_session.query(UploadOutbox).count() == 1


def test_disk_exhaustion_returns_retry_after_without_accepting_or_enqueueing(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:disk-full")
    monkeypatch.setattr(
        bulk_upload.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(total=1000, used=950, free=50),
    )
    content = b"%PDF-1.4 disk-full"
    response = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "disk-full", "sha256": hashlib.sha256(content).hexdigest()},
        files={"file": ("full.pdf", content, "application/pdf")},
    )
    assert response.status_code == 429
    assert response.headers.get("retry-after") == "30", response.text
    assert db_session.query(UploadItem).count() == 0
    assert db_session.query(UploadOutbox).count() == 0


def test_bulk_acceptance_is_not_subject_to_legacy_twenty_per_minute_limiter(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, "queue-owner:twenty-one")
    # If the old per-user dependency is accidentally reintroduced this test
    # must fail immediately, even though the bulk route is intentionally exempt.
    monkeypatch.setattr(
        "app.middleware.upload_rate_limit.require_upload_rate_limit",
        lambda *_args, **_kwargs: pytest.fail("legacy limiter invoked for bulk acceptance"),
    )
    for index in range(21):
        content = f"%PDF-1.4 bulk-{index}".encode()
        response = client.post(
            "/api/uploads/files",
            data={
                "batch_id": batch_id,
                "client_id": f"bulk-{index}",
                "sha256": hashlib.sha256(content).hexdigest(),
            },
            files={"file": (f"bulk-{index}.pdf", content, "application/pdf")},
        )
        assert response.status_code == 202, response.text
    assert db_session.query(UploadOutbox).count() == 21


def test_duplicate_acceptance_releases_its_reservation(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    monkeypatch.setattr(settings, "enable_deduplication", True)
    batch_id = _batch(client, "queue-owner:duplicate-release")
    content = b"%PDF-1.4 duplicate-release"
    sha = hashlib.sha256(content).hexdigest()
    first = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "first", "sha256": sha},
        files={"file": ("same.pdf", content, "application/pdf")},
    )
    assert first.status_code == 202
    reserved_after_first = db_session.get(UploadCapacity, 1).reserved_bytes
    duplicate = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "second", "sha256": sha},
        files={"file": ("same.pdf", content, "application/pdf")},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True
    assert db_session.get(UploadCapacity, 1).reserved_bytes == reserved_after_first
    assert db_session.query(UploadOutbox).count() == 1


def test_capacity_reports_multiple_ingest_slots(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    monkeypatch.setattr(
        bulk_upload.shutil,
        "disk_usage",
        lambda _path: shutil._ntuple_diskusage(total=100_000_000_000, used=10_000_000_000, free=90_000_000_000),
    )
    batch_id = _batch(client, "queue-owner:positive-capacity")
    response = client.get(f"/api/uploads/capacity?batch_id={batch_id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["slots"] > 1
    assert payload["max_bytes"] > 0


def test_capacity_reports_generic_control_plane_health(client, monkeypatch):
    batch_id = _batch(client, "queue-owner:health")
    monkeypatch.setattr(bulk_upload, "freshness", lambda _key: "unknown")

    payload = client.get(f"/api/uploads/capacity?batch_id={batch_id}").json()

    assert payload["processing"]["status"] == "unknown"
    assert {payload["processing"][key] for key in ("scheduler", "dispatcher", "reconciler")} == {"unknown"}

    monkeypatch.setattr(
        bulk_upload,
        "freshness",
        lambda key: "stalled" if key == DISPATCHER_KEY else "healthy",
    )
    payload = client.get(f"/api/uploads/capacity?batch_id={batch_id}").json()
    assert payload["processing"] == {
        "status": "stalled",
        "scheduler": "healthy",
        "dispatcher": "stalled",
        "reconciler": "healthy",
        "queued": 0,
        "processing": 0,
        "complete": 0,
        "failed": 0,
    }

    monkeypatch.setattr(
        bulk_upload,
        "freshness",
        lambda key: "unknown" if key == DISPATCHER_KEY else "healthy",
    )
    assert client.get(f"/api/uploads/capacity?batch_id={batch_id}").json()["processing"]["status"] == "unknown"


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


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected"),
    [
        ("generic.pdf", "application/octet-stream", b"%PDF-1.7 generic", "application/pdf"),
        ("missing.pdf", None, b"%PDF-1.7 missing", "application/pdf"),
        ("photo.jpg", "image/jpg", b"\xff\xd8\xff\xe0jpeg", "image/jpeg"),
        ("photo.png", "image/png", b"\x89PNG\r\n\x1a\nimage", "image/png"),
        ("photo.gif", "image/gif", b"GIF89aimage", "image/gif"),
    ],
)
def test_accepts_generic_or_aliased_mime_for_real_file_signatures(
    client, db_session, monkeypatch, tmp_path, filename, content_type, content, expected
):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, f"queue-owner:mime-{filename}")
    fields = {"batch_id": batch_id, "client_id": filename, "sha256": hashlib.sha256(content).hexdigest()}
    uploaded = client.post(
        "/api/uploads/files",
        data=fields,
        files={"file": (filename, content, content_type)},
    )
    assert uploaded.status_code == 202, uploaded.text
    assert uploaded.json()["file_id"]
    assert db_session.get(FileRecord, uploaded.json()["file_id"]).mime_type == expected
    assert client.get(f"/api/uploads/batches/{batch_id}").json()["items"][0]["state"] == "accepted"


def test_accepts_generic_mime_for_signed_docx(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    payload = content.getvalue()
    batch_id = _batch(client, "queue-owner:mime-docx")
    response = client.post(
        "/api/uploads/files",
        data={"batch_id": batch_id, "client_id": "docx", "sha256": hashlib.sha256(payload).hexdigest()},
        files={"file": ("report.docx", payload, "application/octet-stream")},
    )
    assert response.status_code == 202, response.text


@pytest.mark.parametrize(
    ("filename", "content", "expected_suffix"),
    [
        ("renamed.bin", b"%PDF-1.7 recovered", ".pdf"),
        ("missing-suffix", b"%PDF-1.7 recovered", ".pdf"),
        ("renamed.data", b"\xff\xd8\xff\xe0jpeg", ".jpg"),
        ("renamed.data", b"\x89PNG\r\n\x1a\nimage", ".png"),
        ("renamed.data", b"GIF89aimage", ".gif"),
    ],
)
def test_inspect_override_detects_signature_and_stores_detected_suffix(
    client, db_session, monkeypatch, tmp_path, filename, content, expected_suffix
):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, f"queue-owner:override-{expected_suffix}")
    response = client.post(
        "/api/uploads/files",
        data={
            "batch_id": batch_id,
            "client_id": f"override-{expected_suffix}",
            "sha256": hashlib.sha256(content).hexdigest(),
            "inspect_content": "true",
        },
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 202, response.text
    record = db_session.get(FileRecord, response.json()["file_id"])
    assert record.original_filename == filename
    assert record.local_filename.endswith(expected_suffix)
    assert len(list((tmp_path / "bulk_uploads" / batch_id).iterdir())) == 1


@pytest.mark.parametrize("failure", ["hash", "size", "capacity", "signature", "rename_sync"])
def test_content_override_preserves_guards_and_cleans_rejections(client, db_session, monkeypatch, tmp_path, failure):
    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    batch_id = _batch(client, f"queue-owner:override-guard-{failure}")
    content = b"%PDF-1.7 guarded"
    expected_status = 422
    if failure == "size":
        monkeypatch.setattr(settings, "max_upload_size", 4)
        expected_status = 413
    elif failure == "capacity":
        monkeypatch.setattr(bulk_upload.shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(100, 99, 1))
        expected_status = 429
    elif failure == "signature":
        content = b"\x89PNGtruncated"
        expected_status = 415
    elif failure == "rename_sync":
        expected_status = 507

        def fail_sync(_path):
            raise OSError("synthetic sync failure")

        monkeypatch.setattr(bulk_upload, "_sync_directory", fail_sync)
    response = client.post(
        "/api/uploads/files",
        data={
            "batch_id": batch_id,
            "client_id": failure,
            "sha256": "0" * 64 if failure == "hash" else hashlib.sha256(content).hexdigest(),
            "inspect_content": "true",
        },
        files={"file": ("renamed.bin", content, "video/quicktime")},
    )
    assert response.status_code == expected_status, response.text
    assert not list((tmp_path / "bulk_uploads" / batch_id).glob("*"))
    assert db_session.query(UploadItem).count() == 0
    assert db_session.query(UploadOutbox).count() == 0
    ledger = db_session.get(UploadCapacity, 1)
    assert ledger is None or ledger.reserved_bytes == 0


def test_ooxml_signature_and_generic_browser_mime_are_compatible(tmp_path):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    assert (
        sniff_mime("report.docx", "application/octet-stream", b"PK\x03\x04")
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert sniff_mime("report.docx", "application/octet-stream", b"not-zip") == "application/octet-stream"


def test_stream_to_file_is_atomic_and_rejects_bad_hash(tmp_path):
    from types import SimpleNamespace

    payload = b"durable bytes"
    target = tmp_path / "upload.pdf"
    size, digest = stream_to_file(
        SimpleNamespace(file=io.BytesIO(payload)), target, hashlib.sha256(payload).hexdigest(), 100
    )
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
    leased_outbox = UploadOutbox(
        item_id=leased_item.id,
        claim_token="live",
        claim_expires_at=now + timedelta(seconds=30),
    )
    db_session.add_all(
        (
            UploadOutbox(item_id=old_item.id),
            UploadOutbox(item_id=small_item.id),
            leased_outbox,
        )
    )
    db_session.commit()
    submitted = []
    marker = MagicMock()
    monkeypatch.setattr(dispatch_uploads, "SessionLocal", lambda: nullcontext(db_session))
    monkeypatch.setattr(dispatch_uploads.dispatch_upload_item, "delay", lambda *args: submitted.append(args))
    monkeypatch.setattr(dispatch_uploads, "mark_fresh", marker)
    assert dispatch_uploads.dispatch_upload_outbox.run(limit=2) == 2
    assert [entry[0] for entry in submitted] == [1, 2]
    marker.assert_called_once_with(DISPATCHER_KEY)

    # A failed submission must not certify the tick as healthy. The lease is
    # deliberately retriable after its expiry, so it may be claimed again.
    marker.reset_mock()
    leased_outbox.claim_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    monkeypatch.setattr(
        dispatch_uploads.dispatch_upload_item,
        "delay",
        lambda *_args: (_ for _ in ()).throw(ConnectionError("broker unavailable")),
    )
    with pytest.raises(ConnectionError, match="broker unavailable"):
        dispatch_uploads.dispatch_upload_outbox.run(limit=1)
    marker.assert_not_called()


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
    assert dispatch_uploads.reconcile_upload_states.run() == 0


def test_reconcile_releases_exhausted_failure_and_deleted_file(db_session, monkeypatch):
    batch = UploadBatch(id="failed", principal_id="p", client_batch_id="failed", total_files=2, total_bytes=20)
    record = FileRecord(filehash="f" * 64, local_filename="/tmp/f", file_size=10, mime_type="application/pdf")
    db_session.add_all((batch, record, UploadCapacity(id=1, reserved_files=2, reserved_bytes=20)))
    db_session.flush()
    failed = UploadItem(
        batch_id=batch.id,
        client_id="failed",
        principal_id="p",
        file_id=record.id,
        sha256="f" * 64,
        filename="f.pdf",
        size=10,
        state="failed",
        error="retries exhausted",
    )
    deleted = UploadItem(
        batch_id=batch.id,
        client_id="deleted",
        principal_id="p",
        file_id=None,
        sha256="d" * 64,
        filename="d.pdf",
        size=10,
        state="queued",
    )
    db_session.add_all((failed, deleted))
    db_session.commit()
    monkeypatch.setattr(dispatch_uploads, "SessionLocal", lambda: nullcontext(db_session))
    assert dispatch_uploads.reconcile_upload_states.run() == 2
    assert db_session.get(UploadCapacity, 1).reserved_files == 0
    assert failed.capacity_released is True and failed.state == "failed"
    assert deleted.capacity_released is True and deleted.state == "failed"


def test_websocket_capacity_uses_browser_origin_and_session_auth(client, db_session, monkeypatch):
    from app.api import bulk_upload

    closed = []

    class SessionProxy:
        def __init__(self):
            self._db = db_session

        def __getattr__(self, name):
            return getattr(self._db, name)

        def close(self):
            closed.append(True)

    monkeypatch.setattr(bulk_upload, "SessionLocal", SessionProxy)
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
    assert len(closed) >= 2


def test_batches_are_scoped_to_authenticated_principal(client, monkeypatch):
    from app.api import bulk_upload

    monkeypatch.setattr(bulk_upload, "_principal", lambda *args: ("alice", None))
    batch_id = _batch(client, "alice:private-batch")
    monkeypatch.setattr(bulk_upload, "_principal", lambda *args: ("bob", None))
    assert client.get(f"/api/uploads/batches/{batch_id}").status_code == 404
    assert client.get(f"/api/uploads/capacity?batch_id={batch_id}").status_code == 404
