from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import sessionmaker

from app.models import CredentialCheckState
from app.tasks.check_credentials import _record_credential_result


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
