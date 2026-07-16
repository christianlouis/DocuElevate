"""Owner privacy rules operate only on the canonical file private flag."""

from contextlib import nullcontext
from unittest.mock import patch

import pytest

from app.models import FileRecord, PrivacyDecisionAudit, PrivacyRuleModel, SharedLink
from app.utils.file_privacy import apply_first_matching_privacy_rule
from app.utils.privacy_rules import (
    RULE_TYPE_CONTENT,
    RULE_TYPE_FILENAME,
    RULE_TYPE_METADATA,
    match_privacy_rule,
)
from app.utils.tribe_scope import ensure_document_scope


def _file(db, *, owner: str, name: str, text: str = "", metadata: str | None = None) -> FileRecord:
    tenant_id, tribe_id = ensure_document_scope(db, owner)
    record = FileRecord(
        owner_id=owner,
        filehash=f"hash-{owner}-{name}",
        original_filename=name,
        local_filename=f"/tmp/{name}",
        original_file_path=f"/original/{name}",
        processed_file_path=f"/processed/{name}",
        file_size=123,
        mime_type="application/pdf",
        ocr_text=text,
        ai_metadata=metadata,
        pipeline_id=None,
        tenant_id=tenant_id,
        tribe_id=tribe_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@pytest.mark.unit
@pytest.mark.parametrize(
    ("rule_type", "pattern", "filename", "text", "metadata", "confidence"),
    [
        (RULE_TYPE_FILENAME, "arztbrief", "Arztbrief.pdf", "", {}, 70),
        (RULE_TYPE_CONTENT, "Tamara|Svetlana", "letter.pdf", "Post von Svetlana", {}, 80),
        (RULE_TYPE_METADATA, "document_type=Medical", "lab.pdf", "", {"document_type": "medical"}, 95),
    ],
)
def test_match_privacy_rule(rule_type, pattern, filename, text, metadata, confidence):
    result = match_privacy_rule(
        rule_type=rule_type,
        pattern=pattern,
        case_sensitive=False,
        filename=filename,
        text=text,
        metadata=metadata,
    )
    assert result.matched is True
    assert result.evidence
    assert result.confidence == confidence


@pytest.mark.unit
def test_rule_crud_is_strictly_owner_scoped(client, db_session):
    with patch("app.api.privacy_rules.get_current_owner_id", return_value="alice"):
        created = client.post(
            "/api/privacy-rules/",
            json={
                "name": "Medical letters",
                "description": "Keep all medical letters private",
                "rule_type": "content_keyword",
                "pattern": "Arztbrief|Laborbericht",
            },
        )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    with patch("app.api.privacy_rules.get_current_owner_id", return_value="bob"):
        assert client.get(f"/api/privacy-rules/{rule_id}").status_code == 404
        assert client.put(f"/api/privacy-rules/{rule_id}", json={"enabled": False}).status_code == 404
        assert client.delete(f"/api/privacy-rules/{rule_id}").status_code == 404


@pytest.mark.unit
def test_preview_and_apply_only_change_owner_file_privacy(client, db_session):
    alice = _file(db_session, owner="alice", name="Alice.pdf", text="Arztbrief und Laborbericht")
    bob = _file(db_session, owner="bob", name="Bob.pdf", text="Arztbrief und Laborbericht")
    manual = _file(db_session, owner="alice", name="Pinned-public.pdf", text="Arztbrief")
    manual.privacy_manual_override = False
    link = SharedLink(token="alice-public-link", file_id=alice.id, owner_id="alice", is_active=True)
    rule = PrivacyRuleModel(
        owner_id="alice",
        name="Medical",
        rule_type="content_keyword",
        pattern="Arztbrief|Laborbericht",
        enabled=True,
    )
    db_session.add_all([link, rule])
    db_session.commit()
    db_session.refresh(rule)

    immutable = {
        "owner_id": alice.owner_id,
        "local_filename": alice.local_filename,
        "original_file_path": alice.original_file_path,
        "processed_file_path": alice.processed_file_path,
        "pipeline_id": alice.pipeline_id,
    }
    with (
        patch("app.api.privacy_rules.get_current_owner_id", return_value="alice"),
        patch("app.api.privacy_rules.queue_privacy_reconciliation") as reconcile,
    ):
        preview = client.post(f"/api/privacy-rules/{rule.id}/preview")
        applied = client.post(f"/api/privacy-rules/{rule.id}/apply")

    assert preview.status_code == 200
    assert {item["file_id"] for item in preview.json()["matches"]} == {alice.id, manual.id}
    assert applied.status_code == 200
    assert applied.json()["changed_file_ids"] == [alice.id]
    assert applied.json()["skipped_manual_override"] == 1
    reconcile.assert_called_once_with([alice.id])

    for record in (alice, bob, manual, link):
        db_session.refresh(record)
    assert alice.is_private is True
    assert bob.is_private is False
    assert manual.is_private is False
    assert link.is_active is False
    assert {key: getattr(alice, key) for key in immutable} == immutable
    audit = db_session.query(PrivacyDecisionAudit).filter_by(file_id=alice.id).one()
    assert audit.source == "rule"
    assert audit.rule_id == rule.id
    assert audit.is_private is True


@pytest.mark.unit
def test_manual_owner_choice_wins_until_returned_to_automatic(client, db_session):
    record = _file(db_session, owner="alice", name="Arztbrief.pdf", text="medical")
    rule = PrivacyRuleModel(
        owner_id="alice",
        name="Medical filenames",
        rule_type="filename_pattern",
        pattern="Arztbrief",
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()

    with (
        patch("app.api.files.get_current_owner_id", return_value="alice"),
        patch("app.utils.user_scope.settings.multi_user_enabled", True),
        patch("app.api.files.queue_privacy_reconciliation"),
    ):
        manual = client.put(f"/api/files/{record.id}/privacy", json={"is_private": False})
        automatic = client.delete(f"/api/files/{record.id}/privacy/override")

    assert manual.status_code == 200
    assert automatic.status_code == 200
    assert automatic.json()["is_private"] is True
    assert automatic.json()["mode"] == "automatic"
    db_session.refresh(record)
    assert record.is_private is True
    assert record.privacy_manual_override is None
    sources = [row.source for row in db_session.query(PrivacyDecisionAudit).filter_by(file_id=record.id).all()]
    assert sources == ["manual", "rule"]


@pytest.mark.unit
def test_ownerless_legacy_file_uses_single_user_privacy_scope(client, db_session):
    record = _file(db_session, owner="legacy", name="legacy.pdf")
    record.owner_id = None
    db_session.commit()

    with (
        patch("app.api.files.get_current_owner_id", return_value=None),
        patch("app.utils.user_scope.settings.multi_user_enabled", False),
        patch("app.api.files.queue_privacy_reconciliation"),
    ):
        response = client.put(f"/api/files/{record.id}/privacy", json={"is_private": True})

    assert response.status_code == 200
    db_session.refresh(record)
    assert record.is_private is True
    audit = db_session.query(PrivacyDecisionAudit).filter_by(file_id=record.id).one()
    assert audit.owner_id == "__single_user__"


@pytest.mark.unit
def test_newly_processed_file_is_marked_private_without_routing_changes(db_session):
    record = _file(db_session, owner="alice", name="letter.pdf", text="Post von Tamara")
    rule = PrivacyRuleModel(
        owner_id="alice",
        name="Private contacts",
        rule_type="content_keyword",
        pattern="Tamara|Svetlana",
        enabled=True,
    )
    db_session.add(rule)
    db_session.commit()
    before = (record.owner_id, record.local_filename, record.processed_file_path, record.pipeline_id)

    assert apply_first_matching_privacy_rule(db_session, record) is True
    db_session.commit()

    assert record.is_private is True
    assert (record.owner_id, record.local_filename, record.processed_file_path, record.pipeline_id) == before


@pytest.mark.unit
def test_index_first_vector_write_sees_committed_private_flag(db_session, monkeypatch):
    record = _file(db_session, owner="alice", name="letter.pdf", text="Post von Tamara")
    db_session.add(
        PrivacyRuleModel(
            owner_id="alice",
            name="Private contacts",
            rule_type="content_keyword",
            pattern="Tamara|Svetlana",
            enabled=True,
        )
    )
    db_session.commit()
    observed: dict[str, bool] = {}

    def capture_index(file_record):
        observed["is_private"] = file_record.is_private
        return 1

    monkeypatch.setattr("app.tasks.vector_index.settings.vector_index_enabled", True)
    with (
        patch("app.tasks.vector_index.SessionLocal", return_value=nullcontext(db_session)),
        patch("app.utils.vector_index.QdrantVectorIndex.index_document", side_effect=capture_index),
        patch("app.tasks.vector_index.queue_privacy_reconciliation") as reconcile,
    ):
        from app.tasks.vector_index import index_document_vectors

        result = index_document_vectors.run(record.id)

    db_session.refresh(record)
    assert result["status"] == "success"
    assert observed == {"is_private": True}
    assert record.is_private is True
    reconcile.assert_called_once_with([record.id])


@pytest.mark.unit
def test_privacy_rules_page_is_owner_facing(client):
    response = client.get("/privacy-rules")
    assert response.status_code == 200
    assert 'x-data="privacyRules()"' in response.text
    assert "/api/privacy-rules/" in response.text
