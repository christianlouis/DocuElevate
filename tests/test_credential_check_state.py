from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from app.models import CredentialCheckState
from app.tasks.check_credentials import _record_credential_result, _redact_message


def test_credential_state_is_shared_and_notification_is_thresholded(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind()),
    )

    legacy = {"Dropbox": {"count": 0, "recovered": False}}
    assert _record_credential_result("Dropbox", False, legacy)[1] is True
    assert _record_credential_result("Dropbox", False, legacy)[1] is False
    assert _record_credential_result("Dropbox", False, legacy)[1] is False
    assert _record_credential_result("Dropbox", False, legacy)[1] is False

    state = db_session.query(CredentialCheckState).filter_by(service_name="Dropbox").one()
    assert state.failure_count == 4
    assert state.recovered is False

    _record_credential_result("Dropbox", True, legacy)
    assert _record_credential_result("Dropbox", False, legacy)[1] is True


def test_concurrent_failures_have_one_notification_claim(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind()),
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _record_credential_result("Dropbox", False, {}), range(8)))

    assert sum(should_notify for _snapshot, should_notify in results) == 1
    state = db_session.query(CredentialCheckState).filter_by(service_name="Dropbox").one()
    assert state.failure_count == 8


def test_notification_claim_expires_after_cooldown(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind()),
    )

    _record_credential_result("Dropbox", False, {})
    state = db_session.query(CredentialCheckState).filter_by(service_name="Dropbox").one()
    state.last_notified_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db_session.commit()

    assert _record_credential_result("Dropbox", False, {})[1] is True


def test_legacy_non_mapping_is_ignored_when_seeding(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind()),
    )

    snapshot, should_notify = _record_credential_result("OneDrive", False, {"OneDrive": "invalid"})

    assert should_notify is True
    assert snapshot["count"] == 1


def test_redaction_covers_bearer_and_url_credentials():
    message = "Authorization: Bearer bearer-secret https://user:password@example.test"

    redacted = _redact_message(message)

    assert "bearer-secret" not in redacted
    assert "user:password" not in redacted


def test_task_does_not_read_legacy_json(monkeypatch):
    from app.tasks.check_credentials import check_credentials

    monkeypatch.setattr(
        "app.tasks.check_credentials.get_failure_state",
        lambda: (_ for _ in ()).throw(AssertionError("legacy JSON must not be read")),
    )
    monkeypatch.setattr("app.tasks.check_credentials.get_provider_status", lambda: {})
    monkeypatch.setattr("app.tasks.check_credentials.validate_storage_configs", lambda: {})

    result = check_credentials.run()

    assert result["failures"] == 0


def test_malformed_legacy_state_is_ignored_when_seeding(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.database.SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind()),
    )

    snapshot, should_notify = _record_credential_result("Google Drive", False, {"Google Drive": {"count": "bad"}})

    assert should_notify is True
    assert snapshot["count"] == 1


def test_unavailable_shared_state_does_not_write_legacy_file(monkeypatch):
    from sqlalchemy.exc import OperationalError

    def unavailable():
        raise OperationalError("SELECT", {}, RuntimeError("database down"))

    monkeypatch.setattr("app.database.SessionLocal", unavailable)
    snapshot, should_notify = _record_credential_result("OneDrive", False, {})

    assert snapshot is None
    assert should_notify is False
