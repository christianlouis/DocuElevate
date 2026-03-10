"""Tests to boost code coverage for all view modules below 100%.

Covers: api_tokens, notifications, shared_links, share, plans,
imap_accounts, integrations, general, filemanager, files, help.
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings as app_settings
from app.database import Base, get_db
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _fresh_db():
    """Yield a fresh in-memory SQLite session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client_fresh(_fresh_db) -> TestClient:
    """TestClient backed by a fresh database."""

    def _override():
        try:
            yield _fresh_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app, base_url="http://localhost") as tc:
        yield tc
    app.dependency_overrides.clear()


# ===================================================================
# 1. Simple template-render views (api_tokens, notifications,
#    shared_links, share, plans)
# ===================================================================


class TestApiTokensView:
    """GET /api-tokens should render the management page."""

    @pytest.mark.unit
    def test_api_tokens_page_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/api-tokens")
        assert resp.status_code == 200
        assert "API Tokens" in resp.text


class TestNotificationsView:
    """GET /notifications should render the dashboard."""

    @pytest.mark.unit
    def test_notifications_page_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/notifications")
        assert resp.status_code == 200
        assert "Notifications" in resp.text


class TestSharedLinksView:
    """GET /shared-links should render the management page."""

    @pytest.mark.unit
    def test_shared_links_page_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/shared-links")
        assert resp.status_code == 200
        assert "Shared Links" in resp.text


class TestShareView:
    """GET /share/{token} should render the public share landing page."""

    @pytest.mark.unit
    def test_share_page_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/share/abc123")
        assert resp.status_code == 200
        # Token should be passed to the template
        assert "abc123" in resp.text


class TestPlansViews:
    """GET /admin/plans and /admin/stripe-wizard should render pages."""

    @pytest.mark.unit
    def test_plan_designer_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/admin/plans")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_stripe_wizard_returns_200(self, client_fresh: TestClient):
        resp = client_fresh.get("/admin/stripe-wizard")
        assert resp.status_code == 200


# ===================================================================
# 2. imap_accounts view  (30.95 % → 100 %)
# ===================================================================


class TestImapAccountsView:
    """Tests for /imap-accounts view."""

    @pytest.mark.unit
    def test_imap_accounts_page_no_owner(self, client_fresh: TestClient):
        """When no owner_id is resolved, page renders with defaults."""
        resp = client_fresh.get("/imap-accounts")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_imap_accounts_page_with_owner(self, _fresh_db, client_fresh: TestClient):
        """When session has a user, the page queries IMAP accounts."""
        with patch("app.views.imap_accounts.get_current_owner_id", return_value="testuser"):
            with patch(
                "app.views.imap_accounts.get_user_tier_id",
                return_value="starter",
            ):
                with patch(
                    "app.views.imap_accounts.get_tier",
                    return_value={"id": "starter", "name": "Starter", "max_mailboxes": 3},
                ):
                    resp = client_fresh.get("/imap-accounts")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_get_max_mailboxes_free_tier(self):
        """Free tier should return 0 mailboxes."""
        from app.views.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "free", "max_mailboxes": 0}) == 0

    @pytest.mark.unit
    def test_get_max_mailboxes_unlimited(self):
        """When max_mailboxes is 0 on a non-free tier, it means unlimited."""
        from app.views.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "power", "max_mailboxes": 0}) is None

    @pytest.mark.unit
    def test_get_max_mailboxes_limited(self):
        """When max_mailboxes > 0, return that value."""
        from app.views.imap_accounts import _get_max_mailboxes

        assert _get_max_mailboxes({"id": "starter", "max_mailboxes": 5}) == 5


# ===================================================================
# 3. integrations view  (82.09 % → 100 %)
# ===================================================================


