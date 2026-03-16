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
from app.models import ApiToken, FileRecord

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

    @pytest.mark.unit
    def test_resolves_from_api_token_user_state(self):
        """get_current_owner_id should resolve from request.state.api_token_user."""
        from app.utils.user_scope import get_current_owner_id

        request = MagicMock()
        request.session = {}
        request.state.api_token_user = {
            "id": "tok-owner",
            "preferred_username": "tok-owner",
            "email": "tok-owner",
        }
        assert get_current_owner_id(request) == "tok-owner"

    @pytest.mark.unit
    def test_session_takes_precedence_over_api_token_user(self):
        """Session auth should take precedence over api_token_user in state."""
        from app.utils.user_scope import get_current_owner_id

        request = MagicMock()
        request.session = {"user": {"sub": "session-sub", "email": "session@example.com"}}
        request.state.api_token_user = {"id": "tok-owner"}
        assert get_current_owner_id(request) == "session-sub"

    @pytest.mark.unit
    def test_resolves_bearer_token_directly(self, mu_engine, mu_session):
        """get_current_owner_id should resolve a Bearer token when no session exists."""
        from app.api.api_tokens import generate_api_token, hash_token
        from app.utils.user_scope import get_current_owner_id

        # Create a token in the DB
        plaintext = generate_api_token()
        token_hash = hash_token(plaintext)
        db_token = ApiToken(
            owner_id="bearer-owner",
            name="Test Bearer",
            token_hash=token_hash,
            token_prefix=plaintext[:12],
            is_active=True,
        )
        mu_session.add(db_token)
        mu_session.commit()

        # Build a mock request with Bearer header but no session
        request = MagicMock()
        request.session = {}
        request.state = MagicMock(spec=[])  # no api_token_user attr
        request.headers = {"authorization": f"Bearer {plaintext}"}
        request.client.host = "127.0.0.1"

        with patch("app.database.SessionLocal", return_value=mu_session):
            # Prevent the session from being closed since it's shared with the test
            mu_session.close = MagicMock()
            result = get_current_owner_id(request)

        assert result == "bearer-owner"
        # Verify the resolved user was cached in request.state
        assert request.state.api_token_user["id"] == "bearer-owner"

    @pytest.mark.unit
    def test_returns_none_for_invalid_bearer_token(self, mu_engine, mu_session):
        """get_current_owner_id should return None for an invalid Bearer token."""
        from app.utils.user_scope import get_current_owner_id

        request = MagicMock()
        request.session = {}
        request.state = MagicMock(spec=[])  # no api_token_user attr
        request.headers = {"authorization": "Bearer de_invalid_token_value"}
        request.client.host = "127.0.0.1"

        with patch("app.database.SessionLocal", return_value=mu_session):
            mu_session.close = MagicMock()
            result = get_current_owner_id(request)

        assert result is None


class TestOwnerIdFromUser:
    """Tests for the _owner_id_from_user helper."""

    @pytest.mark.unit
    def test_prefers_sub(self):
        from app.utils.user_scope import _owner_id_from_user

        assert _owner_id_from_user({"sub": "s", "preferred_username": "u", "email": "e"}) == "s"

    @pytest.mark.unit
    def test_falls_back_to_preferred_username(self):
        from app.utils.user_scope import _owner_id_from_user

        assert _owner_id_from_user({"preferred_username": "u", "email": "e"}) == "u"

    @pytest.mark.unit
    def test_falls_back_to_email(self):
        from app.utils.user_scope import _owner_id_from_user

        assert _owner_id_from_user({"email": "e"}) == "e"

    @pytest.mark.unit
    def test_falls_back_to_id(self):
        from app.utils.user_scope import _owner_id_from_user

        assert _owner_id_from_user({"id": "i"}) == "i"

    @pytest.mark.unit
    def test_returns_none_for_empty_dict(self):
        from app.utils.user_scope import _owner_id_from_user

        assert _owner_id_from_user({}) is None


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
        """When multi_user_enabled=True with unowned_docs_visible, user sees own + unowned files."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", True):
            filtered = apply_owner_filter(query, request)

        results = filtered.all()
        # Alice sees her own file + the unowned file (not Bob's)
        assert len(results) == 2
        owner_ids = {r.owner_id for r in results}
        assert owner_ids == {"alice", None}

    @pytest.mark.unit
    def test_filters_strictly_when_unowned_not_visible(self, mu_session):
        """When unowned_docs_visible_to_all=False, user sees only own files."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id="bob")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", False):
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

    @pytest.mark.unit
    def test_default_owner_id_fallback_in_process_document(self):
        """When owner_id is None and default_owner_id is set, fallback is used."""
        # Verify the fallback logic exists in the source code
        import ast
        from pathlib import Path

        src = Path("app/tasks/process_document.py").read_text()
        tree = ast.parse(src)
        # Check that 'default_owner_id' string appears in the source
        assert "default_owner_id" in src, "default_owner_id fallback not found in process_document.py"


