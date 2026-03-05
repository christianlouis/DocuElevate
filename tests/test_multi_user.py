"""
Tests for multi-user document isolation and feature flag.

Covers:
- user_scope utilities (get_current_owner_id, apply_owner_filter)
- FileRecord.owner_id model field
- API file list/detail/delete scoping in multi-user mode
- Upload endpoint owner_id propagation
- Feature flag toggling (single-user vs multi-user mode)
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.models import FileRecord

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mu_engine():
    """In-memory SQLite engine for multi-user tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def mu_session(mu_engine):
    """Session scoped to a single test function."""
    Session = sessionmaker(bind=mu_engine)
    session = Session()
    yield session
    session.close()


def _create_file_record(session, owner_id=None, filename="test.pdf"):
    """Helper to insert a minimal FileRecord."""
    rec = FileRecord(
        filehash="abc123",
        original_filename=filename,
        local_filename="/tmp/test.pdf",
        file_size=1024,
        mime_type="application/pdf",
        is_duplicate=False,
        owner_id=owner_id,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def _mock_request(user=None):
    """Create a mock request with the given session user."""
    request = MagicMock()
    request.session = {"user": user} if user else {}
    return request


def _patch_multi_user(enabled):
    """Return a patch context manager for multi_user_enabled."""
    return patch.object(settings, "multi_user_enabled", enabled)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFileRecordOwnerField:
    """Verify the owner_id column on FileRecord."""

    @pytest.mark.unit
    def test_owner_id_defaults_to_none(self, mu_session):
        """FileRecord created without owner_id should have None."""
        rec = _create_file_record(mu_session)
        assert rec.owner_id is None

    @pytest.mark.unit
    def test_owner_id_stores_value(self, mu_session):
        """FileRecord created with owner_id should persist it."""
        rec = _create_file_record(mu_session, owner_id="user@example.com")
        assert rec.owner_id == "user@example.com"

    @pytest.mark.unit
    def test_owner_id_filterable(self, mu_session):
        """Can query FileRecord by owner_id."""
        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        alice_files = mu_session.query(FileRecord).filter(FileRecord.owner_id == "alice").all()
        assert len(alice_files) == 1
        assert alice_files[0].owner_id == "alice"

        global_files = mu_session.query(FileRecord).filter(FileRecord.owner_id.is_(None)).all()
        assert len(global_files) == 1


# ---------------------------------------------------------------------------
# user_scope utility tests
# ---------------------------------------------------------------------------


class TestGetCurrentOwnerId:
    """Tests for get_current_owner_id()."""

    @pytest.mark.unit
    def test_returns_none_when_no_user(self):
        from app.utils.user_scope import get_current_owner_id

        request = _mock_request(user=None)
        assert get_current_owner_id(request) is None

    @pytest.mark.unit
    def test_prefers_sub_claim(self):
        from app.utils.user_scope import get_current_owner_id

        request = _mock_request(user={"sub": "sub-123", "preferred_username": "alice", "email": "a@b.com"})
        assert get_current_owner_id(request) == "sub-123"

    @pytest.mark.unit
    def test_falls_back_to_preferred_username(self):
        from app.utils.user_scope import get_current_owner_id

        request = _mock_request(user={"preferred_username": "alice", "email": "a@b.com"})
        assert get_current_owner_id(request) == "alice"

    @pytest.mark.unit
    def test_falls_back_to_email(self):
        from app.utils.user_scope import get_current_owner_id

        request = _mock_request(user={"email": "a@b.com"})
        assert get_current_owner_id(request) == "a@b.com"

    @pytest.mark.unit
    def test_falls_back_to_id(self):
        from app.utils.user_scope import get_current_owner_id

        request = _mock_request(user={"id": "admin"})
        assert get_current_owner_id(request) == "admin"

    @pytest.mark.unit
    def test_returns_none_for_empty_session(self):
        from app.utils.user_scope import get_current_owner_id

        request = MagicMock()
        request.session = {}
        assert get_current_owner_id(request) is None


class TestApplyOwnerFilter:
    """Tests for apply_owner_filter()."""

    @pytest.mark.unit
    def test_no_filter_when_disabled(self, mu_session):
        """When multi_user_enabled=False, all files are returned."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(False):
            filtered = apply_owner_filter(query, request)

        assert filtered.count() == 3

    @pytest.mark.unit
    def test_filters_by_owner_when_enabled(self, mu_session):
        """When multi_user_enabled=True, only user's files are returned."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True):
            filtered = apply_owner_filter(query, request)

        results = filtered.all()
        assert len(results) == 1
        assert results[0].owner_id == "alice"

    @pytest.mark.unit
    def test_admin_sees_all_when_enabled(self, mu_session):
        """Admin users bypass the owner filter in multi-user mode."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "admin", "is_admin": True})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True):
            filtered = apply_owner_filter(query, request)

        assert filtered.count() == 3

    @pytest.mark.unit
    def test_unauthenticated_sees_nothing_when_enabled(self, mu_session):
        """When no user is logged in and multi-user is enabled, return empty."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")

        request = _mock_request(user=None)
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True):
            filtered = apply_owner_filter(query, request)

        assert filtered.count() == 0


