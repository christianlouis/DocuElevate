"""Crash and duplicate-delivery coverage for the IMAP consumer handoff."""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import DocumentIntake, FileRecord
from app.tasks import imap_intake


@pytest.fixture
def intake_env(db_session, tmp_path):
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    with (
        patch.object(imap_intake, "SessionLocal", factory),
        patch.object(imap_intake.settings, "workdir", str(tmp_path)),
        patch.object(imap_intake.settings, "default_owner_id", None),
        patch.object(imap_intake.process_imap_intake, "delay") as publish,
        patch.object(imap_intake, "ensure_document_scope", return_value=("default", "quarantine")),
        patch.object(imap_intake, "_trusted_source_integration_id", return_value=None),
    ):
        yield factory, publish


def _prepare(key="message-1"):
    return imap_intake.prepare_imap_attachment(
        owner_id="owner-a",
        source_integration_id=None,
        idempotency_key=key,
        filename="scan.pdf",
        payload=b"%PDF test",
        mime_type="application/pdf",
        is_pdf=True,
    )


@pytest.mark.unit
def test_repeated_delivery_and_failed_stage_reuse_one_record(intake_env):
    factory, publish = intake_env
    intake_id = _prepare()
    assert _prepare() == intake_id
    assert publish.call_count == 1
    with patch.object(imap_intake.process_document, "apply", side_effect=RuntimeError("handoff interrupted")):
        with pytest.raises(RuntimeError):
            imap_intake.process_imap_intake.run(intake_id)
    with factory() as db:
        assert db.query(FileRecord).count() == 1
        assert db.query(DocumentIntake).filter_by(id=intake_id).one().state == "failed"
    successful = MagicMock()
    successful.result = {"status": "Queued for OCR"}
    with patch.object(imap_intake.process_document, "apply", return_value=successful) as run:
        result = imap_intake.process_imap_intake.run(intake_id)
        assert imap_intake.process_imap_intake.run(intake_id)["status"] == "already_completed"
        assert run.call_count == 1
        assert run.call_args.kwargs["kwargs"]["file_id"] == result["file_id"]
    with factory() as db:
        assert db.query(FileRecord).count() == 1


@pytest.mark.unit
def test_reconciliation_republishes_expired_claim_only(intake_env):
    factory, publish = intake_env
    intake_id = _prepare()
    with factory() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).one()
        row.state = "processing"
        row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=imap_intake.CLAIM_SECONDS + 1)
        db.commit()
    publish.reset_mock()
    assert imap_intake.reconcile_imap_intakes() == 1
    publish.assert_called_once_with(intake_id)


@pytest.mark.unit
def test_existing_file_is_matched_within_owner(intake_env):
    factory, _ = intake_env
    intake_id = _prepare()
    import hashlib

    with factory() as db:
        db.add(
            FileRecord(
                owner_id="other",
                filehash=hashlib.sha256(b"%PDF test").hexdigest(),
                original_filename="old.pdf",
                local_filename="/tmp/old",
                file_size=9,
            )
        )
        db.commit()
    successful = MagicMock()
    successful.result = {"status": "Queued for OCR"}
    with patch.object(imap_intake.process_document, "apply", return_value=successful):
        imap_intake.process_imap_intake.run(intake_id)
    with factory() as db:
        assert db.query(FileRecord).count() == 2


@pytest.mark.unit
def test_existing_owner_file_skips_pipeline(intake_env):
    factory, _ = intake_env
    intake_id = _prepare()
    import hashlib

    with factory() as db:
        db.add(
            FileRecord(
                owner_id="owner-a",
                filehash=hashlib.sha256(b"%PDF test").hexdigest(),
                original_filename="old.pdf",
                local_filename="/tmp/old",
                file_size=9,
            )
        )
        db.commit()
    with patch.object(imap_intake.process_document, "apply") as run:
        assert imap_intake.process_imap_intake.run(intake_id)["status"] == "existing"
        run.assert_not_called()
    with factory() as db:
        assert db.query(FileRecord).count() == 1


