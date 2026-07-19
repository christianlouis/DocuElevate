from __future__ import annotations

import pytest

from app.config import settings
from app.models import ApplicationSettings, SettingsAuditLog, UserImapAccount, UserIntegration
from app.utils.encryption import (
    EncryptionRotationError,
    decrypt_value,
    encrypt_value,
    reset_cipher_cache,
    value_uses_primary_key,
)
from app.utils.encryption_rotation import rotate_database_encryption

OLD_SECRET = "old-session-secret-for-rotation-tests-000000000000"
NEW_SECRET = "new-session-secret-for-rotation-tests-111111111111"


@pytest.fixture(autouse=True)
def restore_cipher_settings(monkeypatch: pytest.MonkeyPatch):
    original_current = settings.session_secret
    original_previous = settings.session_secret_previous
    yield
    monkeypatch.setattr(settings, "session_secret", original_current)
    monkeypatch.setattr(settings, "session_secret_previous", original_previous)
    reset_cipher_cache()


def _use_keys(monkeypatch: pytest.MonkeyPatch, current: str, previous: str | None = None) -> None:
    monkeypatch.setattr(settings, "session_secret", current)
    monkeypatch.setattr(settings, "session_secret_previous", previous)
    reset_cipher_cache()


@pytest.mark.integration
def test_rotates_all_database_encryption_surfaces_transactionally(db_session, monkeypatch: pytest.MonkeyPatch):
    _use_keys(monkeypatch, OLD_SECRET)
    setting = ApplicationSettings(key="openai_api_key", value=encrypt_value("operator-key"))
    integration = UserIntegration(
        owner_id="owner-1",
        direction="SOURCE",
        integration_type="DROPBOX",
        name="Preprod source",
        credentials=encrypt_value('{"refresh_token":"refresh"}'),
    )
    mailbox = UserImapAccount(
        owner_id="owner-1",
        name="Mailbox",
        host="imap.example.test",
        port=993,
        username="owner@example.test",
        password=encrypt_value("mail-password"),
    )
    audit = SettingsAuditLog(
        key="openai_api_key",
        old_value=encrypt_value("previous-operator-key"),
        new_value=setting.value,
        changed_by="rotation-test",
        action="update",
    )
    redacted_legacy_audit = SettingsAuditLog(
        key="openai_api_key",
        old_value=None,
        new_value=None,
        changed_by="migration",
        action="update",
    )
    non_sensitive_audit = SettingsAuditLog(
        key="workdir",
        old_value="/old-workdir",
        new_value="/new-workdir",
        changed_by="rotation-test",
        action="update",
    )
    db_session.add_all([setting, integration, mailbox, audit, redacted_legacy_audit, non_sensitive_audit])
    db_session.commit()

    _use_keys(monkeypatch, NEW_SECRET, OLD_SECRET)
    report = rotate_database_encryption(db_session)

    assert report.scanned == 5
    assert report.rotated == 5
    assert report.invalid == 0
    assert value_uses_primary_key(setting.value)
    assert value_uses_primary_key(integration.credentials)
    assert value_uses_primary_key(mailbox.password)
    assert value_uses_primary_key(audit.old_value)
    assert value_uses_primary_key(audit.new_value)
    assert non_sensitive_audit.old_value == "/old-workdir"
    assert non_sensitive_audit.new_value == "/new-workdir"

    _use_keys(monkeypatch, NEW_SECRET)
    assert decrypt_value(setting.value) == "operator-key"
    assert decrypt_value(integration.credentials) == '{"refresh_token":"refresh"}'
    assert decrypt_value(mailbox.password) == "mail-password"
    assert decrypt_value(audit.old_value) == "previous-operator-key"
    assert decrypt_value(audit.new_value) == "operator-key"

    verification = rotate_database_encryption(db_session, verify_only=True)
    assert verification.scanned == 5
    assert verification.invalid == 0


@pytest.mark.integration
def test_rotation_is_idempotent_and_encrypts_legacy_plaintext(db_session, monkeypatch: pytest.MonkeyPatch):
    _use_keys(monkeypatch, NEW_SECRET, OLD_SECRET)
    setting = ApplicationSettings(key="openai_api_key", value="legacy-plaintext")
    db_session.add(setting)
    db_session.commit()

    first = rotate_database_encryption(db_session)
    first_value = setting.value
    second = rotate_database_encryption(db_session)

    assert first.rotated == 1
    assert second.rotated == 0
    assert setting.value == first_value
    assert decrypt_value(setting.value) == "legacy-plaintext"


@pytest.mark.integration
def test_undecryptable_value_aborts_without_partial_commit(db_session, monkeypatch: pytest.MonkeyPatch):
    _use_keys(monkeypatch, OLD_SECRET)
    valid = ApplicationSettings(key="openai_api_key", value=encrypt_value("still-old"))
    integration = UserIntegration(
        owner_id="owner-1",
        direction="SOURCE",
        integration_type="DROPBOX",
        name="Valid fixture",
        credentials=encrypt_value("integration-old"),
    )
    audit = SettingsAuditLog(
        key="openai_api_key",
        old_value=encrypt_value("audit-old"),
        new_value="enc:not-a-fernet-token",
        changed_by="rotation-test",
        action="update",
    )
    db_session.add_all([valid, integration, audit])
    db_session.commit()
    old_value = valid.value
    old_integration_value = integration.credentials
    old_audit_value = audit.old_value

    _use_keys(monkeypatch, NEW_SECRET, OLD_SECRET)
    with pytest.raises(EncryptionRotationError):
        rotate_database_encryption(db_session)

    db_session.refresh(valid)
    db_session.refresh(integration)
    db_session.refresh(audit)
    assert valid.value == old_value
    assert integration.credentials == old_integration_value
    assert audit.old_value == old_audit_value
    assert not value_uses_primary_key(valid.value)


@pytest.mark.integration
def test_verify_only_reports_plaintext_or_non_primary_values(db_session, monkeypatch: pytest.MonkeyPatch):
    _use_keys(monkeypatch, OLD_SECRET)
    old_encrypted = encrypt_value("old-value")
    db_session.add_all(
        [
            ApplicationSettings(key="openai_api_key", value=old_encrypted),
            UserIntegration(
                owner_id="owner-1",
                direction="SOURCE",
                integration_type="DROPBOX",
                name="Plaintext fixture",
                credentials="legacy-plaintext",
            ),
            SettingsAuditLog(
                key="openai_api_key",
                old_value=old_encrypted,
                new_value="legacy-plaintext",
                changed_by="rotation-test",
                action="update",
            ),
        ]
    )
    db_session.commit()

    _use_keys(monkeypatch, NEW_SECRET, OLD_SECRET)
    report = rotate_database_encryption(db_session, verify_only=True)

    assert report.scanned == 4
    assert report.rotated == 0
    assert report.invalid == 4


@pytest.mark.integration
def test_previous_session_key_is_never_a_database_rotation_target(db_session, monkeypatch: pytest.MonkeyPatch):
    _use_keys(monkeypatch, NEW_SECRET, OLD_SECRET)
    stale = ApplicationSettings(key="session_secret_previous", value=encrypt_value(OLD_SECRET))
    db_session.add(stale)
    db_session.commit()

    report = rotate_database_encryption(db_session)

    assert report.scanned == 0
    assert report.rotated == 0
