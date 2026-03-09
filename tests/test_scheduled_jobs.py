"""
Tests for the scheduled batch processing feature.

Covers:
- app/tasks/batch_tasks.py  – all 8 batch Celery tasks
- app/api/scheduled_jobs.py – list, update, run-now API endpoints
- app/views/scheduled_jobs.py – admin view route
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import (
    FileRecord,
    InAppNotification,
    ProcessingLog,
    ScheduledJob,
    SettingsAuditLog,
    SharedLink,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sj_engine():
    """In-memory SQLite engine for scheduled-jobs tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def sj_session(sj_engine):
    """DB session scoped to one test."""
    Session = sessionmaker(bind=sj_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def sj_client(sj_engine):
    """TestClient with an in-memory DB and admin override."""
    from app.api.scheduled_jobs import _require_admin
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=sj_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_admin():
        return {"email": "admin@example.com", "is_admin": True}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[_require_admin] = override_admin

    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture()
def sj_client_no_admin(sj_engine):
    """TestClient with an in-memory DB and no admin override."""
    from app.main import app

    def override_db():
        Session = sessionmaker(bind=sj_engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


def _make_job(session, name="test-job", enabled=True, schedule_type="cron") -> ScheduledJob:
    job = ScheduledJob(
        name=name,
        display_name="Test Job",
        description="A test job",
        task_name="app.tasks.batch_tasks.cleanup_temp_files",
        enabled=enabled,
        schedule_type=schedule_type,
        cron_minute="0",
        cron_hour="*",
        cron_day_of_week="*",
        cron_day_of_month="*",
        cron_month_of_year="*",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _make_file_record(session, **kwargs) -> FileRecord:
    """Insert a minimal FileRecord for testing."""
    defaults = dict(
        filehash="abc123",
        original_filename="test.pdf",
        local_filename="/tmp/test.pdf",
        file_size=1024,
        mime_type="application/pdf",
        is_duplicate=False,
        owner_id=None,
        ocr_text=None,
        ai_metadata=None,
    )
    defaults.update(kwargs)
    record = FileRecord(**defaults)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


# ===========================================================================
# API tests
# ===========================================================================


@pytest.mark.unit
class TestListScheduledJobs:
    """Tests for GET /api/admin/scheduled-jobs."""

    def test_returns_empty_list(self, sj_client):
        """Returns empty list when no jobs exist."""
        response = sj_client.get("/api/admin/scheduled-jobs")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_jobs(self, sj_client, sj_session):
        """Returns all jobs ordered by display_name."""
        job = _make_job(sj_session)
        response = sj_client.get("/api/admin/scheduled-jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == job.name
        assert data[0]["enabled"] is True

    def test_requires_admin(self, sj_client_no_admin):
        """Non-admin request receives 403."""
        response = sj_client_no_admin.get("/api/admin/scheduled-jobs")
        assert response.status_code == 403


@pytest.mark.unit
class TestUpdateScheduledJob:
    """Tests for PATCH /api/admin/scheduled-jobs/{id}."""

    def test_enable_disable_job(self, sj_client, sj_session):
        """PATCH can toggle the enabled flag."""
        job = _make_job(sj_session, enabled=True)
        response = sj_client.patch(f"/api/admin/scheduled-jobs/{job.id}", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    def test_update_cron_schedule(self, sj_client, sj_session):
        """PATCH can update cron fields."""
        job = _make_job(sj_session)
        payload = {
            "schedule_type": "cron",
            "cron_minute": "30",
            "cron_hour": "6",
            "cron_day_of_week": "*",
            "cron_day_of_month": "*",
            "cron_month_of_year": "*",
        }
        response = sj_client.patch(f"/api/admin/scheduled-jobs/{job.id}", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["cron_minute"] == "30"
        assert body["cron_hour"] == "6"

    def test_update_interval_schedule(self, sj_client, sj_session):
        """PATCH can switch to interval schedule."""
        job = _make_job(sj_session)
        response = sj_client.patch(
            f"/api/admin/scheduled-jobs/{job.id}",
            json={"schedule_type": "interval", "interval_seconds": 3600},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["schedule_type"] == "interval"
        assert body["interval_seconds"] == 3600

    def test_returns_404_for_missing_job(self, sj_client):
        """Returns 404 when the job ID does not exist."""
        response = sj_client.patch("/api/admin/scheduled-jobs/9999", json={"enabled": False})
        assert response.status_code == 404

    def test_returns_400_for_empty_payload(self, sj_client, sj_session):
        """Returns 400 when no updatable fields are provided."""
        job = _make_job(sj_session)
        response = sj_client.patch(f"/api/admin/scheduled-jobs/{job.id}", json={})
        assert response.status_code == 400

    def test_rejects_invalid_schedule_type(self, sj_client, sj_session):
        """Returns 422 when schedule_type is not 'cron' or 'interval'."""
        job = _make_job(sj_session)
        response = sj_client.patch(f"/api/admin/scheduled-jobs/{job.id}", json={"schedule_type": "invalid"})
        assert response.status_code == 422


@pytest.mark.unit
class TestRunScheduledJobNow:
    """Tests for POST /api/admin/scheduled-jobs/{id}/run-now."""

    def test_dispatches_task(self, sj_client, sj_session):
        """run-now sends the task and returns a task_id."""
        job = _make_job(sj_session)
        mock_async_result = MagicMock()
        mock_async_result.id = "fake-task-id-123"

        with patch("app.celery_app.celery.send_task", return_value=mock_async_result):
            response = sj_client.post(f"/api/admin/scheduled-jobs/{job.id}/run-now")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "dispatched"
        assert body["task_id"] == "fake-task-id-123"
        assert body["job_name"] == job.name

    def test_returns_404_for_missing_job(self, sj_client):
        """Returns 404 when job ID does not exist."""
        response = sj_client.post("/api/admin/scheduled-jobs/9999/run-now")
        assert response.status_code == 404


# ===========================================================================
# View tests
# ===========================================================================


@pytest.mark.unit
class TestScheduledJobsView:
    """Tests for app/views/scheduled_jobs.py."""

    def test_redirects_non_admin_to_home(self):
        """View redirects to '/' when user is not an admin."""
        from app.views.scheduled_jobs import scheduled_jobs_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com", "is_admin": False}}

        import asyncio

        result = asyncio.run(scheduled_jobs_page(mock_request))
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    def test_redirects_when_no_user_in_session(self):
        """View redirects to '/' when no user is in session."""
        from app.views.scheduled_jobs import scheduled_jobs_page

        mock_request = MagicMock()
        mock_request.session = {}

        import asyncio

        result = asyncio.run(scheduled_jobs_page(mock_request))
        assert result.status_code == 302

    def test_returns_template_for_admin(self):
        """View returns the scheduled_jobs template for an admin user."""
        from app.views.scheduled_jobs import scheduled_jobs_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}
        mock_template_response = MagicMock()

        with patch("app.views.scheduled_jobs.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = mock_template_response
            import asyncio

            result = asyncio.run(scheduled_jobs_page(mock_request))

        mock_templates.TemplateResponse.assert_called_once()
        call_args = mock_templates.TemplateResponse.call_args[0]
        assert call_args[0] == "admin_scheduled_jobs.html"
        assert result is mock_template_response

    def test_raises_500_on_template_error(self):
        """View raises HTTPException 500 when template rendering fails."""
        from app.views.scheduled_jobs import scheduled_jobs_page

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}

        with patch("app.views.scheduled_jobs.templates") as mock_templates:
            mock_templates.TemplateResponse.side_effect = RuntimeError("Template not found")
            import asyncio

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(scheduled_jobs_page(mock_request))

        assert exc_info.value.status_code == 500
        assert "Failed to load scheduled jobs page" in exc_info.value.detail


# ===========================================================================
# seed_default_scheduled_jobs tests
# ===========================================================================


@pytest.mark.unit
class TestSeedDefaultScheduledJobs:
    """Tests for seed_default_scheduled_jobs utility."""

    def test_seeds_all_default_jobs(self, sj_session):
        """All DEFAULT_JOBS entries are created on first call."""
        from app.api.scheduled_jobs import DEFAULT_JOBS, seed_default_scheduled_jobs

        seed_default_scheduled_jobs(sj_session)
        count = sj_session.query(ScheduledJob).count()
        assert count == len(DEFAULT_JOBS)

    def test_is_idempotent(self, sj_session):
        """Calling seed twice does not create duplicate entries."""
        from app.api.scheduled_jobs import DEFAULT_JOBS, seed_default_scheduled_jobs

        seed_default_scheduled_jobs(sj_session)
        seed_default_scheduled_jobs(sj_session)
        count = sj_session.query(ScheduledJob).count()
        assert count == len(DEFAULT_JOBS)

    def test_default_jobs_are_enabled(self, sj_session):
        """All seeded jobs are enabled by default."""
        from app.api.scheduled_jobs import seed_default_scheduled_jobs

        seed_default_scheduled_jobs(sj_session)
        disabled = sj_session.query(ScheduledJob).filter(ScheduledJob.enabled.is_(False)).count()
        assert disabled == 0

    def test_default_jobs_cover_all_batch_tasks(self, sj_session):
        """All 8 batch tasks are represented in the default job list."""
        from app.api.scheduled_jobs import DEFAULT_JOBS

        task_names = {j["task_name"] for j in DEFAULT_JOBS}
        expected = {
            "app.tasks.batch_tasks.process_new_documents",
            "app.tasks.batch_tasks.reprocess_failed_documents",
            "app.tasks.batch_tasks.cleanup_temp_files",
            "app.tasks.batch_tasks.expire_shared_links",
            "app.tasks.batch_tasks.prune_processing_logs",
            "app.tasks.batch_tasks.prune_old_notifications",
            "app.tasks.batch_tasks.backfill_missing_metadata",
            "app.tasks.batch_tasks.sync_search_index",
        }
        assert expected == task_names


# ===========================================================================
# Batch task tests
# ===========================================================================


@pytest.mark.unit
class TestProcessNewDocuments:
    """Tests for batch_tasks.process_new_documents."""

    def test_returns_success_with_no_candidates(self, sj_engine):
        """Returns success with zero queued when no new files exist."""
        from app.tasks.batch_tasks import process_new_documents

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = process_new_documents()
            real_session.close()

        assert result["queued"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_handles_db_exception(self):
        """DB exceptions are caught and job status is set to failed."""
        from app.tasks.batch_tasks import process_new_documents

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB error"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = process_new_documents()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"

    def test_skips_file_with_missing_path(self, sj_engine):
        """Files whose local_filename does not exist on disk are counted as skipped."""
        from app.tasks.batch_tasks import process_new_documents

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(session, filehash="hash_no_file", local_filename="/nonexistent/path.pdf")
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = process_new_documents()
            real_session.close()

        assert result["skipped"] == 1
        assert result["queued"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"


@pytest.mark.unit
class TestReprocessFailedDocuments:
    """Tests for batch_tasks.reprocess_failed_documents."""

    def test_returns_success_with_no_failed_files(self, sj_engine):
        """Returns success with zero queued when no files have failed steps."""
        from app.tasks.batch_tasks import reprocess_failed_documents

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = reprocess_failed_documents()
            real_session.close()

        assert result["queued"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_handles_exception(self):
        """DB exception sets status to failed."""
        from app.tasks.batch_tasks import reprocess_failed_documents

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = reprocess_failed_documents()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestCleanupTempFiles:
    """Tests for batch_tasks.cleanup_temp_files."""

    def test_deletes_old_unprotected_file(self, tmp_path):
        """Old, unreferenced files in workdir/tmp are deleted."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        old_file = tmp_dir / "old.pdf"
        old_file.write_bytes(b"data")

        # Back-date the modification time by 48 hours.
        old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        os.utime(old_file, (old_mtime, old_mtime))

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert result["deleted"] == 1
        assert not old_file.exists()

    def test_skips_new_files(self, tmp_path):
        """Files younger than max_age_hours are not deleted."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        new_file = tmp_dir / "new.pdf"
        new_file.write_bytes(b"data")

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert result["skipped"] >= 1
        assert new_file.exists()

    def test_missing_tmp_dir(self, tmp_path):
        """Returns success immediately when workdir/tmp does not exist."""
        from app.tasks.batch_tasks import cleanup_temp_files

        with (
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path / "nonexistent")
            result = cleanup_temp_files()

        assert result["deleted"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_skips_protected_file(self, tmp_path):
        """Files referenced by in-progress steps are not deleted."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        protected = tmp_dir / "protected.pdf"
        protected.write_bytes(b"data")

        old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        os.utime(protected, (old_mtime, old_mtime))

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)

            in_progress_row = MagicMock()
            in_progress_row.local_filename = str(protected)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = [
                in_progress_row
            ]
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert protected.exists()
        assert result["deleted"] == 0


@pytest.mark.unit
class TestExpireSharedLinks:
    """Tests for batch_tasks.expire_shared_links."""

    def test_revokes_expired_links(self, sj_engine):
        """Links whose expires_at is in the past are revoked."""
        from app.tasks.batch_tasks import expire_shared_links

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        # SharedLink.file_id is NOT NULL — create a file record first.
        file_rec = _make_file_record(session, filehash="hash_sl_expire")
        link = SharedLink(
            token="abc123token",
            file_id=file_rec.id,
            owner_id="user1",
            is_active=True,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(link)
        session.commit()
        link_id = link.id
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = expire_shared_links()
            real_session.close()

        assert result["revoked"] == 1
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

        check = sessionmaker(bind=sj_engine)()
        updated = check.query(SharedLink).filter(SharedLink.id == link_id).first()
        assert updated.is_active is False
        assert updated.revoked_at is not None
        check.close()

    def test_does_not_touch_active_links(self, sj_engine):
        """Links with no expires_at are not affected."""
        from app.tasks.batch_tasks import expire_shared_links

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        file_rec = _make_file_record(session, filehash="hash_sl_active")
        link = SharedLink(token="neverexpires", file_id=file_rec.id, owner_id="u1", is_active=True, expires_at=None)
        session.add(link)
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = expire_shared_links()
            real_session.close()

        assert result["revoked"] == 0

    def test_handles_exception(self):
        """DB exception sets status to failed."""
        from app.tasks.batch_tasks import expire_shared_links

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = expire_shared_links()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestPruneProcessingLogs:
    """Tests for batch_tasks.prune_processing_logs."""

    def test_deletes_old_logs(self, sj_engine):
        """Old processing_log and audit_log rows are deleted."""
        from app.tasks.batch_tasks import prune_processing_logs

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        old_ts = datetime.now(timezone.utc) - timedelta(days=40)
        for _ in range(3):
            session.add(ProcessingLog(file_id=None, task_id="t1", step_name="ocr", status="success", timestamp=old_ts))
        for _ in range(2):
            session.add(
                SettingsAuditLog(
                    key="k", old_value="a", new_value="b", changed_by="admin", action="update", changed_at=old_ts
                )
            )
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_processing_logs(retention_days=30)
            real_session.close()

        assert result["processing_logs_deleted"] == 3
        assert result["audit_log_deleted"] == 2
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_keeps_recent_logs(self, sj_engine):
        """Logs within the retention window are not deleted."""
        from app.tasks.batch_tasks import prune_processing_logs

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        recent_ts = datetime.now(timezone.utc) - timedelta(days=5)
        session.add(ProcessingLog(file_id=None, task_id="t2", step_name="ocr", status="success", timestamp=recent_ts))
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_processing_logs(retention_days=30)
            real_session.close()

        assert result["processing_logs_deleted"] == 0

    def test_handles_exception(self):
        """DB exception sets status to failed."""
        from app.tasks.batch_tasks import prune_processing_logs

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_processing_logs()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestPruneOldNotifications:
    """Tests for batch_tasks.prune_old_notifications."""

    def test_deletes_old_read_notifications(self, sj_engine):
        """Old read notifications are deleted."""
        from app.tasks.batch_tasks import prune_old_notifications

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        old_ts = datetime.now(timezone.utc) - timedelta(days=40)
        for _ in range(4):
            session.add(
                InAppNotification(
                    owner_id="u1", event_type="document.processed", title="Done", is_read=True, created_at=old_ts
                )
            )
        session.add(
            InAppNotification(
                owner_id="u1", event_type="document.processed", title="Unread", is_read=False, created_at=old_ts
            )
        )
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_old_notifications(retention_days=30)
            real_session.close()

        assert result["deleted"] == 4
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_keeps_unread_notifications(self, sj_engine):
        """Unread notifications are never deleted."""
        from app.tasks.batch_tasks import prune_old_notifications

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        old_ts = datetime.now(timezone.utc) - timedelta(days=40)
        session.add(
            InAppNotification(
                owner_id="u1", event_type="document.failed", title="Unread", is_read=False, created_at=old_ts
            )
        )
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_old_notifications(retention_days=30)
            real_session.close()

        assert result["deleted"] == 0

    def test_handles_exception(self):
        """DB exception sets status to failed."""
        from app.tasks.batch_tasks import prune_old_notifications

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = prune_old_notifications()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestBackfillMissingMetadata:
    """Tests for batch_tasks.backfill_missing_metadata."""

    def test_queues_files_with_missing_metadata(self, sj_engine):
        """Files with OCR text but no AI metadata are queued."""
        from app.tasks.batch_tasks import backfill_missing_metadata

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(session, filehash="hash_meta", ocr_text="Some extracted text", ai_metadata=None)
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_extract.delay = MagicMock()
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = backfill_missing_metadata(batch_size=10)
            real_session.close()

        assert result["queued"] == 1
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_skips_files_with_existing_metadata(self, sj_engine):
        """Files that already have ai_metadata are not queued."""
        from app.tasks.batch_tasks import backfill_missing_metadata

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(session, filehash="hash_has_meta", ocr_text="text", ai_metadata='{"document_type":"invoice"}')
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_extract,
        ):
            mock_extract.delay = MagicMock()
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = backfill_missing_metadata(batch_size=10)
            real_session.close()

        assert result["queued"] == 0

    def test_handles_exception(self):
        """DB exception sets status to failed."""
        from app.tasks.batch_tasks import backfill_missing_metadata

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("fail"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = backfill_missing_metadata()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestSyncSearchIndex:
    """Tests for batch_tasks.sync_search_index."""

    def test_skips_when_meilisearch_not_configured(self):
        """Returns success immediately when Meilisearch is not configured."""
        from app.tasks.batch_tasks import sync_search_index

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=None),
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            result = sync_search_index()

        assert result["indexed"] == 0
        assert result.get("reason") == "meilisearch_not_configured"
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_indexes_missing_documents(self, sj_engine):
        """Documents missing from the index are sent to Meilisearch."""
        from app.tasks.batch_tasks import sync_search_index

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(
            session, filehash="hash_search", ocr_text="searchable text", ai_metadata='{"document_type":"invoice"}'
        )
        session.close()

        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        get_docs_result = MagicMock()
        get_docs_result.results = []
        mock_index.get_documents.return_value = get_docs_result

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client),
            patch("app.utils.meilisearch_client.index_document", return_value=True) as mock_idx,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.meilisearch_index_name = "documents"
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = sync_search_index(batch_size=10)
            real_session.close()

        assert result["indexed"] == 1
        mock_idx.assert_called_once()
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_handles_meilisearch_fetch_error(self):
        """Error fetching existing IDs from Meilisearch results in failed status."""
        from app.tasks.batch_tasks import sync_search_index

        mock_client = MagicMock()
        mock_client.get_index.side_effect = RuntimeError("Connection refused")

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client),
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.meilisearch_index_name = "documents"
            result = sync_search_index()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


# ===========================================================================
# _update_job_status helper tests
# ===========================================================================


@pytest.mark.unit
class TestUpdateJobStatus:
    """Tests for the _update_job_status helper."""

    def test_updates_existing_job(self, sj_session):
        """_update_job_status sets last_run_at/status/detail on an existing job."""
        from app.tasks.batch_tasks import _update_job_status

        job = _make_job(sj_session, name="test-update-status")

        with patch("app.tasks.batch_tasks.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = job
            mock_sl.return_value = mock_db

            _update_job_status("test-update-status", "success", "Done.")

        assert job.last_run_status == "success"
        assert job.last_run_detail == "Done."

    def test_silently_handles_missing_job(self):
        """_update_job_status does not raise when the job does not exist."""
        from app.tasks.batch_tasks import _update_job_status

        with patch("app.tasks.batch_tasks.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_sl.return_value = mock_db

            # Should not raise.
            _update_job_status("nonexistent-job", "success", "Done.")


# ===========================================================================
# Additional coverage tests
# ===========================================================================


@pytest.mark.unit
class TestRequireAdminSuccess:
    """Tests for the _require_admin success path."""

    def test_returns_user_for_admin(self):
        """_require_admin returns the user dict when the user is an admin."""
        from app.api.scheduled_jobs import _require_admin

        admin_user = {"email": "admin@example.com", "is_admin": True}
        mock_request = MagicMock()
        mock_request.session = {"user": admin_user}

        result = _require_admin(mock_request)
        assert result == admin_user


@pytest.mark.unit
class TestSeedDefaultScheduledJobsErrors:
    """Tests for error handling in seed_default_scheduled_jobs."""

    def test_rolls_back_on_db_error(self, sj_session):
        """seed_default_scheduled_jobs rolls back and logs on commit failure."""
        from app.api.scheduled_jobs import seed_default_scheduled_jobs

        with patch.object(sj_session, "commit", side_effect=RuntimeError("DB commit error")):
            with patch("app.api.scheduled_jobs.logger") as mock_logger:
                seed_default_scheduled_jobs(sj_session)
                mock_logger.error.assert_called_once()


@pytest.mark.unit
class TestUpdateScheduledJobErrors:
    """Tests for update_scheduled_job DB error handling."""

    def test_returns_500_on_commit_failure(self, sj_session):
        """Returns 500 when the DB commit fails during update."""
        from fastapi import HTTPException

        from app.api.scheduled_jobs import ScheduledJobUpdate, update_scheduled_job

        job = _make_job(sj_session, name="job-to-fail")

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}

        # Patch the session's commit to raise after the job is found.
        with patch.object(sj_session, "commit", side_effect=RuntimeError("commit error")):
            with pytest.raises(HTTPException) as exc_info:
                update_scheduled_job(
                    job_id=job.id,
                    payload=ScheduledJobUpdate(enabled=False),
                    request=mock_request,
                    db=sj_session,
                    _admin={"email": "admin@example.com", "is_admin": True},
                )

        assert exc_info.value.status_code == 500
        assert "Failed to update scheduled job" in exc_info.value.detail


@pytest.mark.unit
class TestProcessNewDocumentsQueuing:
    """Tests for the file-queuing path of process_new_documents."""

    def test_queues_file_that_exists(self, sj_engine, tmp_path):
        """A file with no processing steps whose path exists is queued."""
        from app.tasks.batch_tasks import process_new_documents

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        real_file = tmp_path / "real.pdf"
        real_file.write_bytes(b"%PDF")
        _make_file_record(session, filehash="hash_real_q", local_filename=str(real_file))
        session.close()

        dispatched = []

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            # Patch process_document.delay inside the function module.
            with patch("app.tasks.process_document.process_document") as mock_pd:
                mock_pd.delay = MagicMock(side_effect=lambda *a, **kw: dispatched.append((a, kw)))
                result = process_new_documents()

            real_session.close()

        # The file has no steps so it should be queued.
        assert result["queued"] == 1
        assert result["skipped"] == 0


@pytest.mark.unit
class TestReprocessFailedDocumentsQueuing:
    """Tests for the file-queuing path of reprocess_failed_documents."""

    def test_queues_failed_file_that_exists(self, sj_engine, tmp_path):
        """A file with a failed step whose path exists is re-queued."""
        from app.tasks.batch_tasks import reprocess_failed_documents

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        real_file = tmp_path / "fail.pdf"
        real_file.write_bytes(b"%PDF")
        record = _make_file_record(session, filehash="hash_fail_q", local_filename=str(real_file))

        # Add a failed processing step.
        from app.models import FileProcessingStep

        step = FileProcessingStep(
            file_id=record.id,
            step_name="extract_metadata_with_gpt",
            status="failure",
        )
        session.add(step)
        session.commit()
        session.close()

        dispatched = []

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            with patch("app.tasks.process_document.process_document") as mock_pd:
                mock_pd.delay = MagicMock(side_effect=lambda *a, **kw: dispatched.append((a, kw)))
                result = reprocess_failed_documents()

            real_session.close()

        assert result["queued"] == 1
        assert result["skipped"] == 0


@pytest.mark.unit
class TestCleanupTempFilesEdgeCases:
    """Additional edge-case tests for cleanup_temp_files."""

    def test_increments_errors_on_unlink_failure(self, tmp_path):
        """OSError during file deletion increments the errors counter."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        old_file = tmp_dir / "locked.pdf"
        old_file.write_bytes(b"data")

        old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        os.utime(old_file, (old_mtime, old_mtime))

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
            patch("pathlib.Path.unlink", side_effect=OSError("Permission denied")),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert result["errors"] == 1
        assert result["deleted"] == 0
        # When errors > 0 and deleted == 0, status should be "failed".
        mock_update.assert_called_once_with(
            "cleanup-temp-files", "failed", pytest.approx(mock_update.call_args[0][2], abs=1e9)
        )

    def test_status_success_when_both_deleted_and_errors(self, tmp_path):
        """Status is 'success' when at least one file was deleted even if some had errors."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()

        for name in ["good.pdf", "bad.pdf"]:
            f = tmp_dir / name
            f.write_bytes(b"data")
            old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
            os.utime(f, (old_mtime, old_mtime))

        # First unlink call succeeds (returns None); second raises OSError.
        unlink_calls = {"n": 0}

        def side_effect(*_args, **_kwargs):
            unlink_calls["n"] += 1
            if unlink_calls["n"] > 1:
                raise OSError("Permission denied")

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
            patch("pathlib.Path.unlink", side_effect=side_effect),
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        # deleted=1, errors=1 → status must be "success" (errors only → "failed").
        assert result["deleted"] == 1
        assert result["errors"] == 1
        assert mock_update.call_args[0][1] == "success"

    def test_skips_non_file_entries(self, tmp_path):
        """Subdirectories inside workdir/tmp are skipped (not counted as deleted)."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        subdir = tmp_dir / "subdir"
        subdir.mkdir()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert result["deleted"] == 0
        assert subdir.exists()

    def test_outer_exception_returns_error_dict(self, tmp_path):
        """An unexpected exception in cleanup returns an error dict and sets status failed."""
        from app.tasks.batch_tasks import cleanup_temp_files

        with (
            patch("app.tasks.batch_tasks.SessionLocal", side_effect=RuntimeError("session error")),
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            # Make tmp_dir exist so the early-return doesn't fire.
            (tmp_path / "tmp").mkdir()
            result = cleanup_temp_files(max_age_hours=24)

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestSyncSearchIndexAdditional:
    """Additional coverage tests for sync_search_index."""

    def test_counts_skipped_on_indexing_failure(self, sj_engine):
        """When index_document returns False, the document is counted as skipped."""
        from app.tasks.batch_tasks import sync_search_index

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(session, filehash="hash_idx_fail", ocr_text="text", ai_metadata=None)
        session.close()

        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        get_docs_result = MagicMock()
        get_docs_result.results = []
        mock_index.get_documents.return_value = get_docs_result

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client),
            patch("app.utils.meilisearch_client.index_document", return_value=False),
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.meilisearch_index_name = "documents"
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = sync_search_index(batch_size=10)
            real_session.close()

        assert result["skipped"] == 1
        assert result["indexed"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"

    def test_handles_invalid_ai_metadata_json(self, sj_engine):
        """Invalid ai_metadata JSON is handled gracefully — metadata defaults to {}."""
        from app.tasks.batch_tasks import sync_search_index

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        _make_file_record(
            session,
            filehash="hash_bad_json",
            ocr_text="some text",
            ai_metadata="{invalid-json}",
        )
        session.close()

        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        get_docs_result = MagicMock()
        get_docs_result.results = []
        mock_index.get_documents.return_value = get_docs_result

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client),
            patch("app.utils.meilisearch_client.index_document", return_value=True) as mock_idx,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.meilisearch_index_name = "documents"
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = sync_search_index(batch_size=10)
            real_session.close()

        # The record should still be indexed with empty metadata.
        assert result["indexed"] == 1
        call_args = mock_idx.call_args
        assert call_args[0][2] == {}  # metadata is empty dict
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"


@pytest.mark.unit
class TestReprocessFailedDocumentsMissingFile:
    """Test reprocess_failed_documents when file exists as candidate but not on disk."""

    def test_skips_failed_file_with_missing_path(self, sj_engine):
        """A file with a failed step but no file on disk is counted as skipped."""
        from app.tasks.batch_tasks import reprocess_failed_documents

        Session = sessionmaker(bind=sj_engine)
        session = Session()
        record = _make_file_record(
            session,
            filehash="hash_fail_skip",
            local_filename="/nonexistent/fail.pdf",
        )
        from app.models import FileProcessingStep

        step = FileProcessingStep(
            file_id=record.id,
            step_name="extract_metadata_with_gpt",
            status="failure",
        )
        session.add(step)
        session.commit()
        session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
        ):
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = reprocess_failed_documents()
            real_session.close()

        assert result["skipped"] == 1
        assert result["queued"] == 0
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "success"


@pytest.mark.unit
class TestCleanupTempFilesProtectedByActivity:
    """Tests for cleanup_temp_files protection via in-progress and active tmp records."""

    def test_protects_file_referenced_by_in_progress_step(self, tmp_path, sj_engine):
        """A file with an in-progress step is not deleted."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        protected = tmp_dir / "inprogress.pdf"
        protected.write_bytes(b"data")
        old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        os.utime(protected, (old_mtime, old_mtime))

        Session = sessionmaker(bind=sj_engine)()
        record = _make_file_record(
            Session,
            filehash="hash_ip",
            local_filename=str(protected),
        )
        from app.models import FileProcessingStep

        step = FileProcessingStep(
            file_id=record.id,
            step_name="extract_text",
            status="in_progress",
        )
        Session.add(step)
        Session.commit()
        Session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = cleanup_temp_files(max_age_hours=24)
            real_session.close()

        # File should NOT have been deleted.
        assert protected.exists()
        assert result["deleted"] == 0

    def test_protects_file_referenced_by_active_tmp_record(self, tmp_path, sj_engine):
        """A file listed in FileRecord.local_filename pointing into tmp is not deleted."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        active_file = tmp_dir / "active.pdf"
        active_file.write_bytes(b"data")
        old_mtime = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
        os.utime(active_file, (old_mtime, old_mtime))

        Session = sessionmaker(bind=sj_engine)()
        _make_file_record(
            Session,
            filehash="hash_active_tmp",
            local_filename=str(active_file),
        )
        Session.close()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            real_session = sessionmaker(bind=sj_engine)()
            mock_sl.return_value.__enter__ = MagicMock(return_value=real_session)
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            result = cleanup_temp_files(max_age_hours=24)
            real_session.close()

        assert active_file.exists()
        assert result["deleted"] == 0


@pytest.mark.unit
class TestSyncSearchIndexOuterException:
    """Tests for the outer exception handler in sync_search_index."""

    def test_handles_exception_during_db_query(self):
        """If the DB query itself raises, the outer except sets status failed."""
        from app.tasks.batch_tasks import sync_search_index

        mock_client = MagicMock()
        mock_index = MagicMock()
        mock_client.get_index.return_value = mock_index
        get_docs_result = MagicMock()
        get_docs_result.results = []
        mock_index.get_documents.return_value = get_docs_result

        with (
            patch("app.utils.meilisearch_client.get_meilisearch_client", return_value=mock_client),
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status") as mock_update,
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.meilisearch_index_name = "documents"
            # Make the DB query raise.
            mock_sl.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB down"))
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)

            result = sync_search_index()

        assert "error" in result
        mock_update.assert_called_once()
        assert mock_update.call_args[0][1] == "failed"


@pytest.mark.unit
class TestCleanupTempFilesNullLocalFilename:
    """Tests for null local_filename rows in cleanup_temp_files inner loops."""

    def _make_null_row(self):
        """Return a mock Row with local_filename=None (as SQLAlchemy returns for NULL cols)."""
        row = MagicMock()
        row.local_filename = None
        return row

    def test_skips_null_local_filename_in_in_progress_records(self, tmp_path):
        """In-progress rows with null local_filename do not crash and are ignored."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()

        null_row = self._make_null_row()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            # in_progress_records returns one row with local_filename=None.
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = [
                null_row
            ]
            # active_records returns empty.
            mock_db.query.return_value.filter.return_value.all.return_value = []
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        # No crash; the null row is simply ignored.
        assert result["deleted"] == 0

    def test_skips_null_local_filename_in_active_tmp_records(self, tmp_path):
        """Active-tmp rows with null local_filename do not crash and are ignored."""
        from app.tasks.batch_tasks import cleanup_temp_files

        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()

        null_row = self._make_null_row()

        with (
            patch("app.tasks.batch_tasks.SessionLocal") as mock_sl,
            patch("app.tasks.batch_tasks._update_job_status"),
            patch("app.tasks.batch_tasks.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_db = MagicMock()
            mock_db.__enter__ = MagicMock(return_value=mock_db)
            mock_db.__exit__ = MagicMock(return_value=False)
            # in_progress_records returns empty.
            mock_db.query.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []
            # active_records returns one row with local_filename=None.
            mock_db.query.return_value.filter.return_value.all.return_value = [null_row]
            mock_sl.return_value = mock_db

            result = cleanup_temp_files(max_age_hours=24)

        assert result["deleted"] == 0