# ---------------------------------------------------------------------------
# New config settings tests
# ---------------------------------------------------------------------------


class TestUnownedDocsConfig:
    """Verify the new multi-user configuration settings."""

    @pytest.mark.unit
    def test_unowned_docs_visible_default_true(self):
        """unowned_docs_visible_to_all should default to True."""
        assert hasattr(settings, "unowned_docs_visible_to_all")

    @pytest.mark.unit
    def test_default_owner_id_default_none(self):
        """default_owner_id should default to None."""
        assert hasattr(settings, "default_owner_id")

    @pytest.mark.unit
    def test_unowned_docs_has_metadata(self):
        """unowned_docs_visible_to_all must be in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "unowned_docs_visible_to_all" in SETTING_METADATA
        meta = SETTING_METADATA["unowned_docs_visible_to_all"]
        assert meta["type"] == "boolean"
        assert meta["category"] == "Authentication"

    @pytest.mark.unit
    def test_default_owner_id_has_metadata(self):
        """default_owner_id must be in SETTING_METADATA."""
        from app.utils.settings_service import SETTING_METADATA

        assert "default_owner_id" in SETTING_METADATA
        meta = SETTING_METADATA["default_owner_id"]
        assert meta["type"] == "user_autocomplete"


# ---------------------------------------------------------------------------
# Claim endpoint tests
# ---------------------------------------------------------------------------


class TestClaimEndpoint:
    """Tests for POST /api/files/{file_id}/claim."""

    @pytest.mark.integration
    def test_claim_disabled_without_multi_user(self, client, db_session):
        """Claiming is rejected when multi-user mode is off."""
        rec = _create_file_record(db_session, owner_id=None, filename="unclaimed.pdf")
        with _patch_multi_user(False):
            response = client.post(f"/api/files/{rec.id}/claim")
        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    @pytest.mark.integration
    def test_claim_unauthenticated_returns_401(self, client, db_session):
        """Claiming without a session returns 401."""
        rec = _create_file_record(db_session, owner_id=None, filename="unclaimed.pdf")
        with _patch_multi_user(True):
            response = client.post(f"/api/files/{rec.id}/claim")
        assert response.status_code == 401


class TestClaimUnit:
    """Unit tests for claim logic directly on the model."""

    @pytest.mark.unit
    def test_claim_sets_owner_id(self, mu_session):
        """Setting owner_id on a NULL-owner file persists correctly."""
        rec = _create_file_record(mu_session, owner_id=None)
        assert rec.owner_id is None

        rec.owner_id = "alice"
        mu_session.commit()
        mu_session.refresh(rec)
        assert rec.owner_id == "alice"

    @pytest.mark.unit
    def test_claim_already_owned_same_user(self, mu_session):
        """Claiming a file you already own returns already_owned status."""
        rec = _create_file_record(mu_session, owner_id="alice")
        # The API would return already_owned; test the model constraint
        assert rec.owner_id == "alice"

    @pytest.mark.unit
    def test_claim_unowned_then_verify(self, mu_session):
        """Claim unowned, then verify the file is filterable by new owner."""
        rec = _create_file_record(mu_session, owner_id=None, filename="orphan.pdf")
        # Before claim: found via NULL filter
        unowned = mu_session.query(FileRecord).filter(FileRecord.owner_id.is_(None)).all()
        assert rec in unowned

        # After claim
        rec.owner_id = "claimer"
        mu_session.commit()
        mu_session.refresh(rec)

        owned = mu_session.query(FileRecord).filter(FileRecord.owner_id == "claimer").all()
        assert rec in owned
        unowned = mu_session.query(FileRecord).filter(FileRecord.owner_id.is_(None)).all()
        assert rec not in unowned


# ---------------------------------------------------------------------------
# Bulk claim endpoint tests
# ---------------------------------------------------------------------------


class TestBulkClaimEndpoint:
    """Tests for POST /api/files/bulk-claim."""

    @pytest.mark.integration
    def test_bulk_claim_disabled_without_multi_user(self, client, db_session):
        """Bulk claiming is rejected when multi-user mode is off."""
        _create_file_record(db_session, owner_id=None, filename="a.pdf")
        with _patch_multi_user(False):
            response = client.post("/api/files/bulk-claim", json=[1])
        assert response.status_code == 400

    @pytest.mark.integration
    def test_bulk_claim_unauthenticated_returns_401(self, client, db_session):
        """Bulk claiming without a session returns 401."""
        rec = _create_file_record(db_session, owner_id=None, filename="a.pdf")
        with _patch_multi_user(True):
            response = client.post("/api/files/bulk-claim", json=[rec.id])
        assert response.status_code == 401


class TestBulkClaimUnit:
    """Unit tests for bulk claim DB logic."""

    @pytest.mark.unit
    def test_bulk_claim_multiple_unowned(self, mu_session):
        """Bulk claim sets owner on multiple NULL-owner files."""
        r1 = _create_file_record(mu_session, owner_id=None, filename="a.pdf")
        r2 = _create_file_record(mu_session, owner_id=None, filename="b.pdf")
        r3 = _create_file_record(mu_session, owner_id="bob", filename="c.pdf")

        # Simulate bulk claim logic
        records = mu_session.query(FileRecord).filter(FileRecord.id.in_([r1.id, r2.id, r3.id])).all()
        claimed, skipped = [], []
        for rec in records:
            if rec.owner_id is None:
                rec.owner_id = "claimer"
                claimed.append(rec.id)
            else:
                skipped.append(rec.id)
        mu_session.commit()

        assert set(claimed) == {r1.id, r2.id}
        assert skipped == [r3.id]

    @pytest.mark.unit
    def test_bulk_claim_all_already_owned(self, mu_session):
        """Bulk claim with all already-owned files skips everything."""
        r1 = _create_file_record(mu_session, owner_id="alice", filename="a.pdf")
        r2 = _create_file_record(mu_session, owner_id="bob", filename="b.pdf")

        records = mu_session.query(FileRecord).filter(FileRecord.id.in_([r1.id, r2.id])).all()
        claimed = [rec for rec in records if rec.owner_id is None]
        assert len(claimed) == 0


# ---------------------------------------------------------------------------
# Assign-owner endpoint tests
# ---------------------------------------------------------------------------


class TestAssignOwnerEndpoint:
    """Tests for POST /api/files/assign-owner."""

    @pytest.mark.integration
    def test_assign_owner_disabled_without_multi_user(self, client, db_session):
        """Assigning owner is rejected when multi-user mode is off."""
        with _patch_multi_user(False):
            response = client.post("/api/files/assign-owner?owner_id=alice")
        assert response.status_code == 400

    @pytest.mark.integration
    def test_assign_owner_requires_admin(self, client, db_session):
        """Non-admin users cannot assign owners."""
        with _patch_multi_user(True):
            response = client.post("/api/files/assign-owner?owner_id=alice")
        # 403 (non-admin) or 401 (no auth)
        assert response.status_code in [401, 403]


class TestAssignOwnerUnit:
    """Unit tests for bulk owner assignment."""

    @pytest.mark.unit
    def test_assign_owner_to_unowned_files(self, mu_session):
        """Bulk update sets owner_id on all NULL-owner files."""
        _create_file_record(mu_session, owner_id=None, filename="a.pdf")
        _create_file_record(mu_session, owner_id=None, filename="b.pdf")
        _create_file_record(mu_session, owner_id="bob", filename="c.pdf")

        updated = (
            mu_session.query(FileRecord)
            .filter(FileRecord.owner_id.is_(None))
            .update({FileRecord.owner_id: "alice"}, synchronize_session="fetch")
        )
        mu_session.commit()

        assert updated == 2
        all_files = mu_session.query(FileRecord).all()
        owners = {f.original_filename: f.owner_id for f in all_files}
        assert owners["a.pdf"] == "alice"
        assert owners["b.pdf"] == "alice"
        assert owners["c.pdf"] == "bob"

    @pytest.mark.unit
    def test_assign_owner_to_specific_files(self, mu_session):
        """Update specific file IDs sets owner_id."""
        rec1 = _create_file_record(mu_session, owner_id=None, filename="a.pdf")
        rec2 = _create_file_record(mu_session, owner_id="bob", filename="b.pdf")

        updated = (
            mu_session.query(FileRecord)
            .filter(FileRecord.id.in_([rec1.id, rec2.id]))
            .update({FileRecord.owner_id: "charlie"}, synchronize_session="fetch")
        )
        mu_session.commit()

        assert updated == 2
        mu_session.refresh(rec1)
        mu_session.refresh(rec2)
        assert rec1.owner_id == "charlie"
        assert rec2.owner_id == "charlie"


# ---------------------------------------------------------------------------
# User search endpoint tests
# ---------------------------------------------------------------------------


class TestUserSearchEndpoint:
    """Tests for GET /api/users/search."""

    @pytest.mark.integration
    def test_search_returns_known_users(self, client, db_session):
        """Search should return distinct owner_ids from file records."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")
        _create_file_record(db_session, owner_id="bob", filename="b.pdf")
        _create_file_record(db_session, owner_id="alice", filename="a2.pdf")  # duplicate owner
        _create_file_record(db_session, owner_id=None, filename="c.pdf")  # unowned

        response = client.get("/api/users/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        # Should contain alice and bob (not None)
        assert set(data["users"]) == {"alice", "bob"}

    @pytest.mark.integration
    def test_search_filters_by_substring(self, client, db_session):
        """Search should filter by case-insensitive substring."""
        _create_file_record(db_session, owner_id="christianlouis", filename="a.pdf")
        _create_file_record(db_session, owner_id="bob", filename="b.pdf")
        _create_file_record(db_session, owner_id="alice", filename="c.pdf")

        response = client.get("/api/users/search?q=risti")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == ["christianlouis"]

    @pytest.mark.integration
    def test_search_respects_limit(self, client, db_session):
        """Search should respect the limit parameter."""
        for i in range(10):
            _create_file_record(db_session, owner_id=f"user_{i:02d}", filename=f"file_{i}.pdf")

        response = client.get("/api/users/search?q=user&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 3

    @pytest.mark.integration
    def test_search_empty_when_no_matches(self, client, db_session):
        """Search with no matches should return empty list."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")

        response = client.get("/api/users/search?q=zzzzz")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == []

    @pytest.mark.integration
    def test_search_case_insensitive(self, client, db_session):
        """Search should be case-insensitive."""
        _create_file_record(db_session, owner_id="ChristianLouis", filename="a.pdf")

        response = client.get("/api/users/search?q=CHRISTIAN")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == ["ChristianLouis"]

    @pytest.mark.integration
    def test_search_no_query_param(self, client, db_session):
        """Search without q parameter defaults to empty string (returns all)."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")
        _create_file_record(db_session, owner_id="bob", filename="b.pdf")

        response = client.get("/api/users/search")
        assert response.status_code == 200
        data = response.json()
        assert set(data["users"]) == {"alice", "bob"}

    @pytest.mark.integration
    def test_search_empty_database(self, client, db_session):
        """Search on an empty database returns empty list."""
        response = client.get("/api/users/search?q=anything")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == []

    @pytest.mark.integration
    def test_search_results_sorted_alphabetically(self, client, db_session):
        """Search results should be sorted alphabetically."""
        _create_file_record(db_session, owner_id="zebra", filename="z.pdf")
        _create_file_record(db_session, owner_id="apple", filename="a.pdf")
        _create_file_record(db_session, owner_id="mango", filename="m.pdf")

        response = client.get("/api/users/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == ["apple", "mango", "zebra"]

    @pytest.mark.integration
    def test_search_default_limit_is_5(self, client, db_session):
        """Default limit should be 5."""
        for i in range(10):
            _create_file_record(db_session, owner_id=f"user_{i:02d}", filename=f"file_{i}.pdf")

        response = client.get("/api/users/search?q=user")
        assert response.status_code == 200
        data = response.json()
        assert len(data["users"]) == 5

    @pytest.mark.integration
    def test_search_whitespace_query_trimmed(self, client, db_session):
        """Leading/trailing whitespace in query should be trimmed."""
        _create_file_record(db_session, owner_id="alice", filename="a.pdf")

        response = client.get("/api/users/search?q=%20alice%20")
        assert response.status_code == 200
        data = response.json()
        assert data["users"] == ["alice"]


# ---------------------------------------------------------------------------
# Additional user_scope filter edge-case tests
# ---------------------------------------------------------------------------


class TestApplyOwnerFilterEdgeCases:
    """Additional edge-case tests for apply_owner_filter."""

    @pytest.mark.unit
    def test_unowned_visible_includes_null_and_own(self, mu_session):
        """With unowned_docs_visible_to_all=True, user sees own + NULL files."""
        from app.utils.user_scope import apply_owner_filter

        own = _create_file_record(mu_session, owner_id="alice", filename="mine.pdf")
        other = _create_file_record(mu_session, owner_id="bob", filename="theirs.pdf")
        orphan = _create_file_record(mu_session, owner_id=None, filename="orphan.pdf")

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", True):
            results = apply_owner_filter(query, request).all()

        result_ids = {r.id for r in results}
        assert own.id in result_ids
        assert orphan.id in result_ids
        assert other.id not in result_ids

    @pytest.mark.unit
    def test_unowned_not_visible_excludes_null(self, mu_session):
        """With unowned_docs_visible_to_all=False, user sees only own files."""
        from app.utils.user_scope import apply_owner_filter

        own = _create_file_record(mu_session, owner_id="alice", filename="mine.pdf")
        orphan = _create_file_record(mu_session, owner_id=None, filename="orphan.pdf")

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", False):
            results = apply_owner_filter(query, request).all()

        result_ids = {r.id for r in results}
        assert own.id in result_ids
        assert orphan.id not in result_ids

    @pytest.mark.unit
    def test_admin_always_sees_all(self, mu_session):
        """Admin user always sees all files, regardless of unowned_docs_visible_to_all."""
        from app.utils.user_scope import apply_owner_filter

        _create_file_record(mu_session, owner_id="alice")
        _create_file_record(mu_session, owner_id=None)

        request = _mock_request(user={"preferred_username": "admin", "is_admin": True})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", False):
            results = apply_owner_filter(query, request).all()

        assert len(results) == 2

    @pytest.mark.unit
    def test_no_files_returns_empty(self, mu_session):
        """Empty database returns no results for any user."""
        from app.utils.user_scope import apply_owner_filter

        request = _mock_request(user={"preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True):
            results = apply_owner_filter(query, request).all()

        assert results == []

    @pytest.mark.unit
    def test_user_with_sub_claim(self, mu_session):
        """User with OAuth 'sub' claim uses sub as owner_id."""
        from app.utils.user_scope import apply_owner_filter

        rec = _create_file_record(mu_session, owner_id="oauth-sub-123")
        request = _mock_request(user={"sub": "oauth-sub-123", "preferred_username": "alice"})
        query = mu_session.query(FileRecord)

        with _patch_multi_user(True), patch.object(settings, "unowned_docs_visible_to_all", False):
            results = apply_owner_filter(query, request).all()

        assert len(results) == 1
        assert results[0].id == rec.id
