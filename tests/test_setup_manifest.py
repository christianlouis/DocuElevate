"""Agentic setup manifest validation, planning, and idempotent apply tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import ApplicationSettings, LocalUser, SettingsAuditLog, Tribe, TribeMembership
from app.utils.local_auth import verify_password
from app.utils.settings_service import get_setting_from_db
from app.utils.setup_manifest import (
    MANIFEST_API_VERSION,
    MANIFEST_KIND,
    SetupManifestError,
    apply_setup_manifest,
    load_setup_manifest,
    plan_setup_manifest,
    resolve_setup_manifest,
)


def _manifest() -> dict:
    return {
        "apiVersion": MANIFEST_API_VERSION,
        "kind": MANIFEST_KIND,
        "metadata": {"name": "DocuElevate Preprod Canary"},
        "spec": {
            "completeSetup": False,
            "settings": {
                "ai_provider": "litellm",
                "admin_password": {"fromEnv": "DOCUELEVATE_SETUP_ADMIN_PASSWORD"},
            },
            "users": [
                {
                    "email": "christian@example.test",
                    "username": "christian",
                    "displayName": "Christian",
                    "password": {"fromEnv": "DOCUELEVATE_SETUP_CHRISTIAN_PASSWORD"},
                    "isAdmin": True,
                },
                {
                    "email": "julia@example.test",
                    "username": "julia",
                    "displayName": "Julia",
                    "password": {"fromEnv": "DOCUELEVATE_SETUP_JULIA_PASSWORD"},
                },
            ],
            "tribes": [
                {
                    "name": "Krakau Family Preprod",
                    "members": [
                        {"email": "christian@example.test", "role": "admin"},
                        {"email": "julia@example.test", "role": "member"},
                    ],
                }
            ],
        },
    }


_ENV = {
    "DOCUELEVATE_SETUP_ADMIN_PASSWORD": "FallbackAdminPassword123!",
    "DOCUELEVATE_SETUP_CHRISTIAN_PASSWORD": "ChristianPassword123!",
    "DOCUELEVATE_SETUP_JULIA_PASSWORD": "JuliaPassword123!",
}


def test_example_and_json_schema_use_the_runtime_api_version():
    root = Path(__file__).resolve().parents[1]
    example = json.loads((root / "examples" / "agentic-setup.preprod.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (root / "schemas" / "docuelevate-setup-v1alpha1.schema.json").read_text(encoding="utf-8")
    )
    assert example["apiVersion"] == MANIFEST_API_VERSION
    assert example["kind"] == MANIFEST_KIND
    assert schema["properties"]["apiVersion"]["const"] == MANIFEST_API_VERSION
    assert schema["properties"]["kind"]["const"] == MANIFEST_KIND


def test_load_manifest_requires_json_and_reads_bounded_object(tmp_path):
    path = tmp_path / "setup.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    assert load_setup_manifest(path)["kind"] == MANIFEST_KIND

    yaml_path = tmp_path / "setup.yaml"
    yaml_path.write_text("kind: DocuElevateSetup", encoding="utf-8")
    with pytest.raises(SetupManifestError, match=".json"):
        load_setup_manifest(yaml_path)


def test_manifest_rejects_plaintext_secret_and_bootstrap_setting():
    plaintext = _manifest()
    plaintext["spec"]["settings"]["admin_password"] = "plaintext"
    with pytest.raises(SetupManifestError, match="fromEnv"):
        resolve_setup_manifest(plaintext, environ=_ENV)

    bootstrap = _manifest()
    bootstrap["spec"]["settings"]["database_url"] = "sqlite:///unsafe.db"
    with pytest.raises(SetupManifestError, match="bootstrap"):
        resolve_setup_manifest(bootstrap, environ=_ENV)


def test_manifest_reports_missing_secret_reference():
    with pytest.raises(SetupManifestError, match="DOCUELEVATE_SETUP_ADMIN_PASSWORD"):
        resolve_setup_manifest(_manifest(), environ={})


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda manifest: manifest["metadata"].update({"owner": "AI"}), "metadata"),
        (lambda manifest: manifest["spec"].update({"completeSetup": "false"}), "boolean"),
        (lambda manifest: manifest["spec"]["users"][1].update({"username": "christian"}), "username"),
        (lambda manifest: manifest["spec"]["users"][1].update({"isAdmin": "false"}), "boolean"),
        (lambda manifest: manifest["spec"]["tribes"][0]["members"].append(
            {"email": "julia@example.test", "role": "member"}
        ), "Duplicate member"),
    ],
)
def test_manifest_rejects_ambiguous_or_duplicate_desired_state(mutate, error):
    manifest = _manifest()
    mutate(manifest)
    with pytest.raises(SetupManifestError, match=error):
        resolve_setup_manifest(manifest, environ=_ENV)


def test_plan_redacts_all_secret_values(db_session):
    resolved = resolve_setup_manifest(_manifest(), environ=_ENV)
    plan = plan_setup_manifest(db_session, resolved)
    rendered = json.dumps(plan)
    assert plan["success"] is True
    assert "<resolved-secret>" in rendered
    assert not any(secret in rendered for secret in _ENV.values())


def test_apply_is_idempotent_and_creates_users_personal_scopes_and_shared_tribe(db_session):
    resolved = resolve_setup_manifest(_manifest(), environ=_ENV)
    with patch("app.utils.setup_manifest.notify_settings_updated"):
        result = apply_setup_manifest(db_session, resolved)

    assert result["success"] is True
    assert get_setting_from_db(db_session, "ai_provider") == "litellm"
    assert get_setting_from_db(db_session, "admin_password") == _ENV["DOCUELEVATE_SETUP_ADMIN_PASSWORD"]

    stored_secret = db_session.query(ApplicationSettings).filter_by(key="admin_password").one().value
    audit_secret = db_session.query(SettingsAuditLog).filter_by(key="admin_password").one().new_value
    assert stored_secret.startswith("enc:")
    assert audit_secret.startswith("enc:")
    assert _ENV["DOCUELEVATE_SETUP_ADMIN_PASSWORD"] not in stored_secret
    assert _ENV["DOCUELEVATE_SETUP_ADMIN_PASSWORD"] not in audit_secret

    users = {user.email: user for user in db_session.query(LocalUser).all()}
    assert set(users) == {"christian@example.test", "julia@example.test"}
    assert users["christian@example.test"].is_admin is True
    assert verify_password(_ENV["DOCUELEVATE_SETUP_JULIA_PASSWORD"], users["julia@example.test"].hashed_password)

    family = db_session.query(Tribe).filter_by(name="Krakau Family Preprod").one()
    roles = {
        membership.user_id: membership.role
        for membership in db_session.query(TribeMembership).filter_by(tribe_id=family.id).all()
    }
    assert roles == {"christian@example.test": "admin", "julia@example.test": "member"}
    for email in users:
        assert db_session.query(TribeMembership).filter_by(user_id=email, role="admin").count() >= 1

    second_plan = plan_setup_manifest(db_session, resolved)
    assert second_plan["summary"] == {"create": 0, "update": 0, "unchanged": 5}

    before_audits = db_session.query(SettingsAuditLog).count()
    with patch("app.utils.setup_manifest.notify_settings_updated"):
        second_apply = apply_setup_manifest(db_session, resolved)
    assert second_apply["applied"] == []
    assert db_session.query(SettingsAuditLog).count() == before_audits
