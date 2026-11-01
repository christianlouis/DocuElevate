"""Focused lifecycle tests independent of the application's large fixture."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AccountDeletionTombstone, FileRecord, Tenant, Tribe
from app.services.account_deletion import DeletionBlocked, delete_account, assert_account_active


@pytest.fixture()
def deletion_db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Tenant(id="default", name="test"))
    db.add(Tribe(id="default-quarantine", tenant_id="default", name="quarantine"))
    db.commit()
    yield db, tmp_path
    db.close()


def _file(owner, path):
    return FileRecord(owner_id=owner, filehash=owner, local_filename=str(path), file_size=1, tenant_id="default", tribe_id="default-quarantine")


def test_deletion_preserves_other_owner_shared_path_and_fences(deletion_db, monkeypatch):
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    db, root = deletion_db
    shared = root / "shared.pdf"
    shared.write_bytes(b"x")
    db.add_all([_file("alice", shared), _file("bob", shared)])
    db.commit()

    result = delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)

    assert result["status"] == "deleted"
    assert shared.exists()
    assert db.query(FileRecord).filter(FileRecord.owner_id == "bob").count() == 1
    with pytest.raises(DeletionBlocked):
        assert_account_active(db, "alice")


def test_legal_hold_fails_closed_before_mutation(deletion_db):
    db, root = deletion_db
    path = root / "held.pdf"
    path.write_bytes(b"x")
    file = _file("alice", path)
    file.legal_hold = True
    db.add(file)
    db.commit()

    with pytest.raises(DeletionBlocked):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert path.exists()
    assert db.query(FileRecord).count() == 1


def test_external_failure_keeps_manifest_and_can_retry(deletion_db, monkeypatch):
    db, root = deletion_db
    path = root / "document.pdf"
    path.write_bytes(b"x")
    db.add(_file("alice", path))
    db.commit()
    def fail(owner, ids):
        raise RuntimeError("offline")
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", fail)
    from app.services.account_deletion import AccountDeletionError
    with pytest.raises(AccountDeletionError):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    row = db.query(AccountDeletionTombstone).filter_by(owner_id="alice").one()
    assert row.status == "failed" and 'file_ids' in row.cleanup_manifest
    assert path.exists()
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
    assert not path.exists()


def test_legal_hold_does_not_fence_account(deletion_db):
    db, root = deletion_db
    file = _file("alice", root / "held.pdf")
    file.legal_hold = True
    db.add(file)
    db.commit()
    with pytest.raises(DeletionBlocked):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert db.query(AccountDeletionTombstone).count() == 0
