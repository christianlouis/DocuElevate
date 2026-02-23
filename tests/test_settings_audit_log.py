"""Tests for the settings audit log, rollback, per-option save, and worker sync features."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import SettingsAuditLog

# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ===========================================================================
# A) Audit log written on save
# ===========================================================================


@pytest.mark.unit
class TestAuditLogOnSave:
    """Audit log entries are created when settings are saved or deleted."""

    def test_save_creates_audit_entry(self, db_session):
        from app.utils.settings_service import save_setting_to_db

        result = save_setting_to_db(db_session, "workdir", "/new/path", changed_by="alice")

        assert result is True
        entry = db_session.query(SettingsAuditLog).filter_by(key="workdir").first()
        assert entry is not None
        assert entry.action == "update"
        assert entry.new_value == "/new/path"
        assert entry.changed_by == "alice"
        assert entry.old_value is None  # was not previously set

    def test_update_records_old_value(self, db_session):
        from app.utils.settings_service import save_setting_to_db

        # Set initial value
        save_setting_to_db(db_session, "workdir", "/old/path", changed_by="admin")
        # Update
        save_setting_to_db(db_session, "workdir", "/new/path", changed_by="bob")

        entries = db_session.query(SettingsAuditLog).filter_by(key="workdir").all()
        assert len(entries) == 2
        # Second entry should have old_value from first write
        update_entry = entries[1]
        assert update_entry.old_value == "/old/path"
        assert update_entry.new_value == "/new/path"

    def test_delete_creates_audit_entry(self, db_session):
        from app.utils.settings_service import delete_setting_from_db, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/some/path", changed_by="admin")
        result = delete_setting_from_db(db_session, "workdir", changed_by="carol")

        assert result is True
        delete_entry = db_session.query(SettingsAuditLog).filter_by(key="workdir", action="delete").first()
        assert delete_entry is not None
        assert delete_entry.old_value == "/some/path"
        assert delete_entry.new_value is None
        assert delete_entry.changed_by == "carol"

    def test_delete_nonexistent_returns_false_no_entry(self, db_session):
        from app.utils.settings_service import delete_setting_from_db

        result = delete_setting_from_db(db_session, "nonexistent_key", changed_by="admin")

        assert result is False
        assert db_session.query(SettingsAuditLog).count() == 0

    def test_default_changed_by_is_system(self, db_session):
        from app.utils.settings_service import save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/tmp")

        entry = db_session.query(SettingsAuditLog).first()
        assert entry.changed_by == "system"


# ===========================================================================
# C) Audit log retrieval
# ===========================================================================


@pytest.mark.unit
class TestGetAuditLog:
    """get_audit_log returns entries, masks sensitive values."""

    def test_returns_all_entries_most_recent_first(self, db_session):
        from app.utils.settings_service import get_audit_log, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/first", changed_by="u1")
        save_setting_to_db(db_session, "workdir", "/second", changed_by="u2")

        log = get_audit_log(db_session, limit=100)

        assert len(log) == 2
        # Most recent first
        assert log[0]["new_value"] == "/second"
        assert log[1]["new_value"] == "/first"

    def test_sensitive_values_are_masked(self, db_session):
        from app.utils.settings_service import get_audit_log, save_setting_to_db

        save_setting_to_db(db_session, "openai_api_key", "sk-secret123", changed_by="admin")

        log = get_audit_log(db_session)

        entry = next(e for e in log if e["key"] == "openai_api_key")
        assert entry["new_value"] == "[REDACTED]"

    def test_required_fields_present(self, db_session):
        from app.utils.settings_service import get_audit_log, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/path", changed_by="alice")

        log = get_audit_log(db_session)

        assert len(log) == 1
        entry = log[0]
        for field in (
            "id",
            "key",
            "old_value",
            "new_value",
            "changed_by",
            "changed_at",
            "action",
        ):
            assert field in entry

    def test_limit_and_offset(self, db_session):
        from app.utils.settings_service import get_audit_log, save_setting_to_db

        for i in range(5):
            save_setting_to_db(db_session, "workdir", f"/path{i}", changed_by="admin")

        first_page = get_audit_log(db_session, limit=3, offset=0)
        second_page = get_audit_log(db_session, limit=3, offset=3)

        assert len(first_page) == 3
        assert len(second_page) == 2


# ===========================================================================
# C) Per-key history
# ===========================================================================


@pytest.mark.unit
class TestGetSettingHistory:
    """get_setting_history returns only entries for the requested key."""

    def test_returns_only_matching_key(self, db_session):
        from app.utils.settings_service import get_setting_history, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/wdir", changed_by="admin")
        save_setting_to_db(db_session, "debug", "true", changed_by="admin")

        history = get_setting_history(db_session, "workdir")

        assert len(history) == 1
        assert history[0]["key"] == "workdir"

    def test_returns_empty_list_for_unknown_key(self, db_session):
        from app.utils.settings_service import get_setting_history

        history = get_setting_history(db_session, "totally_unknown_key")

        assert history == []


# ===========================================================================
# D) Rollback
# ===========================================================================


@pytest.mark.unit
class TestRollbackSetting:
    """rollback_setting reinstates the value from a given audit log entry."""

    def test_rollback_to_previous_value(self, db_session):
        """Rolling back an entry restores the old_value (the value *before* that change)."""
        from app.utils.settings_service import get_setting_from_db, rollback_setting, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/v1", changed_by="admin")  # entry 1: old=None, new=/v1
        save_setting_to_db(db_session, "workdir", "/v2", changed_by="admin")  # entry 2: old=/v1, new=/v2

        # Rolling back entry 2 should undo the /v1→/v2 change and restore /v1
        second_entry = (
            db_session.query(SettingsAuditLog).filter_by(key="workdir").order_by(SettingsAuditLog.id.desc()).first()
        )
        success = rollback_setting(db_session, "workdir", second_entry.id, changed_by="rollbacker")

        assert success is True
        current = get_setting_from_db(db_session, "workdir")
        assert current == "/v1"

    def test_rollback_deletes_setting_when_old_value_is_none(self, db_session):
        """Rolling back the first-ever entry (old_value=None) deletes the setting from DB."""
        from app.utils.settings_service import get_setting_from_db, rollback_setting, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/v1", changed_by="admin")  # old=None, new=/v1

        first_entry = db_session.query(SettingsAuditLog).filter_by(key="workdir").first()
        success = rollback_setting(db_session, "workdir", first_entry.id, changed_by="rollbacker")

        assert success is True
        # Setting should be removed from DB (fallback to ENV/default)
        current = get_setting_from_db(db_session, "workdir")
        assert current is None

    def test_rollback_creates_new_audit_entry(self, db_session):
        from app.utils.settings_service import rollback_setting, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/v1", changed_by="admin")
        entry = db_session.query(SettingsAuditLog).filter_by(key="workdir").first()

        initial_count = db_session.query(SettingsAuditLog).count()
        rollback_setting(db_session, "workdir", entry.id, changed_by="rollbacker")

        assert db_session.query(SettingsAuditLog).count() == initial_count + 1

    def test_rollback_wrong_history_id_returns_false(self, db_session):
        from app.utils.settings_service import rollback_setting, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/v1", changed_by="admin")

        result = rollback_setting(db_session, "workdir", 9999, changed_by="admin")

        assert result is False

    def test_rollback_wrong_key_returns_false(self, db_session):
        from app.utils.settings_service import rollback_setting, save_setting_to_db

        save_setting_to_db(db_session, "workdir", "/v1", changed_by="admin")
        entry = db_session.query(SettingsAuditLog).filter_by(key="workdir").first()

        # Pass wrong key for the history ID
        result = rollback_setting(db_session, "debug", entry.id, changed_by="admin")

        assert result is False


# ===========================================================================
# B) Worker sync – settings_sync module
# ===========================================================================


@pytest.mark.unit
class TestNotifySettingsUpdated:
    """notify_settings_updated publishes the settings version key to Redis."""

    def test_sets_redis_key(self):
        from app.utils.settings_sync import SETTINGS_VERSION_KEY, notify_settings_updated

        mock_redis = MagicMock()
        mock_redis_instance = MagicMock()
        mock_redis.return_value = mock_redis_instance

        with patch("app.utils.settings_sync.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis_instance
            notify_settings_updated()

        mock_redis_instance.set.assert_called_once()
        call_args = mock_redis_instance.set.call_args[0]
        assert call_args[0] == SETTINGS_VERSION_KEY

    def test_does_not_raise_on_redis_failure(self):
        """notify_settings_updated must not propagate Redis errors."""
        from app.utils.settings_sync import notify_settings_updated

        with patch("app.utils.settings_sync.redis") as mock_redis_module:
            mock_redis_module.from_url.side_effect = Exception("Redis down")
            # Should not raise
            notify_settings_updated()


@pytest.mark.unit
class TestRegisterSettingsReloadSignal:
    """register_settings_reload_signal installs a task_prerun handler."""

    def test_registers_without_error(self):
        from app.utils.settings_sync import register_settings_reload_signal

        with patch("app.utils.settings_sync.task_prerun") as mock_signal:
            mock_signal.connect = MagicMock()
            # Call it – the decorator calls task_prerun.connect(weak=False)
            register_settings_reload_signal()
        # If no exception is raised the registration succeeded


# ===========================================================================
# API endpoint – audit log
# ===========================================================================


@pytest.mark.integration
class TestAuditLogEndpoint:
    """GET /api/settings/audit-log requires admin access."""

    def test_requires_admin(self, client):
        response = client.get("/api/settings/audit-log")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.get_audit_log")
    def test_returns_entries_for_admin(self, mock_get_log):
        from app.api.settings import list_audit_log

        mock_get_log.return_value = [
            {
                "id": 1,
                "key": "workdir",
                "old_value": None,
                "new_value": "/tmp",
                "changed_by": "admin",
                "changed_at": "2024-01-01T00:00:00",
                "action": "update",
            }
        ]

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(list_audit_log(mock_request, mock_db, mock_admin))

        assert "entries" in result
        assert len(result["entries"]) == 1
        assert result["entries"][0]["key"] == "workdir"


@pytest.mark.integration
class TestHistoryEndpoint:
    """GET /api/settings/{key}/history requires admin access."""

    def test_requires_admin(self, client):
        response = client.get("/api/settings/workdir/history")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.get_setting_history")
    def test_returns_history_for_admin(self, mock_get_history):
        from app.api.settings import get_key_history

        mock_get_history.return_value = [
            {
                "id": 1,
                "key": "workdir",
                "old_value": None,
                "new_value": "/tmp",
                "changed_by": "admin",
                "changed_at": "2024-01-01T00:00:00",
                "action": "update",
            }
        ]

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(get_key_history("workdir", mock_request, mock_db, mock_admin))

        assert result["key"] == "workdir"
        assert len(result["history"]) == 1


@pytest.mark.integration
class TestRollbackEndpoint:
    """POST /api/settings/{key}/rollback/{history_id} requires admin access."""

    def test_requires_admin(self, client):
        response = client.post("/api/settings/workdir/rollback/1")
        assert response.status_code in [302, 401, 403]

    @patch("app.api.settings.notify_settings_updated")
    @patch("app.api.settings.rollback_setting")
    def test_rollback_success(self, mock_rollback, mock_notify):
        from app.api.settings import rollback_setting_to_history

        mock_rollback.return_value = True
        mock_request = MagicMock()
        mock_request.session = {"user": {"preferred_username": "admin"}}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(rollback_setting_to_history("workdir", 1, mock_request, mock_db, mock_admin))

        assert result["success"] is True
        mock_notify.assert_called_once()

    @patch("app.api.settings.rollback_setting")
    def test_rollback_not_found_raises_404(self, mock_rollback):
        import asyncio

        from fastapi import HTTPException

        from app.api.settings import rollback_setting_to_history

        mock_rollback.return_value = False
        mock_request = MagicMock()
        mock_request.session = {"user": {"preferred_username": "admin"}}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(rollback_setting_to_history("workdir", 9999, mock_request, mock_db, mock_admin))

        assert exc_info.value.status_code == 404