@pytest.mark.unit
def test_fresh_processing_claim_blocks_second_consumer(intake_env):
    factory, _ = intake_env
    intake_id = _prepare()
    with factory() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).one()
        row.state, row.updated_at = "processing", datetime.now(timezone.utc)
        db.commit()
    with patch.object(imap_intake.process_document, "apply") as run:
        assert imap_intake.process_imap_intake.run(intake_id)["status"] == "already_processing"
        run.assert_not_called()
    with factory() as db:
        assert db.query(FileRecord).count() == 0


@pytest.mark.unit
def test_failed_publish_returns_to_pending_and_recovers(intake_env):
    factory, publish = intake_env
    publish.side_effect = RuntimeError("broker unavailable")
    with pytest.raises(RuntimeError):
        _prepare()
    with factory() as db:
        row = db.query(DocumentIntake).one()
        assert row.state == "pending"
        assert row.local_path and os.path.isfile(row.local_path)
        intake_id = row.id
    publish.side_effect = None
    assert imap_intake.reconcile_imap_intakes() == 1
    assert publish.call_args.args == (intake_id,)
    with factory() as db:
        assert db.query(DocumentIntake).one().state == "dispatched"


@pytest.mark.unit
def test_ambiguous_published_message_is_republished_after_lease(intake_env):
    factory, publish = intake_env
    intake_id = _prepare()
    with factory() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).one()
        row.updated_at = datetime.now(timezone.utc) - timedelta(seconds=imap_intake.CLAIM_SECONDS + 1)
        db.commit()
    publish.reset_mock()
    assert imap_intake.reconcile_imap_intakes() == 1
    publish.assert_called_once_with(intake_id)


