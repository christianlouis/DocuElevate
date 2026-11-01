"""Account deletion fences background writers that can recreate derived data."""

from contextlib import contextmanager, nullcontext
from unittest.mock import MagicMock

from app.models import AccountDeletionTombstone, FileRecord
from app.services.account_deletion import tombstone_key


def _file(db):
    record = FileRecord(owner_id="alice", filehash="hash", local_filename="document.pdf", file_size=1, ocr_text="text")
    db.add(record)
    db.commit()
    return record


def test_tombstone_blocks_background_writers(db_session, monkeypatch, tmp_path):
    import app.tasks.batch_tasks as batch
    import app.tasks.dropbox_corpus_import as dropbox
    import app.tasks.reconcile_file_privacy as privacy
    import app.tasks.refine_text_with_gpt as refine
    from app.config import settings

    monkeypatch.setattr(settings, "workdir", str(tmp_path))
    record = _file(db_session)
    db_session.add(AccountDeletionTombstone(owner_id=tombstone_key("alice"), status="deleting"))
    db_session.commit()
    for module in (batch, dropbox, privacy, refine):
        monkeypatch.setattr(module, "SessionLocal", lambda: nullcontext(db_session))
    callback = MagicMock()
    provider = MagicMock()
    index = MagicMock()
    monkeypatch.setattr(refine, "get_ai_provider", provider)
    monkeypatch.setattr(privacy, "_reconcile", index)

    with batch._current_file(record) as current:
        assert current is None
    assert dropbox._guard_owner_work(FileRecord, record.id, callback)["status"] == "skipped"
    assert privacy.reconcile_file_privacy.run(record.id)["status"] == "skipped"
    assert refine.refine_text_with_gpt.run(record.local_filename, "text", file_id=record.id)["status"] == "skipped"
    callback.assert_not_called()
    provider.assert_not_called()
    index.assert_not_called()


def test_privacy_rereads_after_acquiring_lock(db_session, monkeypatch):
    import app.tasks.reconcile_file_privacy as privacy

    record = _file(db_session)
    file_id = record.id
    monkeypatch.setattr(privacy, "SessionLocal", lambda: nullcontext(db_session))
    index = MagicMock()
    monkeypatch.setattr(privacy, "_reconcile", index)

    @contextmanager
    def deletion_before_lock(db, owner, exclusive=False):
        db.delete(record)
        db.commit()
        yield

    monkeypatch.setattr(privacy, "account_lifecycle_lock", deletion_before_lock)
    assert privacy.reconcile_file_privacy.run(file_id)["status"] == "skipped"
    index.assert_not_called()


def test_search_sync_does_not_recreate_file_deleted_before_lock(db_session, monkeypatch):
    import app.tasks.batch_tasks as batch
    import app.utils.meilisearch_client as search

    record = _file(db_session)
    monkeypatch.setattr(batch, "SessionLocal", lambda: nullcontext(db_session))
    monkeypatch.setattr(batch, "_update_job_status", MagicMock())
    client = MagicMock()
    client.get_index.return_value.get_documents.return_value.results = []
    monkeypatch.setattr(search, "get_meilisearch_client", lambda: client)
    index = MagicMock()
    monkeypatch.setattr(search, "index_documents", index)

    @contextmanager
    def deletion_before_lock(db, owner, exclusive=False):
        db.delete(record)
        db.commit()
        yield

    monkeypatch.setattr(batch, "account_lifecycle_lock", deletion_before_lock)
    result = batch.sync_search_index.run(batch_size=10)
    assert result["indexed"] == 0
    assert result["skipped"] == 1
    index.assert_not_called()
