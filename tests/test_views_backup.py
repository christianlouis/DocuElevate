"""Tests for app/views/backup.py module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse

# ---------------------------------------------------------------------------
# backup_dashboard route
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBackupDashboard:
    """Unit tests for the backup_dashboard view handler."""

    def _make_admin_request(self):
        """Return a mock request with an admin user in session."""
        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "admin@example.com", "is_admin": True}}
        return mock_request

    def _make_mock_db(self, records=None):
        """Return a mock DB session whose query chain returns *records*."""
        if records is None:
            records = []
        mock_db = MagicMock()
        mock_db.query.return_value.order_by.return_value.limit.return_value.all.return_value = records
        return mock_db

    @pytest.mark.asyncio
    async def test_redirects_non_admin_to_home(self):
        """backup_dashboard redirects to '/' when user is not an admin."""
        from app.views.backup import backup_dashboard

        mock_request = MagicMock()
        mock_request.session = {"user": {"email": "user@example.com", "is_admin": False}}
        mock_db = self._make_mock_db()

        result = await backup_dashboard(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_redirects_when_no_user_in_session(self):
        """backup_dashboard redirects to '/' when no user is in the session."""
        from app.views.backup import backup_dashboard

        mock_request = MagicMock()
        mock_request.session = {}
        mock_db = self._make_mock_db()

        result = await backup_dashboard(mock_request, db=mock_db)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302

    @pytest.mark.asyncio
    async def test_returns_template_for_admin_empty_records(self):
        """backup_dashboard renders template with empty records and zero counts."""
        from app.views.backup import backup_dashboard

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=[])
        mock_template_response = MagicMock()

        with patch("app.views.backup.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = mock_template_response
            result = await backup_dashboard(mock_request, db=mock_db)

        assert result is mock_template_response
        mock_templates.TemplateResponse.assert_called_once()
        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        assert _tpl_name == "backup.html"
        assert context["request"] is mock_request
        assert context["records"] == []
        assert context["counts"] == {"hourly": 0, "daily": 0, "weekly": 0}
        assert context["total_size"] == 0

    @pytest.mark.asyncio
    async def test_counts_backup_types_correctly(self):
        """backup_dashboard counts records per backup_type (hourly/daily/weekly)."""
        from app.views.backup import backup_dashboard

        def _rec(btype):
            r = MagicMock()
            r.backup_type = btype
            r.local_path = None
            r.size_bytes = 100
            return r

        records = [
            _rec("hourly"),
            _rec("hourly"),
            _rec("daily"),
            _rec("weekly"),
            _rec("weekly"),
            _rec("weekly"),
        ]

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=records)

        with patch("app.views.backup.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await backup_dashboard(mock_request, db=mock_db)

        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        assert context["counts"] == {"hourly": 2, "daily": 1, "weekly": 3}

    @pytest.mark.asyncio
    async def test_unknown_backup_type_not_counted(self):
        """backup_dashboard ignores backup_type values not in hourly/daily/weekly."""
        from app.views.backup import backup_dashboard

        r = MagicMock()
        r.backup_type = "unknown_type"
        r.local_path = None
        r.size_bytes = 0
        records = [r]

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=records)

        with patch("app.views.backup.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = MagicMock()
            await backup_dashboard(mock_request, db=mock_db)

        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        assert context["counts"] == {"hourly": 0, "daily": 0, "weekly": 0}

    @pytest.mark.asyncio
    async def test_total_size_includes_existing_local_files(self):
        """backup_dashboard sums size_bytes only for records with an existing local_path."""
        from app.views.backup import backup_dashboard

        r_exists = MagicMock()
        r_exists.backup_type = "hourly"
        r_exists.local_path = "/tmp/backup_exists.db.gz"
        r_exists.size_bytes = 512

        r_missing = MagicMock()
        r_missing.backup_type = "daily"
        r_missing.local_path = "/tmp/backup_missing.db.gz"
        r_missing.size_bytes = 1024

        r_no_path = MagicMock()
        r_no_path.backup_type = "weekly"
        r_no_path.local_path = None
        r_no_path.size_bytes = 2048

        records = [r_exists, r_missing, r_no_path]
        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=records)

        def _fake_exists(path):
            return path == "/tmp/backup_exists.db.gz"

        with (
            patch("app.views.backup.templates") as mock_templates,
            patch("app.views.backup.os.path.exists", side_effect=_fake_exists),
        ):
            mock_templates.TemplateResponse.return_value = MagicMock()
            await backup_dashboard(mock_request, db=mock_db)

        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        # Only r_exists (512) should be counted; r_missing path doesn't exist; r_no_path has no path
        assert context["total_size"] == 512

    @pytest.mark.asyncio
    async def test_total_size_zero_when_no_local_files_exist(self):
        """backup_dashboard total_size is 0 when no local files are present."""
        from app.views.backup import backup_dashboard

        r = MagicMock()
        r.backup_type = "hourly"
        r.local_path = "/tmp/nonexistent.db.gz"
        r.size_bytes = 999

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=[r])

        with (
            patch("app.views.backup.templates") as mock_templates,
            patch("app.views.backup.os.path.exists", return_value=False),
        ):
            mock_templates.TemplateResponse.return_value = MagicMock()
            await backup_dashboard(mock_request, db=mock_db)

        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        assert context["total_size"] == 0

    @pytest.mark.asyncio
    async def test_template_context_contains_settings_values(self):
        """backup_dashboard passes all expected settings fields to the template."""
        from app.views.backup import backup_dashboard

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=[])

        with (
            patch("app.views.backup.templates") as mock_templates,
            patch("app.views.backup.settings") as mock_settings,
        ):
            mock_settings.backup_enabled = True
            mock_settings.backup_remote_destination = "s3"
            mock_settings.backup_retain_hourly = 48
            mock_settings.backup_retain_daily = 14
            mock_settings.backup_retain_weekly = 8
            mock_settings.version = "1.2.3"
            mock_templates.TemplateResponse.return_value = MagicMock()

            await backup_dashboard(mock_request, db=mock_db)

        _tpl_name, context = mock_templates.TemplateResponse.call_args[0]
        assert context["backup_enabled"] is True
        assert context["backup_remote_destination"] == "s3"
        assert context["backup_retain_hourly"] == 48
        assert context["backup_retain_daily"] == 14
        assert context["backup_retain_weekly"] == 8
        assert context["app_version"] == "1.2.3"

    @pytest.mark.asyncio
    async def test_raises_500_on_db_error(self):
        """backup_dashboard raises HTTPException 500 when the DB query fails."""
        from app.views.backup import backup_dashboard

        mock_request = self._make_admin_request()
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("DB connection lost")

        with pytest.raises(HTTPException) as exc_info:
            await backup_dashboard(mock_request, db=mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to load backup dashboard" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_logs_error_on_db_failure(self):
        """backup_dashboard logs an error when the DB query raises."""
        from app.views.backup import backup_dashboard

        mock_request = self._make_admin_request()
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("DB connection lost")

        with (
            patch("app.views.backup.logger") as mock_logger,
            pytest.raises(HTTPException),
        ):
            await backup_dashboard(mock_request, db=mock_db)

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_500_on_template_error(self):
        """backup_dashboard raises HTTPException 500 when template rendering fails."""
        from app.views.backup import backup_dashboard

        mock_request = self._make_admin_request()
        mock_db = self._make_mock_db(records=[])

        with patch("app.views.backup.templates") as mock_templates:
            mock_templates.TemplateResponse.side_effect = RuntimeError("Template error")

            with pytest.raises(HTTPException) as exc_info:
                await backup_dashboard(mock_request, db=mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to load backup dashboard" in exc_info.value.detail
