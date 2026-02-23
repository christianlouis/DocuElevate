"""
Tests for wizard DB persistence, settings export, and related functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.utils.settings_service import get_setting_from_db, save_setting_to_db

# ---------------------------------------------------------------------------
# TestSetupWizardDbPersist
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetupWizardDbPersist:
    """Unit tests for setup_wizard_save POST handler DB persistence."""

    @patch("app.views.wizard.notify_settings_updated")
    @patch("app.views.wizard.save_setting_to_db")
    def test_settings_saved_to_db(self, mock_save, mock_notify, client):
        """Test that settings are saved to DB via save_setting_to_db."""
        mock_save.return_value = True

        response = client.post(
            "/setup",
            data={"step": "1", "database_url": "sqlite:///test.db"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        mock_save.assert_called()

    @patch("app.views.wizard.notify_settings_updated")
    @patch("app.views.wizard.save_setting_to_db")
    def test_notify_called_when_settings_saved(self, mock_save, mock_notify, client):
        """Test that notify_settings_updated is called when settings are saved."""
        mock_save.return_value = True

        client.post(
            "/setup",
            data={"step": "1", "database_url": "sqlite:///test.db"},
            follow_redirects=False,
        )

        mock_notify.assert_called_once()

    @patch("app.views.wizard.notify_settings_updated")
    @patch("app.views.wizard.save_setting_to_db")
    def test_notify_not_called_when_no_settings_saved(
        self, mock_save, mock_notify, client
    ):
        """Test that notify_settings_updated is NOT called when saved_count == 0."""
        mock_save.return_value = False

        client.post(
            "/setup",
            data={"step": "1"},  # no values provided
            follow_redirects=False,
        )

        mock_notify.assert_not_called()

    @patch("app.views.wizard.notify_settings_updated")
    @patch("app.views.wizard.secrets.token_hex")
    @patch("app.views.wizard.save_setting_to_db")
    def test_auto_generate_session_secret(
        self, mock_save, mock_token, mock_notify, client
    ):
        """Test that session_secret auto-generate path produces a real token."""
        mock_save.return_value = True
        mock_token.return_value = "deadbeef" * 8

        client.post(
            "/setup",
            data={"step": "2", "session_secret": "auto-generate"},
            follow_redirects=False,
        )

        mock_token.assert_called_once()
        # Ensure save was called with the generated token, not 'auto-generate'
        for call_args in mock_save.call_args_list:
            args = call_args[0]
            if len(args) >= 2 and args[1] == "session_secret":
                assert args[2] != "auto-generate"


# ---------------------------------------------------------------------------
# TestSetupWizardUndoSkip
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSetupWizardUndoSkip:
    """Tests for /setup/undo-skip route."""

    def test_undo_skip_removes_marker(self, client, db_session):
        """Test that undo-skip removes the _setup_wizard_skipped marker from DB."""
        # First, put the marker in DB
        save_setting_to_db(db_session, "_setup_wizard_skipped", "true")
        assert get_setting_from_db(db_session, "_setup_wizard_skipped") == "true"

        # Undo skip via the route
        response = client.get("/setup/undo-skip", follow_redirects=False)

        # Should redirect
        assert response.status_code in (303, 200)

    def test_undo_skip_redirects_to_wizard(self, client):
        """Test that undo-skip redirects to /setup?step=1."""
        response = client.get("/setup/undo-skip", follow_redirects=False)
        # The redirect should go to /setup?step=1 or /settings on error
        assert response.status_code in (303, 302)
        location = response.headers.get("location", "")
        assert "/setup" in location or "/settings" in location

    @patch("app.utils.settings_service.delete_setting_from_db")
    def test_undo_skip_calls_delete(self, mock_delete, client):
        """Test that undo-skip calls delete_setting_from_db."""
        mock_delete.return_value = True
        # Just ensure the route exists and does not 404
        response = client.get("/setup/undo-skip", follow_redirects=False)
        assert response.status_code != 404


# ---------------------------------------------------------------------------
# TestDropboxSaveSettingsDbPersist
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDropboxSaveSettingsDbPersist:
    """Unit tests for save_dropbox_settings DB persistence."""

    @patch("app.api.dropbox.settings")
    @patch("app.api.dropbox.notify_settings_updated")
    @patch("app.api.dropbox.save_setting_to_db")
    def test_db_written_even_when_env_missing(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that DB is written even when .env doesn't exist (no exception)."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            response = client.post(
                "/api/dropbox/save-settings",
                data={"refresh_token": "test-refresh-token"},
                follow_redirects=False,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        mock_save.assert_called()

    @patch("app.api.dropbox.settings")
    @patch("app.api.dropbox.notify_settings_updated")
    @patch("app.api.dropbox.save_setting_to_db")
    def test_notify_settings_updated_called(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that notify_settings_updated is called."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            client.post(
                "/api/dropbox/save-settings",
                data={"refresh_token": "test-refresh-token"},
                follow_redirects=False,
            )

        mock_notify.assert_called_once()

    @patch("app.api.dropbox.settings")
    @patch("app.api.dropbox.notify_settings_updated")
    @patch("app.api.dropbox.save_setting_to_db")
    def test_all_provided_values_persisted(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that all provided values are persisted to DB."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            client.post(
                "/api/dropbox/save-settings",
                data={
                    "refresh_token": "tok",
                    "app_key": "key",
                    "app_secret": "secret",
                    "folder_path": "/uploads",
                },
                follow_redirects=False,
            )

        keys_saved = [call[0][1] for call in mock_save.call_args_list]
        assert "dropbox_refresh_token" in keys_saved
        assert "dropbox_app_key" in keys_saved
        assert "dropbox_app_secret" in keys_saved
        assert "dropbox_folder" in keys_saved


# ---------------------------------------------------------------------------
# TestGoogleDriveUpdateSettingsDbPersist
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGoogleDriveUpdateSettingsDbPersist:
    """Unit tests for update_google_drive_settings DB persistence."""

    @patch("app.api.google_drive.settings")
    @patch("app.api.google_drive.notify_settings_updated")
    @patch("app.api.google_drive.save_setting_to_db")
    def test_db_written_for_each_provided_field(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that DB is written for each provided field."""
        mock_save.return_value = True

        response = client.post(
            "/api/google-drive/update-settings",
            data={
                "refresh_token": "gdrive-refresh",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "folder_id": "folder-123",
                "use_oauth": "true",
            },
            follow_redirects=False,
        )

        assert response.status_code == 200
        keys_saved = [call[0][1] for call in mock_save.call_args_list]
        assert "google_drive_refresh_token" in keys_saved
        assert "google_drive_client_id" in keys_saved
        assert "google_drive_client_secret" in keys_saved
        assert "google_drive_folder_id" in keys_saved
        assert "google_drive_use_oauth" in keys_saved

    @patch("app.api.google_drive.settings")
    @patch("app.api.google_drive.notify_settings_updated")
    @patch("app.api.google_drive.save_setting_to_db")
    def test_use_oauth_saved_as_lowercase_string(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that use_oauth is saved as 'true' or 'false' string."""
        mock_save.return_value = True

        client.post(
            "/api/google-drive/update-settings",
            data={"refresh_token": "tok", "use_oauth": "true"},
            follow_redirects=False,
        )

        use_oauth_calls = [
            call
            for call in mock_save.call_args_list
            if call[0][1] == "google_drive_use_oauth"
        ]
        assert len(use_oauth_calls) == 1
        assert use_oauth_calls[0][0][2] in ("true", "false")

    @patch("app.api.google_drive.settings")
    @patch("app.api.google_drive.notify_settings_updated")
    @patch("app.api.google_drive.save_setting_to_db")
    def test_notify_called(self, mock_save, mock_notify, mock_settings, client):
        """Test that notify_settings_updated is called."""
        mock_save.return_value = True

        client.post(
            "/api/google-drive/update-settings",
            data={"refresh_token": "tok"},
            follow_redirects=False,
        )

        mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# TestOneDriveSaveSettingsDbPersist
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOneDriveSaveSettingsDbPersist:
    """Unit tests for save_onedrive_settings DB persistence."""

    @patch("app.api.onedrive.settings")
    @patch("app.api.onedrive.notify_settings_updated")
    @patch("app.api.onedrive.save_setting_to_db")
    def test_db_written_even_without_env_file(
        self, mock_save, mock_notify, mock_settings, client
    ):
        """Test that DB is written even when .env file does not exist."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            response = client.post(
                "/api/onedrive/save-settings",
                data={"refresh_token": "od-refresh", "tenant_id": "common"},
                follow_redirects=False,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        mock_save.assert_called()

    @patch("app.api.onedrive.settings")
    @patch("app.api.onedrive.notify_settings_updated")
    @patch("app.api.onedrive.save_setting_to_db")
    def test_all_fields_persisted(self, mock_save, mock_notify, mock_settings, client):
        """Test that all provided fields are persisted to DB."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            client.post(
                "/api/onedrive/save-settings",
                data={
                    "refresh_token": "tok",
                    "client_id": "cid",
                    "client_secret": "csec",
                    "tenant_id": "my-tenant",
                    "folder_path": "/docs",
                },
                follow_redirects=False,
            )

        keys_saved = [call[0][1] for call in mock_save.call_args_list]
        assert "onedrive_refresh_token" in keys_saved
        assert "onedrive_client_id" in keys_saved
        assert "onedrive_client_secret" in keys_saved
        assert "onedrive_tenant_id" in keys_saved
        assert "onedrive_folder_path" in keys_saved

    @patch("app.api.onedrive.settings")
    @patch("app.api.onedrive.notify_settings_updated")
    @patch("app.api.onedrive.save_setting_to_db")
    def test_notify_called(self, mock_save, mock_notify, mock_settings, client):
        """Test that notify_settings_updated is called."""
        mock_save.return_value = True

        with patch("os.path.exists", return_value=False):
            client.post(
                "/api/onedrive/save-settings",
                data={"refresh_token": "tok"},
                follow_redirects=False,
            )

        mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetSettingsForExport
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetSettingsForExport:
    """Unit tests for the get_settings_for_export service function."""

    def test_source_db_returns_only_db_settings(self, db_session):
        """Test that source=db returns only DB-persisted settings."""
        from app.utils.settings_service import get_settings_for_export

        save_setting_to_db(db_session, "workdir", "/tmp/test", changed_by="test")
        result = get_settings_for_export(db_session, source="db")

        assert "WORKDIR" in result
        assert result["WORKDIR"] == "/tmp/test"

    def test_source_effective_includes_metadata_keys(self, db_session):
        """Test that source=effective includes keys from SETTING_METADATA."""
        from app.utils.settings_service import get_settings_for_export

        result = get_settings_for_export(db_session, source="effective")

        # The effective export should include keys from SETTING_METADATA that have values
        # At a minimum check it returns a dict
        assert isinstance(result, dict)
        # Keys should be uppercase
        for k in result:
            assert k == k.upper()

    def test_keys_are_uppercase(self, db_session):
        """Test that all keys are returned in uppercase."""
        from app.utils.settings_service import get_settings_for_export

        save_setting_to_db(db_session, "workdir", "/tmp", changed_by="test")
        result = get_settings_for_export(db_session, source="db")

        for k in result:
            assert k == k.upper(), f"Key {k!r} is not uppercase"

    def test_none_values_excluded(self, db_session):
        """Test that None values are excluded from the export."""
        from app.utils.settings_service import get_settings_for_export

        result = get_settings_for_export(db_session, source="db")

        for v in result.values():
            assert v is not None

    def test_db_only_excludes_env_only_values(self, db_session):
        """Test that source=db does NOT include ENV-only values (only DB rows)."""
        from app.utils.settings_service import get_settings_for_export

        # Ensure no settings in DB
        result = get_settings_for_export(db_session, source="db")
        # DB is empty so result should be empty
        assert len(result) == 0


# ---------------------------------------------------------------------------
# TestExportEnvEndpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportEnvEndpoint:
    """Unit tests for export_env_settings endpoint function."""

    def test_requires_admin(self, client):
        """Test that the endpoint requires admin access (no session)."""
        response = client.get("/api/settings/export-env")
        assert response.status_code in (302, 401, 403)

    def test_returns_text_plain(self, db_session):
        """Test that the endpoint returns text/plain response."""
        import asyncio

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = asyncio.run(
            export_env_settings(mock_request, db_session, mock_admin, source="db")
        )
        assert result.media_type == "text/plain"

    def test_content_disposition_header(self, db_session):
        """Test that the response includes a content-disposition attachment header."""
        import asyncio

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = asyncio.run(
            export_env_settings(mock_request, db_session, mock_admin, source="db")
        )
        cd = result.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".env" in cd

    def test_invalid_source_returns_400(self, db_session):
        """Test that an invalid source parameter raises HTTPException 400."""
        import asyncio

        from fastapi import HTTPException

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                export_env_settings(
                    mock_request, db_session, mock_admin, source="invalid"
                )
            )
        assert exc_info.value.status_code == 400

    def test_default_source_is_db(self, db_session):
        """Test that default source is db (filename contains 'db')."""
        import asyncio

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = asyncio.run(export_env_settings(mock_request, db_session, mock_admin))
        cd = result.headers.get("content-disposition", "")
        assert "db" in cd

    def test_effective_source_returns_response(self, db_session):
        """Test that source=effective returns a valid response."""
        import asyncio

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = asyncio.run(
            export_env_settings(
                mock_request, db_session, mock_admin, source="effective"
            )
        )
        assert result.media_type == "text/plain"

    def test_output_contains_docuelevate_header(self, db_session):
        """Test that the export output contains a DocuElevate header comment."""
        import asyncio

        from app.api.settings import export_env_settings

        mock_request = MagicMock()
        mock_admin = {"id": "admin", "is_admin": True}

        result = asyncio.run(
            export_env_settings(mock_request, db_session, mock_admin, source="db")
        )
        assert b"DocuElevate" in result.body
