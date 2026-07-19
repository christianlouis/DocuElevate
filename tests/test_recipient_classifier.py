"""Recipient identity, classification and Tribe-boundary coverage."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.models import (
    DocumentRecipientDecision,
    FileRecord,
    RecipientIdentityProfile,
    RecipientRoutingPolicy,
    Tribe,
)
from app.utils.recipient_classifier import classify_and_persist_recipient, classify_recipient
from app.utils.tribe_scope import ensure_personal_scope, ensure_tribe_membership, shared_tribe_id


def _session(user_id: str):
    return patch(
        "starlette.requests.Request.session",
        new_callable=lambda: property(lambda self: {"user": {"id": user_id}}),
    )


def _family(db_session):
    tenant_id, _ = ensure_personal_scope(db_session, "christian")
    tribe = Tribe(id=shared_tribe_id("Family Krakau", tenant_id), tenant_id=tenant_id, name="Family Krakau")
    db_session.add(tribe)
    db_session.flush()
    for user_id, role in (("christian", "admin"), ("julia", "routing_manager"), ("emma", "member")):
        ensure_tribe_membership(
            db_session,
            tenant_id=tenant_id,
            tribe_id=tribe.id,
            user_id=user_id,
            role=role,
        )
    db_session.commit()
    return tribe


def _profile(db_session, tribe, name, users, **values):
    profile = RecipientIdentityProfile(
        tenant_id=tribe.tenant_id,
        tribe_id=tribe.id,
        profile_type="household" if len(users) > 1 else "person",
        display_name=name,
        user_ids=json.dumps(users),
        aliases=json.dumps(values.get("aliases", [])),
        postal_addresses=json.dumps(values.get("postal_addresses", [])),
        email_addresses=json.dumps(values.get("email_addresses", [])),
        identifiers=json.dumps(values.get("identifiers", [])),
        created_by="christian",
    )
    db_session.add(profile)
    db_session.flush()
    return profile


def _file(db_session, tribe, owner="christian"):
    row = FileRecord(
        owner_id=owner,
        tenant_id=tribe.tenant_id,
        tribe_id=tribe.id,
        filehash=f"hash-{owner}",
        local_filename=f"{owner}.pdf",
        file_size=10,
    )
    db_session.add(row)
    db_session.flush()
    return row


@pytest.mark.unit
class TestRecipientClassifier:
    def test_explicit_person_identifier_is_explainable(self, db_session):
        tribe = _family(db_session)
        christian = _profile(db_session, tribe, "Christian Krakau-Louis", ["christian"], identifiers=["KD-4242"])
        row = _file(db_session, tribe)

        result = classify_recipient(db_session, row, {"empfaenger": "Christian Krakau-Louis"}, "Kundennr. KD-4242")

        assert result.status == "matched"
        assert result.recipient_user_ids == ["christian"]
        assert result.matched_profile_ids == [christian.id]
        assert result.confidence == 100
        assert any(item["field"] == "identifier" for item in result.evidence)

    def test_joint_addressees_return_a_recipient_set(self, db_session):
        tribe = _family(db_session)
        _profile(db_session, tribe, "Christian Krakau-Louis", ["christian"])
        _profile(db_session, tribe, "Julia Krakau-Louis", ["julia"])
        row = _file(db_session, tribe)

        result = classify_recipient(
            db_session,
            row,
            {"empfaenger": "Christian Krakau-Louis und Julia Krakau-Louis"},
            "Gemeinsamer Steuerbescheid",
        )

        assert result.status == "matched"
        assert result.recipient_user_ids == ["christian", "julia"]
        assert len(result.matched_profile_ids) == 2

    def test_household_label_expands_to_all_configured_members(self, db_session):
        tribe = _family(db_session)
        household = _profile(
            db_session,
            tribe,
            "Familie Krakau",
            ["christian", "julia", "emma"],
            aliases=["Familie Krakau-Louis"],
        )
        row = _file(db_session, tribe)

        result = classify_recipient(db_session, row, {"recipient": "Familie Krakau"}, "")

        assert result.matched_profile_ids == [household.id]
        assert result.recipient_user_ids == ["christian", "emma", "julia"]

    def test_incidental_name_is_reviewable_not_auto_assigned(self, db_session):
        tribe = _family(db_session)
        _profile(db_session, tribe, "Emma Krakau", ["emma"])
        row = _file(db_session, tribe)

        result = classify_recipient(db_session, row, {}, "Im Anhang erwähnt Emma Krakau den Vorgang.")

        assert result.status == "ambiguous"
        assert result.recipient_user_ids == []
        assert result.confidence == 68

    def test_profiles_from_another_tribe_are_never_candidates(self, db_session):
        family = _family(db_session)
        _profile(db_session, family, "Christian Krakau-Louis", ["christian"])
        _tenant_id, personal = ensure_personal_scope(db_session, "mallory")
        other = db_session.query(Tribe).filter_by(id=personal).one()
        alien = _profile(db_session, other, "Secret Recipient", ["mallory"])
        row = _file(db_session, family)

        result = classify_recipient(db_session, row, {"recipient": "Secret Recipient"}, "")

        assert result.status == "unmatched"
        assert all(item["profile_id"] != alien.id for item in result.candidates)

    def test_ai_fallback_may_only_select_known_profiles_and_members(self, db_session):
        tribe = _family(db_session)
        julia = _profile(db_session, tribe, "Julia Krakau-Louis", ["julia"])
        row = _file(db_session, tribe)
        db_session.add(
            RecipientRoutingPolicy(
                tenant_id=tribe.tenant_id,
                tribe_id=tribe.id,
                auto_assign_threshold=80,
                review_threshold=45,
                minimum_margin=15,
                ai_fallback_enabled=True,
                ai_model="test-model",
                updated_by="christian",
            )
        )
        db_session.flush()

        result = classify_recipient(
            db_session,
            row,
            {},
            "Liebe Julia, dieses Dokument ist fuer Dich.",
            ai_resolver=lambda prompt, model: {
                "profile_ids": [julia.id, 999999],
                "confidence": 91,
                "reason": "direct salutation",
            },
        )

        assert result.strategy == "ai_fallback"
        assert result.matched_profile_ids == [julia.id]
        assert result.recipient_user_ids == ["julia"]

    def test_decision_is_upserted_with_scope_and_evidence(self, db_session):
        tribe = _family(db_session)
        _profile(db_session, tribe, "Julia Krakau-Louis", ["julia"])
        row = _file(db_session, tribe)

        decision = classify_and_persist_recipient(db_session, row, {"empfaenger": "Julia Krakau-Louis"}, "")
        db_session.commit()
        updated = classify_and_persist_recipient(db_session, row, {}, "unrelated")
        db_session.commit()

        assert decision.id == updated.id
        assert updated.tenant_id == tribe.tenant_id
        assert updated.tribe_id == tribe.id
        assert updated.status == "unmatched"
        assert db_session.query(DocumentRecipientDecision).filter_by(file_id=row.id).count() == 1


@pytest.mark.integration
class TestRecipientIdentityAPI:
    def test_routing_manager_can_create_profile_and_dry_run(self, client, db_session):
        tribe = _family(db_session)
        with _session("julia"):
            created = client.post(
                f"/api/tribes/{tribe.id}/recipients/profiles",
                json={
                    "display_name": "Emma Krakau",
                    "profile_type": "person",
                    "user_ids": ["emma"],
                    "aliases": ["Emma K."],
                },
            )
            dry_run = client.post(
                f"/api/tribes/{tribe.id}/recipients/dry-run",
                json={"metadata": {"empfaenger": "Emma K."}},
            )

        assert created.status_code == 201
        assert dry_run.status_code == 200
        assert dry_run.json()["recipient_user_ids"] == ["emma"]

    def test_member_cannot_manage_profiles_and_unknown_users_are_rejected(self, client, db_session):
        tribe = _family(db_session)
        body = {"display_name": "Outsider", "profile_type": "person", "user_ids": ["mallory"]}
        with _session("emma"):
            forbidden = client.post(f"/api/tribes/{tribe.id}/recipients/profiles", json=body)
        with _session("christian"):
            invalid = client.post(f"/api/tribes/{tribe.id}/recipients/profiles", json=body)

        assert forbidden.status_code == 403
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == {"unknown_tribe_members": ["mallory"]}

    def test_non_member_cannot_read_profiles_or_decisions(self, client, db_session):
        tribe = _family(db_session)
        with _session("mallory"):
            profiles = client.get(f"/api/tribes/{tribe.id}/recipients/profiles")
            decision = client.get(f"/api/tribes/{tribe.id}/recipients/files/1/decision")

        assert profiles.status_code == 404
        assert decision.status_code == 404

    def test_private_document_decision_is_visible_only_to_owner(self, client, db_session, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "multi_user_enabled", True)
        tribe = _family(db_session)
        _profile(db_session, tribe, "Christian Krakau-Louis", ["christian"])
        row = _file(db_session, tribe)
        row.is_private = True
        classify_and_persist_recipient(db_session, row, {"empfaenger": "Christian Krakau-Louis"}, "")
        db_session.commit()

        with _session("julia"):
            denied = client.get(f"/api/tribes/{tribe.id}/recipients/files/{row.id}/decision")
        with _session("christian"):
            allowed = client.get(f"/api/tribes/{tribe.id}/recipients/files/{row.id}/decision")

        assert denied.status_code == 404
        assert allowed.status_code == 200
        assert allowed.json()["recipient_user_ids"] == ["christian"]

    def test_policy_is_database_backed_and_validated(self, client, db_session):
        tribe = _family(db_session)
        with _session("christian"):
            updated = client.put(
                f"/api/tribes/{tribe.id}/recipients/policy",
                json={
                    "auto_assign_threshold": 85,
                    "review_threshold": 55,
                    "minimum_margin": 10,
                    "ai_fallback_enabled": True,
                    "ai_model": "gpt-5-nano",
                },
            )
            loaded = client.get(f"/api/tribes/{tribe.id}/recipients/policy")
            invalid = client.put(
                f"/api/tribes/{tribe.id}/recipients/policy",
                json={"auto_assign_threshold": 50, "review_threshold": 75},
            )

        assert updated.status_code == 200
        assert loaded.json()["ai_model"] == "gpt-5-nano"
        assert loaded.json()["auto_assign_threshold"] == 85
        assert invalid.status_code == 422