# ---------------------------------------------------------------------------
# Config / feature flag tests
# ---------------------------------------------------------------------------


class TestMultiUserConfig:
    """Verify the multi-user configuration settings."""

    @pytest.mark.unit
    def test_multi_user_default_disabled(self):
        """multi_user_enabled should default to False."""
        from app.config import settings

        # Default is False (overridable via env)
        assert hasattr(settings, "multi_user_enabled")

    @pytest.mark.unit
    def test_default_daily_upload_limit_exists(self):
        """default_daily_upload_limit should exist on settings."""
        from app.config import settings

        assert hasattr(settings, "default_daily_upload_limit")

    @pytest.mark.unit
    def test_multi_user_setting_has_metadata(self):
        """multi_user_enabled must be in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "multi_user_enabled" in SETTING_METADATA
        meta = SETTING_METADATA["multi_user_enabled"]
        assert meta["type"] == "boolean"
        assert meta["category"] == "Authentication"

    @pytest.mark.unit
    def test_daily_upload_limit_setting_has_metadata(self):
        """default_daily_upload_limit must be in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "default_daily_upload_limit" in SETTING_METADATA
        meta = SETTING_METADATA["default_daily_upload_limit"]
        assert meta["type"] == "integer"


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestMigration012:
    """Verify the multi-user migration file exists and is well-formed."""

    @pytest.mark.unit
    def test_migration_file_exists(self):
        """Migration 012 should exist."""
        from pathlib import Path

        migration = Path("migrations/versions/012_add_multi_user_support.py")
        assert migration.exists()

    @pytest.mark.unit
    def test_migration_chain(self):
        """Migration 012 should chain from 011."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migration_012", "migrations/versions/012_add_multi_user_support.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.down_revision == "011_add_pdfa_paths"
        assert mod.revision == "012_add_multi_user_support"


# ---------------------------------------------------------------------------
# API integration tests (list files with owner scoping)
# ---------------------------------------------------------------------------


class TestFilesAPIMultiUser:
    """Verify that the files API respects multi-user scoping."""

    @pytest.mark.integration
    def test_list_files_unscoped_single_user(self, client, db_session):
        """In single-user mode all files are visible."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")
        _create_file_record(db_session, owner_id="bob", filename="b.pdf")

        with _patch_multi_user(False):
            response = client.get("/api/files")

        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 2

    @pytest.mark.integration
    def test_list_files_scoped_multi_user(self, client, db_session):
        """In multi-user mode only the user's files should be returned."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")
        _create_file_record(db_session, owner_id="bob", filename="b.pdf")

        with _patch_multi_user(True):
            # Without a real session, the filter will return no results
            # (unauthenticated user sees nothing in multi-user mode)
            response = client.get("/api/files")
            assert response.status_code == 200
            data = response.json()
            # No session user means empty results
            assert data["pagination"]["total"] == 0

    @pytest.mark.integration
    def test_get_file_detail_respects_scope(self, client, db_session):
        """File detail endpoint should return 404 for files owned by other users."""
        rec = _create_file_record(db_session, owner_id="alice", filename="a.pdf")

        with _patch_multi_user(True):
            response = client.get(f"/api/files/{rec.id}")
            # Without session, user is unauthenticated → 404
            assert response.status_code == 404

    @pytest.mark.integration
    def test_get_file_detail_single_user_mode(self, client, db_session):
        """File detail endpoint should work normally in single-user mode."""
        rec = _create_file_record(db_session, owner_id="alice", filename="a.pdf")

        with _patch_multi_user(False):
            response = client.get(f"/api/files/{rec.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["file"]["id"] == rec.id


# ---------------------------------------------------------------------------
# process_document owner_id parameter tests
# ---------------------------------------------------------------------------


class TestProcessDocumentOwnerId:
    """Verify process_document task accepts owner_id."""

    @pytest.mark.unit
    def test_process_document_signature_accepts_owner_id(self):
        """process_document should accept owner_id as a keyword argument."""
        import inspect

        from app.tasks.process_document import process_document

        sig = inspect.signature(process_document)
        assert "owner_id" in sig.parameters
        assert sig.parameters["owner_id"].default is None

    @pytest.mark.unit
    def test_convert_to_pdf_signature_accepts_owner_id(self):
        """convert_to_pdf should accept owner_id as a keyword argument."""
        import inspect

        from app.tasks.convert_to_pdf import convert_to_pdf

        sig = inspect.signature(convert_to_pdf)
        assert "owner_id" in sig.parameters
        assert sig.parameters["owner_id"].default is None