class TestIntegrationsView:
    """Tests for /integrations view."""

    @pytest.mark.unit
    def test_integrations_dashboard_no_owner(self, client_fresh: TestClient):
        """When no owner, the dashboard renders with zero-count defaults."""
        resp = client_fresh.get("/integrations")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_integrations_dashboard_with_owner(self, _fresh_db, client_fresh: TestClient):
        """When an owner_id is resolved, DB queries run and tier is fetched."""
        with patch("app.views.integrations.get_current_owner_id", return_value="testuser"):
            with patch("app.views.integrations.get_user_tier_id", return_value="power"):
                with patch(
                    "app.views.integrations.get_tier",
                    return_value={
                        "id": "power",
                        "name": "Power",
                        "max_storage_destinations": 0,
                        "max_mailboxes": 0,
                    },
                ):
                    resp = client_fresh.get("/integrations")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_integrations_dashboard_generic_exception(self, client_fresh: TestClient):
        """A non-HTTP exception in the dashboard returns 500."""
        with patch(
            "app.views.integrations.get_current_owner_id",
            side_effect=RuntimeError("boom"),
        ):
            resp = client_fresh.get("/integrations")
        assert resp.status_code == 500

    @pytest.mark.unit
    def test_get_max_destinations_free_default(self):
        from app.views.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "free", "max_storage_destinations": 0}) == 1

    @pytest.mark.unit
    def test_get_max_destinations_free_with_value(self):
        from app.views.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "free", "max_storage_destinations": 3}) == 3

    @pytest.mark.unit
    def test_get_max_destinations_unlimited(self):
        from app.views.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "power", "max_storage_destinations": 0}) is None

    @pytest.mark.unit
    def test_get_max_destinations_limited(self):
        from app.views.integrations import _get_max_destinations

        assert _get_max_destinations({"id": "starter", "max_storage_destinations": 5}) == 5

    @pytest.mark.unit
    def test_get_max_sources_free(self):
        from app.views.integrations import _get_max_sources

        assert _get_max_sources({"id": "free", "max_mailboxes": 0}) == 0

    @pytest.mark.unit
    def test_get_max_sources_unlimited(self):
        from app.views.integrations import _get_max_sources

        assert _get_max_sources({"id": "power", "max_mailboxes": 0}) is None

    @pytest.mark.unit
    def test_get_max_sources_limited(self):
        from app.views.integrations import _get_max_sources

        assert _get_max_sources({"id": "starter", "max_mailboxes": 2}) == 2


# ===================================================================
# 4. general view  (88.68 % → 100 %)
# ===================================================================


class TestGeneralViewMultiUser:
    """Cover the multi_user_enabled subscription branch (lines 96-105)."""

    @pytest.mark.unit
    def test_home_page_multi_user_with_subscription(self, _fresh_db, client_fresh: TestClient):
        """When multi_user_enabled is True and user has owner_id, subscription info is fetched."""
        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.utils.setup_wizard.is_setup_required", return_value=False),
            patch("app.views.general.get_provider_status", return_value={}),
            patch("app.views.general.validate_storage_configs", return_value={}),
            patch(
                "app.utils.subscription.get_user_tier_id",
                return_value="starter",
            ),
            patch(
                "app.utils.subscription.get_tier",
                return_value={"id": "starter", "name": "Starter"},
            ),
            patch(
                "app.utils.subscription.get_user_usage",
                return_value={"pages": 10},
            ),
        ):
            resp = client_fresh.get("/?setup=complete")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_home_page_multi_user_subscription_error(self, _fresh_db, client_fresh: TestClient):
        """When subscription lookup fails, error is logged but page still renders."""
        with (
            patch.object(app_settings, "multi_user_enabled", True),
            patch("app.utils.setup_wizard.is_setup_required", return_value=False),
            patch("app.views.general.get_provider_status", return_value={}),
            patch("app.views.general.validate_storage_configs", return_value={}),
            patch(
                "app.utils.subscription.get_user_tier_id",
                side_effect=RuntimeError("DB error"),
            ),
        ):
            resp = client_fresh.get("/?setup=complete")
        assert resp.status_code == 200


# ===================================================================
# 5. filemanager view  (96.63 % → 100 %)
# ===================================================================