@pytest.mark.unit
def test_existing_owner_hash_is_seeded_before_publish(intake_env):
    factory, publish = intake_env
    import hashlib

    with factory() as db:
        existing = FileRecord(
            owner_id="owner-a",
            filehash=hashlib.sha256(b"%PDF test").hexdigest(),
            original_filename="old.pdf",
            local_filename="/tmp/old",
            file_size=9,
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id
    with patch.object(imap_intake, "_stage_payload") as stage:
        intake_id = _prepare()
        assert _prepare() == intake_id
    stage.assert_not_called()
    publish.assert_not_called()
    with factory() as db:
        import json

        row = db.query(DocumentIntake).filter_by(id=intake_id).one()
        assert row.state == "completed"
        assert json.loads(row.metadata_json)["file_id"] == existing_id


@pytest.mark.unit
def test_real_eager_celery_consumer_can_invoke_pipeline_task(intake_env):
    intake_id = _prepare()
    with patch.object(imap_intake.process_document, "run", return_value={"status": "Queued for OCR"}) as run:
        outcome = imap_intake.process_imap_intake.apply(args=[intake_id], throw=True).result
    assert outcome["status"] == "completed"
    assert run.call_args.kwargs["file_id"] == outcome["file_id"]


@pytest.mark.unit
def test_deduplication_disabled_keeps_distinct_uid_intakes_as_records(intake_env):
    factory, _ = intake_env
    with patch.object(imap_intake.settings, "enable_deduplication", False):
        first = _prepare("uid-101")
        second = _prepare("uid-102")
        assert _prepare("uid-101") == first
        with factory() as db:
            rows = db.query(FileRecord).order_by(FileRecord.id).all()
            assert len(rows) == 0
        successful = MagicMock()
        successful.result = {"status": "Queued for OCR"}
        with patch.object(imap_intake.process_document, "apply", return_value=successful):
            assert imap_intake.process_imap_intake.run(first)["status"] == "completed"
            assert imap_intake.process_imap_intake.run(second)["status"] == "completed"
        with factory() as db:
            assert db.query(FileRecord).count() == 2


@pytest.mark.unit
def test_original_filename_is_basename_and_existing_stage_is_reused(intake_env):
    factory, _ = intake_env
    intake_id = imap_intake.prepare_imap_attachment(
        owner_id="owner-a", source_integration_id=None, idempotency_key="uid-103",
        filename=r"C:\\incoming/..\\scan.pdf", payload=b"%PDF test",
        mime_type="application/pdf", is_pdf=True,
    )
    with factory() as db:
        row = db.query(DocumentIntake).filter_by(id=intake_id).one()
        assert row.original_filename == "scan.pdf"
        staged = row.local_path
    assert imap_intake.prepare_imap_attachment(
        owner_id="owner-a", source_integration_id=None, idempotency_key="uid-103",
        filename="different-name.pdf", payload=b"%PDF test",
        mime_type="application/pdf", is_pdf=True,
    ) == intake_id
    assert staged.endswith(".pdf")


@pytest.mark.unit
@pytest.mark.parametrize("filename", (".", "..", r"C:\\incoming\\.."))
def test_dot_filenames_use_safe_attachment_basename(intake_env, filename):
    factory, _ = intake_env
    intake_id = imap_intake.prepare_imap_attachment(
        owner_id="owner-a", source_integration_id=None, idempotency_key=f"dot-{filename}",
        filename=filename, payload=b"%PDF test", mime_type="application/pdf", is_pdf=True,
    )
    with factory() as db:
        assert db.query(DocumentIntake).filter_by(id=intake_id).one().original_filename == "attachment"


@pytest.mark.unit
def test_inactive_owner_is_rejected_before_staging(intake_env):
    with patch.object(imap_intake, "assert_account_active", side_effect=ValueError("deleted")):
        with pytest.raises(ValueError, match="deleted"):
            _prepare("uid-deleted")
    assert not os.path.exists(os.path.join(imap_intake.settings.workdir, "imap-staging"))


@pytest.mark.unit
def test_same_intake_key_rejects_different_payload_without_new_stage(intake_env):
    factory, _ = intake_env
    intake_id = _prepare("uid-conflict")
    with pytest.raises(ValueError, match="different attachment content"):
        imap_intake.prepare_imap_attachment(
            owner_id="owner-a", source_integration_id=None, idempotency_key="uid-conflict",
            filename="replacement.pdf", payload=b"not the first payload",
            mime_type="application/pdf", is_pdf=True,
        )
    with factory() as db:
        assert db.query(DocumentIntake).count() == 1
        assert db.query(DocumentIntake).one().id == intake_id


@pytest.mark.unit
def test_distinct_reservations_use_isolated_staged_paths(intake_env):
    factory, _ = intake_env
    _prepare("uid-isolated-1")
    _prepare("uid-isolated-2")
    with factory() as db:
        paths = [row.local_path for row in db.query(DocumentIntake).order_by(DocumentIntake.id)]
    assert len(paths) == 2
    assert len(set(paths)) == 2
    assert all(os.path.isfile(path) for path in paths)


@pytest.mark.unit
def test_reservation_failure_removes_only_unreserved_stage(intake_env):
    factory, _ = intake_env
    owned_id = _prepare("uid-owned-stage")
    with factory() as db:
        owned_path = db.query(DocumentIntake).filter_by(id=owned_id).one().local_path

    def failing_session():
        session = factory()

        def fail_commit():
            raise RuntimeError("reservation commit failed")

        session.commit = fail_commit
        return session

    with patch.object(imap_intake, "SessionLocal", failing_session):
        with pytest.raises(RuntimeError, match="reservation commit failed"):
            _prepare("uid-commit-failure")
    staging = os.path.join(imap_intake.settings.workdir, "imap-staging")
    assert os.path.isdir(staging)
    assert os.path.isfile(owned_path)
    assert os.listdir(staging) == [os.path.basename(owned_path)]


@pytest.mark.unit
def test_consumer_reservation_holds_owner_lifecycle_lock(intake_env):
    intake_id = _prepare("uid-consumer-fence")
    successful = MagicMock()
    successful.result = {"status": "Queued for OCR"}
    lock = MagicMock(return_value=imap_intake.nullcontext())
    with (
        patch.object(imap_intake, "account_lifecycle_lock", lock),
        patch.object(imap_intake.process_document, "apply", return_value=successful),
    ):
        assert imap_intake.process_imap_intake.run(intake_id)["status"] == "completed"
    lock.assert_called_once_with(ANY, "owner-a", exclusive=False)
