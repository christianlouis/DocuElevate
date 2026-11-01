"""Focused lifecycle tests independent of the application's large fixture."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AccountDeletionTombstone, FileRecord, Tenant, Tribe
from app.services.account_deletion import DeletionBlocked, delete_account, assert_account_active


@pytest.fixture()
def deletion_db(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
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


def test_null_owner_shared_path_is_preserved(deletion_db, monkeypatch):
    db, root = deletion_db
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    path = root / "shared-null.pdf"
    path.write_bytes(b"x")
    db.add_all([_file("alice", path), _file(None, path)])
    # Distinct hashes; unowned records still protect their content.
    for row in db.new:
        if isinstance(row, FileRecord) and row.owner_id is None:
            row.filehash = "unowned"
    db.commit()
    delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert path.exists()
    assert db.query(FileRecord).filter(FileRecord.owner_id.is_(None)).count() == 1


def test_crashed_deleting_state_can_resume(deletion_db, monkeypatch):
    import json
    db, root = deletion_db
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    path = root / "resume.pdf"
    path.write_bytes(b"x")
    file = _file("alice", path)
    db.add(file)
    db.flush()
    db.add(AccountDeletionTombstone(owner_id="alice", status="deleting", cleanup_manifest=json.dumps({"file_ids": [file.id], "paths": [str(path)]})))
    db.commit()
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
    assert not path.exists()


def test_indirect_children_are_removed(deletion_db, monkeypatch):
    from app.models import Pipeline, PipelineStep, PipelineVersion, UserIntegration, DropboxImportObject
    db, root = deletion_db
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    pipeline = Pipeline(owner_id="alice", name="owned")
    integration = UserIntegration(owner_id="alice", name="dropbox", direction="SOURCE", integration_type="DROPBOX")
    db.add_all([pipeline, integration])
    db.flush()
    db.add_all([PipelineStep(pipeline_id=pipeline.id, position=1, step_type="ocr"),
                PipelineVersion(pipeline_id=pipeline.id, version=1, snapshot="{}"),
                DropboxImportObject(integration_id=integration.id, dropbox_file_id="abc", revision="1", remote_path="/a")])
    db.commit()
    delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert db.query(PipelineStep).count() == db.query(PipelineVersion).count() == 0
    assert db.query(DropboxImportObject).count() == 0


def test_subject_is_fenced_but_retry_route_remains_accessible(deletion_db, monkeypatch):
    from types import SimpleNamespace
    import app.database
    from app.auth import get_current_user
    from app.config import settings
    from app.utils.user_scope import get_current_owner_id
    db, root = deletion_db
    db.add(AccountDeletionTombstone(owner_id="subject-1", status="failed"))
    db.commit()
    monkeypatch.setattr(app.database, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())())
    monkeypatch.setattr(settings, "auth_enabled", False)
    user = {"sub": "subject-1", "preferred_username": "alice"}
    request = SimpleNamespace(url=SimpleNamespace(path="/api/files"), method="GET", session={"user": user}, state=SimpleNamespace(), headers={})
    assert get_current_user(request) is None
    assert request.session["user"] == user
    request.url.path = "/api/account"
    assert get_current_owner_id(request) == "subject-1"


def test_bearer_fence_allows_only_retry_route(deletion_db):
    from types import SimpleNamespace
    from app.api.api_tokens import hash_token
    from app.auth import _resolve_bearer_user
    from app.models import ApiToken
    db, _ = deletion_db
    db.add_all([AccountDeletionTombstone(owner_id="alice", status="failed"),
                ApiToken(owner_id="alice", name="phone", token_hash=hash_token("secret"), token_prefix="secret")])
    db.commit()
    request = SimpleNamespace(url=SimpleNamespace(path="/api/files"), method="GET", headers={"authorization": "Bearer secret"}, client=None)
    assert _resolve_bearer_user(request, db) is None
    request.url.path = "/api/account"
    assert _resolve_bearer_user(request, db)["id"] == "alice"


def test_disabled_indexes_do_not_block(deletion_db, monkeypatch):
    from app.config import settings
    db, root = deletion_db
    monkeypatch.setattr(settings, "enable_search", False)
    monkeypatch.setattr(settings, "vector_index_enabled", False)
    path = root / "file.pdf"
    path.write_bytes(b"x")
    db.add(_file("alice", path))
    db.commit()
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
    assert not path.exists()


def test_database_cleanup_failure_is_retryable(deletion_db, monkeypatch):
    from app.services.account_deletion import AccountDeletionError
    db, root = deletion_db
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    path = root / "retry.pdf"
    path.write_bytes(b"x")
    db.add(_file("alice", path))
    db.commit()
    import app.services.account_deletion as service
    original = service._delete_mapped_owner_rows
    def fail(*args):
        raise RuntimeError("database failure")
    monkeypatch.setattr(service, "_delete_mapped_owner_rows", fail)
    with pytest.raises(AccountDeletionError):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert db.query(AccountDeletionTombstone).filter_by(owner_id="alice").one().status == "failed"
    assert db.query(FileRecord).filter_by(owner_id="alice").count() == 1
    monkeypatch.setattr(service, "_delete_mapped_owner_rows", original)
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