class TestFilemanagerCoverageGaps:
    """Cover the remaining gaps in filemanager.py."""

    @pytest.mark.unit
    def test_format_size_petabytes(self):
        """Line 43: _format_size should return PB for very large sizes."""
        from app.views.filemanager import _format_size

        # 1 PB = 1024^5 bytes
        one_pb = 1024**5
        result = _format_size(one_pb)
        assert "PB" in result
        assert "1.0 PB" == result

    @pytest.mark.unit
    def test_format_size_multiple_petabytes(self):
        """Large values above 1 PB."""
        from app.views.filemanager import _format_size

        result = _format_size(5 * 1024**5)
        assert "PB" in result

    @pytest.mark.unit
    def test_scan_dir_with_broken_symlink(self, tmp_path):
        """Lines 104-106: files that cannot be stat'd are skipped with a warning.

        Using a broken symlink to trigger OSError on stat().
        """
        from app.views.filemanager import _scan_dir

        # Create a broken symlink — stat() will raise FileNotFoundError (subclass of OSError)
        broken_link = tmp_path / "broken_link.txt"
        broken_link.symlink_to("/nonexistent/target/file")

        # Also create a valid file so we can verify it's included
        valid_file = tmp_path / "valid.txt"
        valid_file.write_text("hello")

        db_paths: set[str] = set()
        entries = _scan_dir(tmp_path, tmp_path, db_paths)

        # The broken symlink should be skipped, the valid file should be included
        entry_names = [e["name"] for e in entries]
        assert "broken_link.txt" not in entry_names
        assert "valid.txt" in entry_names

    @pytest.mark.unit
    def test_scan_dir_oserror(self, tmp_path):
        """OSError during stat in _scan_dir is caught and file is skipped.

        We create a second broken symlink for this test.
        """
        from app.views.filemanager import _scan_dir

        broken_link = tmp_path / "also_broken.txt"
        broken_link.symlink_to("/another/nonexistent/path")

        valid_file = tmp_path / "good.txt"
        valid_file.write_text("ok")
        db_paths: set[str] = set()

        entries = _scan_dir(tmp_path, tmp_path, db_paths)
        entry_names = [e["name"] for e in entries]
        assert "also_broken.txt" not in entry_names
        assert "good.txt" in entry_names

    @pytest.mark.unit
    def test_walk_all_files_with_broken_symlink(self, tmp_path):
        """Lines 146-147: files that fail stat during walk are skipped.

        Using a broken symlink to trigger OSError.
        """
        from app.views.filemanager import _walk_all_files

        broken_link = tmp_path / "broken.pdf"
        broken_link.symlink_to("/nonexistent/target/file")

        valid_file = tmp_path / "valid.pdf"
        valid_file.write_text("content")

        db_paths: set[str] = set()
        entries = _walk_all_files(tmp_path, db_paths)

        entry_names = [e["name"] for e in entries]
        assert "broken.pdf" not in entry_names
        assert "valid.pdf" in entry_names


# ===================================================================
# 6. files view  (99.21 % → 100 %)
# ===================================================================


