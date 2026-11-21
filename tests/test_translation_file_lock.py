"""Focused regression tests for per-file translation admission."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_sqlite_translation_lock_is_nonblocking_and_releases(tmp_path, monkeypatch):
    from app.services import translation_file_lock as module
    from app.services.translation_file_lock import TranslationFileBusy, translation_file_lock

    monkeypatch.setattr(module.settings, "workdir", str(tmp_path))
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    first, second = Session(), Session()
    with translation_file_lock(first, 987) as factory:
        assert factory() is not None
        with pytest.raises(TranslationFileBusy):
            with translation_file_lock(second, 987):
                pass
    with translation_file_lock(second, 987):
        pass
    first.close()
    second.close()


def test_checkpoint_rejects_mismatch_when_resuming():
    from app.models import FileRecord
    from app.tasks.translate_to_default_language import _checkpoint_for

    record = FileRecord(translation_checkpoint='{"fingerprint":"old","chunk_count":1,"translated_chunks":["x"]}')
    with pytest.raises(RuntimeError):
        _checkpoint_for(record, "new", ["text"], allow_reset=False)


@pytest.mark.parametrize("lost_attribute", ["closed", "invalidated"])
def test_postgres_lock_fences_sessions_to_original_connection(lost_attribute):
    from app.services import translation_file_lock as module

    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    connection = MagicMock(closed=False, invalidated=False)
    connection.execute.return_value.scalar.return_value = True
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    with patch.object(module, "_engine", return_value=engine), patch.object(module, "Session") as session:
        with module.translation_file_lock(db, 987) as factory:
            connection.commit.assert_called_once()  # No acquisition transaction survives admission.
            factory()
            session.assert_called_once_with(bind=connection)
            setattr(connection, lost_attribute, True)
            with pytest.raises(RuntimeError, match="no longer usable"):
                factory()
            session.assert_called_once()  # No checkpoint/final write can obtain another ORM session.
        engine.connect.assert_called_once()  # No reconnect can silently lose the advisory lock.
        connection.execute.assert_called_once()  # Do not attempt an unlock on a dead connection.


@pytest.mark.parametrize("checkpoint", [None, "bad-json", "{}", '{"fingerprint":"new"}'])
def test_erased_or_corrupt_checkpoint_cannot_be_reset_during_save(checkpoint):
    from app.models import FileRecord
    from app.tasks.translate_to_default_language import _checkpoint_for

    with pytest.raises(RuntimeError, match="checkpoint changed"):
        _checkpoint_for(FileRecord(translation_checkpoint=checkpoint), "new", ["text"], allow_reset=False)
