"""Tests for uncovered paths in app/utils/settings_service.py.

Covers:
- save_setting_to_db: decryption of old_storage_value for sensitive keys (lines 1247-1252)
- delete_setting_from_db: decryption of stored value for sensitive keys (lines 1329-1334)
- get_audit_log: SQLAlchemyError handling (lines 1469-1471)
- get_setting_history: SQLAlchemyError handling (lines 1510-1512)
- rollback_setting: SQLAlchemyError handling (lines 1553-1556)
- get_settings_for_export: DB value takes precedence in effective export (line 1582)
"""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.models import ApplicationSettings, SettingsAuditLog
from app.utils.settings_service import (
    delete_setting_from_db,
    get_audit_log,
    get_setting_history,
    get_settings_for_export,
    rollback_setting,
    save_setting_to_db,
)


@pytest.mark.unit
class TestSaveSettingDecryptsOldValue:
    """Sensitive settings history remains encrypted at rest."""

    @patch("app.utils.settings_service.get_setting_metadata")
    def test_save_sensitive_setting_decrypts_old_value_for_audit(self, mock_metadata, db_session):
        """Updating a secret keeps both audit values encrypted."""
        mock_metadata.return_value = {"sensitive": True}

        # First, save an encrypted value directly
        setting = ApplicationSettings(key="openai_api_key", value="enc:old_encrypted")
        db_session.add(setting)
        db_session.commit()

        with (
            patch("app.utils.encryption.is_encryption_available", return_value=True),
            patch("app.utils.encryption.encrypt_value", return_value="enc:new_encrypted"),
        ):
            result = save_setting_to_db(db_session, "openai_api_key", "new_api_key", changed_by="admin")

        assert result is True
        audit = db_session.query(SettingsAuditLog).filter_by(key="openai_api_key").first()
        assert audit is not None
        assert audit.old_value == "enc:old_encrypted"
        assert audit.new_value == "enc:new_encrypted"

    @patch("app.utils.settings_service.get_setting_metadata")
    def test_save_sensitive_setting_refuses_plaintext_fallback(self, mock_metadata, db_session):
        """A secret is not persisted when encryption is unavailable."""
        mock_metadata.return_value = {"sensitive": True}

        setting = ApplicationSettings(key="openai_api_key", value="enc:corrupted")
        db_session.add(setting)
        db_session.commit()

        with (
            patch("app.utils.encryption.is_encryption_available", return_value=False),
        ):
            result = save_setting_to_db(db_session, "openai_api_key", "new_key", changed_by="admin")

        assert result is False
        assert db_session.query(SettingsAuditLog).count() == 0
        assert db_session.query(ApplicationSettings).filter_by(key="openai_api_key").one().value == "enc:corrupted"


@pytest.mark.unit
class TestDeleteSettingDecryptsOldValue:
    """Deletion audit rows retain only encrypted secret material."""

    @patch("app.utils.settings_service.get_setting_metadata")
    def test_delete_sensitive_setting_decrypts_for_audit(self, mock_metadata, db_session):
        """Deleting a sensitive setting never decrypts it into history."""
        mock_metadata.return_value = {"sensitive": True}

        setting = ApplicationSettings(key="openai_api_key", value="enc:secret_value")
        db_session.add(setting)
        db_session.commit()

        result = delete_setting_from_db(db_session, "openai_api_key", changed_by="admin")

        assert result is True

        audit = db_session.query(SettingsAuditLog).filter_by(key="openai_api_key").first()
        assert audit is not None
        assert audit.old_value == "enc:secret_value"
        assert audit.action == "delete"

    @patch("app.utils.settings_service.get_setting_metadata")
    def test_delete_sensitive_setting_keeps_corrupt_ciphertext_opaque(self, mock_metadata, db_session):
        """Even unreadable ciphertext is never converted to plaintext history."""
        mock_metadata.return_value = {"sensitive": True}

        setting = ApplicationSettings(key="openai_api_key", value="enc:bad_data")
        db_session.add(setting)
        db_session.commit()

        result = delete_setting_from_db(db_session, "openai_api_key", changed_by="admin")

        assert result is True

        audit = db_session.query(SettingsAuditLog).filter_by(key="openai_api_key").first()
        assert audit is not None
        assert audit.old_value == "enc:bad_data"


@pytest.mark.unit
class TestGetAuditLogError:
    """Tests for get_audit_log SQLAlchemyError handling."""

    def test_get_audit_log_returns_empty_on_db_error(self, db_session):
        """get_audit_log returns empty list when a database error occurs."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("Connection lost")):
            result = get_audit_log(db_session)
        assert result == []


@pytest.mark.unit
class TestGetSettingHistoryError:
    """Tests for get_setting_history SQLAlchemyError handling."""

    def test_get_setting_history_returns_empty_on_db_error(self, db_session):
        """get_setting_history returns empty list when a database error occurs."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("Timeout")):
            result = get_setting_history(db_session, "debug")
        assert result == []


@pytest.mark.unit
class TestRollbackSettingError:
    """Tests for rollback_setting SQLAlchemyError handling."""

    def test_rollback_setting_returns_false_on_db_error(self, db_session):
        """rollback_setting returns False when a database error occurs."""
        with patch.object(db_session, "query", side_effect=SQLAlchemyError("DB locked")):
            result = rollback_setting(db_session, "debug", 1, changed_by="admin")
        assert result is False


@pytest.mark.unit
class TestGetSettingsForExport:
    """Tests for get_settings_for_export effective mode."""

    def test_effective_export_db_value_takes_precedence(self, db_session):
        """In effective mode, DB value takes precedence over ENV/default."""
        # Save a value in the DB
        save_setting_to_db(db_session, "debug", "true", changed_by="test")

        with patch("app.utils.settings_service.SETTING_METADATA", {"debug": {"type": "bool"}}):
            result = get_settings_for_export(db_session, source="effective")

        assert "DEBUG" in result
        assert result["DEBUG"] == "true"