class TestFilesViewCoverageGaps:
    """Cover the remaining branches in files.py."""

    @pytest.mark.unit
    def test_compute_processing_flow_with_pipeline_steps(self):
        """Lines 504-515: pipeline_steps filtering in _compute_processing_flow."""
        from app.views.files import _compute_processing_flow

        # Create mock pipeline steps
        ps1 = SimpleNamespace(enabled=True, step_type="ocr")
        ps2 = SimpleNamespace(enabled=False, step_type="extract_metadata")
        ps3 = SimpleNamespace(enabled=True, step_type="send_to_destinations")

        # Create mock logs with all required attributes including task_id
        log1 = SimpleNamespace(
            step_name="create_file_record",
            status="completed",
            message="ok",
            timestamp=None,
            started_at=None,
            completed_at=None,
            task_id="task-001",
        )
        log2 = SimpleNamespace(
            step_name="check_text",
            status="completed",
            message="ok",
            timestamp=None,
            started_at=None,
            completed_at=None,
            task_id="task-002",
        )

        result = _compute_processing_flow([log1, log2], pipeline_steps=[ps1, ps2, ps3])

        # _compute_processing_flow returns a list of stage dicts
        stage_keys = [s["key"] for s in result]
        assert "create_file_record" in stage_keys  # always shown
        assert "check_text" in stage_keys  # OCR step type + ran
        # extract_metadata is disabled, so its stages should NOT be included
        assert "extract_metadata_with_gpt" not in stage_keys

    @pytest.mark.unit
    def test_compute_processing_flow_with_pipeline_steps_none(self):
        """When pipeline_steps is None, all stages are shown."""
        from app.views.files import _compute_processing_flow

        result = _compute_processing_flow([], pipeline_steps=None)
        stage_keys = [s["key"] for s in result]
        assert "create_file_record" in stage_keys
        assert "extract_metadata_with_gpt" in stage_keys

    @pytest.mark.unit
    def test_compute_processing_flow_with_empty_pipeline_steps(self):
        """When pipeline_steps is empty list, only always-show + ran stages remain."""
        from app.views.files import _compute_processing_flow

        result = _compute_processing_flow([], pipeline_steps=[])
        stage_keys = [s["key"] for s in result]
        assert "create_file_record" in stage_keys
        # Other stages should be filtered out
        assert "convert_to_pdf" not in stage_keys

    @pytest.mark.unit
    def test_compute_processing_flow_dedup_enabled(self):
        """When dedup is enabled and shown, check_for_duplicates stage appears."""
        from app.views.files import _compute_processing_flow

        with (
            patch.object(app_settings, "enable_deduplication", True),
            patch.object(app_settings, "show_deduplication_step", True),
        ):
            result = _compute_processing_flow([], pipeline_steps=None)
        stage_keys = [s["key"] for s in result]
        assert "check_for_duplicates" in stage_keys

    @pytest.mark.unit
    def test_file_detail_safe_exists_value_error(self, _fresh_db, client_fresh: TestClient):
        """Test that _safe_exists handles ValueError from commonpath gracefully.

        Lines 240-241: When os.path.commonpath raises ValueError (e.g., paths
        on different drives on Windows), _safe_exists returns False.
        """
        from app.models import FileRecord

        # Create a file record with all required fields
        rec = FileRecord(
            original_filename="test.pdf",
            local_filename="/tmp/test_local.pdf",
            original_file_path="/tmp/test_original.pdf",
            processed_file_path="/tmp/test_processed.pdf",
            file_size=100,
            mime_type="application/pdf",
            filehash="abc123def456",
        )
        _fresh_db.add(rec)
        _fresh_db.commit()
        _fresh_db.refresh(rec)

        # Patch commonpath to raise ValueError
        with patch("os.path.commonpath", side_effect=ValueError("different drives")):
            resp = client_fresh.get(f"/files/{rec.id}")

        assert resp.status_code == 200


# ===================================================================
# 7. help view  (96 % → 100 %)
# ===================================================================


class TestHelpViewCoverageGaps:
    """Cover the missing branch in help.py (34->37)."""

    @pytest.mark.unit
    def test_help_page_no_session_attr(self, client_fresh: TestClient):
        """When no session user is set, defaults are used for Zammad widgets."""
        resp = client_fresh.get("/help")
        assert resp.status_code == 200

    @pytest.mark.unit
    def test_help_page_request_without_session(self):
        """Direct function call where request has no session attribute.

        Branch 34->37: when hasattr(request, 'session') is False.
        """
        from app.views.help import help_center

        # Create a mock request without session attribute
        mock_request = MagicMock(spec=[])  # spec=[] means no attributes
        # help_center checks hasattr(request, "session")
        # With spec=[], hasattr will return False

        with patch("app.views.help.templates") as mock_templates:
            mock_templates.TemplateResponse.return_value = "ok"
            result = asyncio.get_event_loop().run_until_complete(help_center(mock_request))

        # Template should be called with empty user context
        call_args = mock_templates.TemplateResponse.call_args
        ctx = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("context", {})
        assert ctx["user_name"] == ""
        assert ctx["user_email"] == ""
        assert ctx["user_id"] == ""
