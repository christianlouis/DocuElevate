"""Focused lifecycle tests independent of the application's large fixture."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AccountDeletionTombstone, FileRecord, Tenant, Tribe
from app.services.account_deletion import DeletionBlocked, assert_account_active, delete_account, tombstone_key


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
    return FileRecord(
        owner_id=owner,
        filehash=owner,
        local_filename=str(path),
        file_size=1,
        tenant_id="default",
        tribe_id="default-quarantine",
    )


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
    row = db.query(AccountDeletionTombstone).filter_by(owner_id=tombstone_key("alice")).one()
    assert row.status == "failed" and "file_ids" in row.cleanup_manifest
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
    db.add(
        AccountDeletionTombstone(
            owner_id=tombstone_key("alice"),
            status="deleting",
            cleanup_manifest=json.dumps({"file_ids": [file.id], "paths": [str(path)]}),
        )
    )
    db.commit()
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
    assert not path.exists()


def test_indirect_children_are_removed(deletion_db, monkeypatch):
    from app.models import DropboxImportObject, Pipeline, PipelineStep, PipelineVersion, UserIntegration

    db, root = deletion_db
    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda owner, ids: None)
    pipeline = Pipeline(owner_id="alice", name="owned")
    integration = UserIntegration(owner_id="alice", name="dropbox", direction="SOURCE", integration_type="DROPBOX")
    db.add_all([pipeline, integration])
    db.flush()
    db.add_all(
        [
            PipelineStep(pipeline_id=pipeline.id, position=1, step_type="ocr"),
            PipelineVersion(pipeline_id=pipeline.id, version=1, snapshot="{}"),
            DropboxImportObject(integration_id=integration.id, dropbox_file_id="abc", revision="1", remote_path="/a"),
        ]
    )
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
    db.add(AccountDeletionTombstone(owner_id=tombstone_key("subject-1"), status="failed"))
    db.commit()
    monkeypatch.setattr(app.database, "SessionLocal", sessionmaker(bind=db.get_bind()))
    monkeypatch.setattr(settings, "auth_enabled", False)
    user = {"sub": "subject-1", "preferred_username": "alice"}
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/files"),
        method="GET",
        session={"user": user},
        state=SimpleNamespace(),
        headers={},
    )
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
    db.add_all(
        [
            AccountDeletionTombstone(owner_id=tombstone_key("alice"), status="failed"),
            ApiToken(owner_id="alice", name="phone", token_hash=hash_token("secret"), token_prefix="secret"),
        ]
    )
    db.commit()
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/files"), method="GET", headers={"authorization": "Bearer secret"}, client=None
    )
    assert _resolve_bearer_user(request, db) is None
    request.url.path = "/api/account"
    assert _resolve_bearer_user(request, db)["id"] == "alice"


def test_configured_indexes_are_cleaned_even_when_disabled(deletion_db, monkeypatch):
    from unittest.mock import MagicMock

    import meilisearch

    from app.config import settings
    from app.utils.vector_index import QdrantVectorIndex

    db, root = deletion_db
    monkeypatch.setattr(settings, "enable_search", False)
    monkeypatch.setattr(settings, "vector_index_enabled", False)
    client = MagicMock()
    client.wait_for_task.return_value.status = "succeeded"
    monkeypatch.setattr(meilisearch, "Client", lambda **kwargs: client)
    vector_delete = MagicMock()
    monkeypatch.setattr(QdrantVectorIndex, "delete_documents", vector_delete)
    path = root / "file.pdf"
    path.write_bytes(b"x")
    db.add(_file("alice", path))
    db.commit()
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"
    client.get_index.return_value.delete_document.assert_called_once()
    vector_delete.assert_called_once()
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
    assert db.query(AccountDeletionTombstone).filter_by(owner_id=tombstone_key("alice")).one().status == "failed"
    assert db.query(FileRecord).filter_by(owner_id="alice").count() == 1
    monkeypatch.setattr(service, "_delete_mapped_owner_rows", original)
    assert delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)["status"] == "deleted"


def test_other_owner_references_and_local_username_are_preserved(deletion_db, monkeypatch):
    from app.models import DocumentComment, LocalUser, Pipeline, PipelineRoutingRule

    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda *args: None)
    db, root = deletion_db
    alice = _file("alice", root / "alice.pdf")
    bob = _file("bob", root / "bob.pdf")
    pipeline = Pipeline(owner_id="alice", name="private")
    db.add_all([alice, bob, pipeline, LocalUser(email="bob@example.com", username="alice", hashed_password="x")])
    db.flush()
    rule = PipelineRoutingRule(
        owner_id="alice", name="r", field="filename", operator="equals", value="x", target_pipeline_id=pipeline.id
    )
    db.add(rule)
    db.flush()
    bob.duplicate_of_id, bob.pipeline_id, bob.pipeline_routing_rule_id = alice.id, pipeline.id, rule.id
    comment = DocumentComment(file_id=bob.id, user_id="alice", body="hello")
    db.add(comment)
    db.flush()
    reply = DocumentComment(file_id=bob.id, user_id="bob", body="reply", parent_id=comment.id)
    db.add(reply)
    db.commit()
    bob_id, reply_id = bob.id, reply.id
    delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    db.expire_all()
    survivor = db.get(FileRecord, bob_id)
    assert (survivor.duplicate_of_id, survivor.pipeline_id, survivor.pipeline_routing_rule_id) == (None, None, None)
    assert db.get(DocumentComment, reply_id).parent_id is None
    assert db.query(LocalUser).filter_by(email="bob@example.com").count() == 1
    assert db.query(AccountDeletionTombstone).one().owner_id == tombstone_key("alice")


def test_other_owner_intake_protects_shared_path(deletion_db, monkeypatch):
    from app.models import DocumentIntake

    monkeypatch.setattr("app.services.account_deletion._delete_external_indexes", lambda *args: None)
    db, root = deletion_db
    path = root / "shared.pdf"
    path.write_bytes(b"data")
    db.add_all(
        [
            _file("alice", path),
            DocumentIntake(
                principal_id="bob",
                idempotency_key="k",
                source="upload",
                original_filename="shared.pdf",
                local_path=str(path),
            ),
        ]
    )
    db.commit()
    delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert path.exists()


def test_unconfigured_index_does_not_claim_cleanup(deletion_db, monkeypatch):
    from app.config import settings
    from app.services.account_deletion import AccountDeletionError

    db, root = deletion_db
    monkeypatch.setattr(settings, "meilisearch_url", "")
    db.add(_file("alice", root / "file.pdf"))
    db.commit()
    with pytest.raises(AccountDeletionError):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    row = db.query(AccountDeletionTombstone).one()
    assert row.status == "failed" and row.cleanup_manifest
    assert db.query(FileRecord).filter_by(owner_id="alice").count() == 1


def test_foreign_routing_rule_blocks_before_fence_or_file_deletion(deletion_db):
    from app.models import Pipeline, PipelineRoutingRule

    db, root = deletion_db
    path = root / "held.pdf"
    path.write_bytes(b"data")
    pipeline = Pipeline(owner_id="alice", name="shared")
    db.add_all([_file("alice", path), pipeline])
    db.flush()
    db.add(
        PipelineRoutingRule(
            owner_id="bob", name="r", field="filename", operator="equals", value="x", target_pipeline_id=pipeline.id
        )
    )
    db.commit()
    with pytest.raises(DeletionBlocked, match="remove or reassign"):
        delete_account(db, "alice", confirmation="DELETE MY ACCOUNT", workdir=root)
    assert path.read_bytes() == b"data"
    assert db.query(AccountDeletionTombstone).count() == 0
    assert db.query(FileRecord).filter_by(owner_id="alice").count() == 1


def test_never_used_index_mode_skips_only_disabled_indexes(monkeypatch):
    from app.config import settings
    from app.services.account_deletion import _delete_external_indexes

    monkeypatch.setattr(settings, "meilisearch_deletion_mode", "never_used")
    monkeypatch.setattr(settings, "vector_index_deletion_mode", "never_used")
    monkeypatch.setattr(settings, "enable_search", False)
    monkeypatch.setattr(settings, "vector_index_enabled", False)
    monkeypatch.setattr(settings, "meilisearch_url", "")
    monkeypatch.setattr(settings, "vector_index_url", "")
    _delete_external_indexes("alice", [1])


def test_never_used_mode_rejects_enabled_index(monkeypatch):
    from app.config import settings
    from app.services.account_deletion import _delete_external_indexes

    monkeypatch.setattr(settings, "meilisearch_deletion_mode", "never_used")
    monkeypatch.setattr(settings, "enable_search", True)
    with pytest.raises(RuntimeError, match="never_used"):
        _delete_external_indexes("alice", [1])


def test_managed_disabled_index_still_requires_cleanup(monkeypatch):
    from app.config import settings
    from app.services.account_deletion import _delete_external_indexes

    monkeypatch.setattr(settings, "meilisearch_deletion_mode", "managed")
    monkeypatch.setattr(settings, "meilisearch_url", "")
    monkeypatch.setattr(settings, "vector_index_deletion_mode", "never_used")
    monkeypatch.setattr(settings, "vector_index_enabled", False)
    with pytest.raises(RuntimeError, match="Meilisearch"):
        _delete_external_indexes("alice", [1])
