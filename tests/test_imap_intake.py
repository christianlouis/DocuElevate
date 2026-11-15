"""Crash and duplicate-delivery coverage for the IMAP consumer handoff."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    intake_id = _prepare()
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
