"""Tests for the system reset feature (app/api/system_reset.py, app/utils/system_reset.py, app/views/system_reset.py)."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    DocumentMetadata,
    FileProcessingStep,
    FileRecord,
    ProcessingLog,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_workdir():
    """Create a temporary workdir populated with sample user data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create data subdirectories with dummy files
        for subdir in ("original", "processed", "tmp", "pdfa", "backups"):
            d = Path(tmpdir) / subdir
            d.mkdir()
            (d / "sample.pdf").write_bytes(b"%PDF-1.4 fake")

        # Create cache files
        for cache in ("watch_folder_processed.json", "ftp_ingest_processed.json"):
            (Path(tmpdir) / cache).write_text("{}")

        # Create a per-user watch folder cache
        (Path(tmpdir) / "user_wf_42.json").write_text("{}")

        # Create a loose PDF in workdir root
        (Path(tmpdir) / "abc123.pdf").write_bytes(b"%PDF-1.4 loose")

        yield tmpdir


@pytest.fixture
def reset_db_session():
    """Fresh in-memory database with sample user data rows."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed with sample data
    fr = FileRecord(
        filehash="abc123",
        original_filename="test.pdf",
        local_filename="uuid.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    session.add(fr)
    session.flush()

    session.add(ProcessingLog(file_id=fr.id, task_id="t1", step_name="hash_file", status="success"))
    session.add(FileProcessingStep(file_id=fr.id, step_name="hash_file", status="success"))
    session.add(DocumentMetadata(filename="test.pdf", sender="Alice", recipient="Bob"))
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Unit tests for app/utils/system_reset.py
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWipeWorkdirData:
    """Tests for _wipe_workdir_data()."""

    def test_removes_data_subdirs(self, reset_workdir):
        from app.utils.system_reset import _wipe_workdir_data

        result = _wipe_workdir_data(reset_workdir)

        # All data subdirectories should be gone
        for subdir in ("original", "processed", "tmp", "pdfa", "backups"):
            assert not (Path(reset_workdir) / subdir).exists()

        assert result["deleted_dirs"] == 5

    def test_removes_cache_files(self, reset_workdir):
        from app.utils.system_reset import _wipe_workdir_data

        result = _wipe_workdir_data(reset_workdir)

        assert not (Path(reset_workdir) / "watch_folder_processed.json").exists()
        assert not (Path(reset_workdir) / "ftp_ingest_processed.json").exists()
        assert not (Path(reset_workdir) / "user_wf_42.json").exists()
        assert result["deleted_files"] >= 3

    def test_removes_loose_document_files(self, reset_workdir):
        from app.utils.system_reset import _wipe_workdir_data

        _wipe_workdir_data(reset_workdir)
        assert not (Path(reset_workdir) / "abc123.pdf").exists()

    def test_preserves_workdir_directory(self, reset_workdir):
        from app.utils.system_reset import _wipe_workdir_data

        _wipe_workdir_data(reset_workdir)
        assert Path(reset_workdir).is_dir()

    def test_handles_empty_workdir(self):
        """No errors when workdir has no data dirs or caches."""
        from app.utils.system_reset import _wipe_workdir_data

        with tempfile.TemporaryDirectory() as empty_dir:
            result = _wipe_workdir_data(empty_dir)
            assert result["deleted_dirs"] == 0
            assert result["deleted_files"] == 0


@pytest.mark.unit
class TestWipeDatabase:
    """Tests for _wipe_database()."""

    def test_deletes_all_user_data(self, reset_db_session):
        from app.utils.system_reset import _wipe_database

        result = _wipe_database(reset_db_session)

        assert result.get("files", 0) >= 1
        assert result.get("processing_logs", 0) >= 1
        assert result.get("file_processing_steps", 0) >= 1
        assert result.get("document_metadata", 0) >= 1

    def test_tables_are_empty_after_wipe(self, reset_db_session):
        from app.utils.system_reset import _wipe_database

        _wipe_database(reset_db_session)

        assert reset_db_session.query(FileRecord).count() == 0
        assert reset_db_session.query(ProcessingLog).count() == 0
        assert reset_db_session.query(FileProcessingStep).count() == 0
        assert reset_db_session.query(DocumentMetadata).count() == 0


@pytest.mark.unit
class TestPerformFullReset:
    """Tests for perform_full_reset()."""

    def test_wipes_db_and_filesystem(self, reset_db_session, reset_workdir):
        from app.utils.system_reset import perform_full_reset

        with patch("app.utils.system_reset.settings") as mock_settings:
            mock_settings.workdir = reset_workdir
            result = perform_full_reset(reset_db_session)

        assert "database" in result
        assert "filesystem" in result
        assert reset_db_session.query(FileRecord).count() == 0
        assert not (Path(reset_workdir) / "original").exists()


@pytest.mark.unit
class TestPerformResetAndReimport:
    """Tests for perform_reset_and_reimport()."""

    def test_copies_originals_to_reimport_then_wipes(self, reset_db_session, reset_workdir):
        from app.utils.system_reset import perform_reset_and_reimport

        with patch("app.utils.system_reset.settings") as mock_settings:
            mock_settings.workdir = reset_workdir
            mock_settings.watch_folders = ""
            mock_settings.watch_folder_delete_after_process = False
            result = perform_reset_and_reimport(reset_db_session)

        reimport_dir = Path(reset_workdir) / "reimport"
        assert reimport_dir.is_dir()
        assert result["reimport"]["files_moved"] >= 1

        # DB should be wiped
        assert reset_db_session.query(FileRecord).count() == 0

        # Reimport folder should contain the original file
        reimport_files = list(reimport_dir.iterdir())
        assert len(reimport_files) >= 1

    def test_configures_watch_folder(self, reset_db_session, reset_workdir):
        from app.utils.system_reset import perform_reset_and_reimport

        with patch("app.utils.system_reset.settings") as mock_settings:
            mock_settings.workdir = reset_workdir
            mock_settings.watch_folders = "/some/other/folder"
            mock_settings.watch_folder_delete_after_process = False
            perform_reset_and_reimport(reset_db_session)

        reimport_path = str(Path(reset_workdir) / "reimport")
        # watch_folders should now include the reimport path
        assert reimport_path in mock_settings.watch_folders


@pytest.mark.unit
class TestStartupReset:
    """Tests for perform_startup_reset()."""

    def test_startup_reset_calls_full_reset(self):
        from app.utils.system_reset import perform_startup_reset

        with patch("app.utils.system_reset.perform_full_reset") as mock_reset:
            with patch("app.database.SessionLocal") as mock_sl:
                mock_db = mock_sl.return_value
                perform_startup_reset()

                mock_reset.assert_called_once_with(mock_db)
                mock_db.close.assert_called_once()

    def test_startup_reset_handles_errors(self):
        from app.utils.system_reset import perform_startup_reset

        with patch("app.utils.system_reset.perform_full_reset", side_effect=RuntimeError("boom")):
            with patch("app.database.SessionLocal") as mock_sl:
                mock_db = mock_sl.return_value
                # Should not raise
                perform_startup_reset()
                mock_db.rollback.assert_called_once()
                mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# Integration tests for API endpoints
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSystemResetApi:
    """Tests for the /api/admin/system-reset/ endpoints."""

    def test_full_reset_requires_admin(self, client):
        """Non-admin users get 403."""
        response = client.post(
            "/api/admin/system-reset/full",
            json={"confirmation": "DELETE"},
        )
        assert response.status_code == 403

    def test_full_reset_requires_feature_flag(self, client):
        """Returns 404 when ENABLE_FACTORY_RESET is false."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            with patch("app.api.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = False
                response = client.post(
                    "/api/admin/system-reset/full",
                    json={"confirmation": "DELETE"},
                )
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)
        assert response.status_code == 404

    def test_full_reset_requires_confirmation(self, client):
        """Wrong confirmation string gets 400."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            with patch("app.api.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = True
                response = client.post(
                    "/api/admin/system-reset/full",
                    json={"confirmation": "WRONG"},
                )
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)

        assert response.status_code == 400

    def test_reimport_requires_confirmation(self, client):
        """Wrong confirmation string gets 400."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            with patch("app.api.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = True
                response = client.post(
                    "/api/admin/system-reset/reimport",
                    json={"confirmation": "WRONG"},
                )
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)

        assert response.status_code == 400

    def test_status_endpoint(self, client):
        """The status endpoint returns feature-flag state."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            response = client.get("/api/admin/system-reset/status")
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "factory_reset_on_startup" in data

    def test_full_reset_success(self, client):
        """Full reset succeeds with correct confirmation and feature flag."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            with patch("app.api.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = True
                with patch(
                    "app.utils.system_reset.perform_full_reset", return_value={"database": {}, "filesystem": {}}
                ):
                    response = client.post(
                        "/api/admin/system-reset/full",
                        json={"confirmation": "DELETE"},
                    )
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_reimport_success(self, client):
        """Reimport succeeds with correct confirmation."""
        from app.api.system_reset import _require_admin

        client.app.dependency_overrides[_require_admin] = lambda: {"is_admin": True}
        try:
            with patch("app.api.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = True
                with patch(
                    "app.utils.system_reset.perform_reset_and_reimport",
                    return_value={"database": {}, "filesystem": {}, "reimport": {"files_moved": 3}},
                ):
                    response = client.post(
                        "/api/admin/system-reset/reimport",
                        json={"confirmation": "REIMPORT"},
                    )
        finally:
            client.app.dependency_overrides.pop(_require_admin, None)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Integration tests for the view
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSystemResetView:
    """Tests for the /admin/system-reset view."""

    def test_view_redirects_when_disabled(self, client):
        """When ENABLE_FACTORY_RESET=False, accessing the page redirects away."""
        with client:
            client.cookies.set("session", "test")
            with patch("app.views.system_reset.settings") as mock_s:
                mock_s.enable_factory_reset = False
                response = client.get("/admin/system-reset", follow_redirects=False)
        # Redirect to /settings (302) when disabled, or to login (302/307) when unauthenticated
        assert response.status_code in (302, 307)

    def test_view_requires_auth(self, client):
        """Unauthenticated users are redirected away from the page."""
        with patch("app.views.system_reset.settings") as mock_s:
            mock_s.enable_factory_reset = True
            mock_s.factory_reset_on_startup = False
            response = client.get("/admin/system-reset", follow_redirects=False)
        # Should redirect to login since there's no active session
        assert response.status_code in (302, 307)
