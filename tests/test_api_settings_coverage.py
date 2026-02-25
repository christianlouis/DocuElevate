"""Tests for uncovered paths in app/api/settings.py.

Covers:
- audit-log endpoint error path (lines 181-183)
- export-env endpoint error path (lines 237-239)
- delete setting HTTPException re-raise (line 341, 353)
- install-ocr-languages endpoint (lines 424-443)
- key history endpoint error path (lines 461-463)
- rollback endpoint error path and HTTPException re-raise (lines 509-513)
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.unit
class TestAuditLogEndpoint:
    """Tests for GET /settings/audit-log endpoint."""

    @patch("app.api.settings.get_audit_log")
    def test_audit_log_success(self, mock_audit_log):
        """Test successful retrieval of audit log."""
        from app.api.settings import list_audit_log

        mock_audit_log.return_value = [
            {"id": 1, "key": "debug", "old_value": "false", "new_value": "true", "changed_by": "admin"}
        ]
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(list_audit_log(mock_request, mock_db, mock_admin, limit=100, offset=0))

        assert result["entries"] == mock_audit_log.return_value
        assert result["limit"] == 100
        assert result["offset"] == 0

    @patch("app.api.settings.get_audit_log")
    def test_audit_log_error_raises_500(self, mock_audit_log):
        """Test that audit log errors raise HTTP 500."""
        from app.api.settings import list_audit_log

        mock_audit_log.side_effect = Exception("DB connection lost")
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(list_audit_log(mock_request, mock_db, mock_admin))
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestExportEnvEndpoint:
    """Tests for GET /settings/export-env endpoint."""

    @patch("app.utils.settings_service.get_settings_for_export")
    def test_export_env_db_source_success(self, mock_export):
        """Test successful export with db source."""
        from app.api.settings import export_env_settings

        mock_export.return_value = {"DEBUG": "true", "WORKDIR": "/tmp"}
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(export_env_settings(mock_request, mock_db, mock_admin, source="db"))

        assert result.status_code == 200
        assert "text/plain" in result.media_type
        body = result.body.decode()
        assert "DEBUG=true" in body
        assert "WORKDIR=/tmp" in body

    @patch("app.utils.settings_service.get_settings_for_export")
    def test_export_env_error_raises_500(self, mock_export):
        """Test that export errors raise HTTP 500."""
        from app.api.settings import export_env_settings

        mock_export.side_effect = Exception("Export failed")
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(export_env_settings(mock_request, mock_db, mock_admin, source="db"))
        assert exc_info.value.status_code == 500

    def test_export_env_invalid_source_raises_400(self):
        """Test that invalid source parameter raises HTTP 400."""
        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(export_env_settings(mock_request, mock_db, mock_admin, source="invalid"))
        assert exc_info.value.status_code == 400


@pytest.mark.unit
class TestDeleteSettingEndpoint:
    """Tests for DELETE /settings/{key} endpoint."""

    @patch("app.api.settings.notify_settings_updated")
    @patch("app.api.settings.delete_setting_from_db")
    @patch("app.api.settings.validate_setting_key")
    def test_delete_setting_not_found_raises_404(self, mock_validate, mock_delete, mock_notify):
        """Test that deleting a non-existent setting raises 404."""
        from app.api.settings import delete_setting

        mock_delete.return_value = False
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(delete_setting(key="nonexistent", request=mock_request, db=mock_db, admin=mock_admin))
        assert exc_info.value.status_code == 404

    @patch("app.api.settings.delete_setting_from_db")
    @patch("app.api.settings.validate_setting_key")
    def test_delete_setting_unexpected_error_raises_500(self, mock_validate, mock_delete):
        """Test that unexpected errors during delete raise 500."""
        from app.api.settings import delete_setting

        mock_delete.side_effect = RuntimeError("Unexpected DB error")
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(delete_setting(key="some_key", request=mock_request, db=mock_db, admin=mock_admin))
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestInstallOCRLanguagesEndpoint:
    """Tests for POST /settings/install-ocr-languages endpoint."""

    @patch("app.utils.ocr_language_manager.ensure_ocr_languages_from_settings")
    def test_install_ocr_languages_all_ok(self, mock_ensure):
        """Test successful OCR language installation."""
        from app.api.settings import install_ocr_languages

        mock_ensure.return_value = {"tesseract_missing": [], "easyocr_failed": []}
        mock_request = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(install_ocr_languages(mock_request, mock_admin))

        assert result["success"] is True
        assert result["tesseract_missing"] == []
        assert result["easyocr_failed"] == []

    @patch("app.utils.ocr_language_manager.ensure_ocr_languages_from_settings")
    def test_install_ocr_languages_some_missing(self, mock_ensure):
        """Test partial failure in OCR language installation."""
        from app.api.settings import install_ocr_languages

        mock_ensure.return_value = {"tesseract_missing": ["jpn"], "easyocr_failed": ["ar"]}
        mock_request = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(install_ocr_languages(mock_request, mock_admin))

        assert result["success"] is False
        assert "jpn" in result["tesseract_missing"]
        assert "ar" in result["easyocr_failed"]

    @patch("app.utils.ocr_language_manager.ensure_ocr_languages_from_settings")
    def test_install_ocr_languages_error_raises_500(self, mock_ensure):
        """Test that errors during installation raise HTTP 500."""
        from app.api.settings import install_ocr_languages

        mock_ensure.side_effect = Exception("Installation crashed")
        mock_request = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(install_ocr_languages(mock_request, mock_admin))
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestKeyHistoryEndpoint:
    """Tests for GET /settings/{key}/history endpoint."""

    @patch("app.api.settings.get_setting_history")
    @patch("app.api.settings.validate_setting_key_format")
    def test_key_history_success(self, mock_validate, mock_history):
        """Test successful retrieval of setting history."""
        from app.api.settings import get_key_history

        mock_history.return_value = [{"id": 1, "key": "debug", "old_value": "false", "new_value": "true"}]
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(get_key_history("debug", mock_request, mock_db, mock_admin))

        assert result["key"] == "debug"
        assert len(result["history"]) == 1

    @patch("app.api.settings.get_setting_history")
    @patch("app.api.settings.validate_setting_key_format")
    def test_key_history_error_raises_500(self, mock_validate, mock_history):
        """Test that history retrieval errors raise HTTP 500."""
        from app.api.settings import get_key_history

        mock_history.side_effect = Exception("History lookup failed")
        mock_request = MagicMock()
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_key_history("debug", mock_request, mock_db, mock_admin))
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestRollbackSettingEndpoint:
    """Tests for POST /settings/{key}/rollback/{history_id} endpoint."""

    @patch("app.api.settings.notify_settings_updated")
    @patch("app.api.settings.rollback_setting")
    @patch("app.api.settings.validate_setting_key_format")
    def test_rollback_success(self, mock_validate, mock_rollback, mock_notify):
        """Test successful setting rollback."""
        from app.api.settings import rollback_setting_to_history

        mock_rollback.return_value = True
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        result = asyncio.run(rollback_setting_to_history("debug", 42, mock_request, mock_db, mock_admin))

        assert result["success"] is True

    @patch("app.api.settings.rollback_setting")
    @patch("app.api.settings.validate_setting_key_format")
    def test_rollback_not_found_raises_404(self, mock_validate, mock_rollback):
        """Test that rollback with invalid history_id raises 404."""
        from app.api.settings import rollback_setting_to_history

        mock_rollback.return_value = False
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(rollback_setting_to_history("debug", 999, mock_request, mock_db, mock_admin))
        assert exc_info.value.status_code == 404

    @patch("app.api.settings.rollback_setting")
    @patch("app.api.settings.validate_setting_key_format")
    def test_rollback_unexpected_error_raises_500(self, mock_validate, mock_rollback):
        """Test that unexpected errors during rollback raise 500."""
        from app.api.settings import rollback_setting_to_history

        mock_rollback.side_effect = RuntimeError("Unexpected error")
        mock_request = MagicMock()
        mock_request.session.get.return_value = {"username": "admin", "is_admin": True}
        mock_db = MagicMock()
        mock_admin = {"is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(rollback_setting_to_history("debug", 1, mock_request, mock_db, mock_admin))
        assert exc_info.value.status_code == 500
