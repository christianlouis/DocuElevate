"""Tests for the file sharing API (FileShare model and /api/files/{id}/shares endpoints)."""

import pytest

from app.models import FILE_SHARE_ROLE_EDITOR, FILE_SHARE_ROLE_VIEWER, FileRecord, FileShare, UserProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_file(db_session, owner_id="owner1") -> FileRecord:
    """Create a minimal owned FileRecord."""
    f = FileRecord(
        owner_id=owner_id,
        filehash="sharehash",
        original_filename="shared.pdf",
        local_filename="shared.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _create_unowned_file(db_session) -> FileRecord:
    """Create a FileRecord with no owner."""
    f = FileRecord(
        owner_id=None,
        filehash="unownedhash",
        original_filename="unowned.pdf",
        local_filename="unowned.pdf",
        file_size=512,
        mime_type="application/pdf",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _create_profile(db_session, user_id: str, display_name: str | None = None) -> UserProfile:
    p = UserProfile(user_id=user_id, display_name=display_name)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# get_file_role helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFileRole:
    """Tests for the get_file_role() utility."""

    def test_owner_returns_owner(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import get_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert get_file_role(f, "alice", db_session) == "owner"

    def test_non_owner_no_share_returns_none(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import get_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert get_file_role(f, "bob", db_session) is None

    def test_shared_viewer_returns_viewer(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import get_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role=FILE_SHARE_ROLE_VIEWER)
        db_session.add(share)
        db_session.commit()
        assert get_file_role(f, "bob", db_session) == FILE_SHARE_ROLE_VIEWER

    def test_shared_editor_returns_editor(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import get_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="carol", role=FILE_SHARE_ROLE_EDITOR)
        db_session.add(share)
        db_session.commit()
        assert get_file_role(f, "carol", db_session) == FILE_SHARE_ROLE_EDITOR

    def test_unowned_file_returns_viewer_when_setting_allows(self, db_session, monkeypatch):
        from app.utils import user_scope

        monkeypatch.setattr(user_scope.settings, "multi_user_enabled", True)
        monkeypatch.setattr(user_scope.settings, "unowned_docs_visible_to_all", True)
        f = _create_unowned_file(db_session)
        role = user_scope.get_file_role(f, "anyone", db_session)
        assert role == FILE_SHARE_ROLE_VIEWER

    def test_none_user_returns_none(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import get_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert get_file_role(f, None, db_session) is None


# ---------------------------------------------------------------------------
# has_file_role helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasFileRole:
    """Tests for the has_file_role() utility."""

    def test_owner_satisfies_viewer(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert has_file_role(f, "alice", db_session, minimum_role="viewer") is True

    def test_owner_satisfies_editor(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert has_file_role(f, "alice", db_session, minimum_role="editor") is True

    def test_owner_satisfies_owner(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert has_file_role(f, "alice", db_session, minimum_role="owner") is True

    def test_viewer_does_not_satisfy_editor(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role=FILE_SHARE_ROLE_VIEWER)
        db_session.add(share)
        db_session.commit()
        assert has_file_role(f, "bob", db_session, minimum_role="editor") is False

    def test_editor_satisfies_viewer(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="carol", role=FILE_SHARE_ROLE_EDITOR)
        db_session.add(share)
        db_session.commit()
        assert has_file_role(f, "carol", db_session, minimum_role="viewer") is True

    def test_no_access_returns_false(self, db_session, monkeypatch):
        from app.config import settings as real_settings
        from app.utils.user_scope import has_file_role

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")
        assert has_file_role(f, "stranger", db_session) is False


# ---------------------------------------------------------------------------
# List shares
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListShares:
    """Tests for GET /api/files/{file_id}/shares."""

    def test_owner_can_list_shares(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role=FILE_SHARE_ROLE_VIEWER)
        db_session.add(share)
        db_session.commit()

        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        resp = client.get(f"/api/files/{f.id}/shares")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["shared_with_user_id"] == "bob"
        assert data[0]["role"] == FILE_SHARE_ROLE_VIEWER

    def test_non_owner_cannot_list_shares(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        f = _create_file(db_session, owner_id="alice")

        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "bob")
        # bob has no access to alice's file — the get_file_role call in list_shares
        # will return None for bob, giving 404 not 403 (file not found for bob)
        resp = client.get(f"/api/files/{f.id}/shares")
        assert resp.status_code in (403, 404)

    def test_list_shares_file_not_found(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod

        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")
        resp = client.get("/api/files/99999/shares")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create share
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateShare:
    """Tests for POST /api/files/{file_id}/shares."""

    def test_owner_can_share_with_viewer(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "bob", "role": "viewer"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["shared_with_user_id"] == "bob"
        assert data["role"] == "viewer"
        assert data["file_id"] == f.id

    def test_owner_can_share_with_editor(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "carol", "role": "editor"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "editor"

    def test_non_owner_cannot_share(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "bob")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "carol", "role": "viewer"},
        )
        # bob doesn't own the file; get_file_role returns None → 404 for non-owner
        assert resp.status_code in (403, 404)

    def test_share_with_self_rejected(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "alice", "role": "viewer"},
        )
        assert resp.status_code == 422

    def test_invalid_role_rejected(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "bob", "role": "admin"},
        )
        assert resp.status_code == 422

    def test_empty_user_id_rejected(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "  ", "role": "viewer"},
        )
        assert resp.status_code == 422

    def test_duplicate_share_updates_role(self, client, db_session, monkeypatch):
        """Creating a share for an already-shared user updates the role."""
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()

        resp = client.post(
            f"/api/files/{f.id}/shares",
            json={"shared_with_user_id": "bob", "role": "editor"},
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == "editor"


# ---------------------------------------------------------------------------
# Update share role
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateShare:
    """Tests for PUT /api/files/{file_id}/shares/{share_id}."""

    def test_owner_can_update_role(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()
        db_session.refresh(share)

        resp = client.put(
            f"/api/files/{f.id}/shares/{share.id}",
            json={"role": "editor"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    def test_non_owner_cannot_update_role(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "bob")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()
        db_session.refresh(share)

        resp = client.put(
            f"/api/files/{f.id}/shares/{share.id}",
            json={"role": "editor"},
        )
        assert resp.status_code in (403, 404)

    def test_invalid_role_rejected(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()
        db_session.refresh(share)

        resp = client.put(
            f"/api/files/{f.id}/shares/{share.id}",
            json={"role": "superuser"},
        )
        assert resp.status_code == 422

    def test_share_not_found(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.put(
            f"/api/files/{f.id}/shares/99999",
            json={"role": "editor"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Revoke share
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRevokeShare:
    """Tests for DELETE /api/files/{file_id}/shares/{share_id}."""

    def test_owner_can_revoke(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()
        db_session.refresh(share)

        resp = client.delete(f"/api/files/{f.id}/shares/{share.id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        # Confirm the share is gone
        db_session.expire_all()
        assert db_session.query(FileShare).filter(FileShare.id == share.id).first() is None

    def test_non_owner_cannot_revoke(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "carol")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()
        db_session.refresh(share)

        resp = client.delete(f"/api/files/{f.id}/shares/{share.id}")
        assert resp.status_code in (403, 404)

    def test_revoke_not_found(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        resp = client.delete(f"/api/files/{f.id}/shares/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List shared-with
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListSharedWith:
    """Tests for GET /api/files/{file_id}/shared-with."""

    def test_owner_can_see_shared_with(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        _create_profile(db_session, "bob", "Bob Smith")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()

        resp = client.get(f"/api/files/{f.id}/shared-with")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["user_id"] == "bob"
        assert data[0]["display_name"] == "Bob Smith"
        assert data[0]["role"] == "viewer"

    def test_viewer_can_see_shared_with(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "bob")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()

        resp = client.get(f"/api/files/{f.id}/shared-with")
        assert resp.status_code == 200

    def test_unauthorized_user_gets_404(self, client, db_session, monkeypatch):
        import app.api.sharing as sharing_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(sharing_mod, "get_current_owner_id", lambda req: "stranger")

        f = _create_file(db_session, owner_id="alice")
        resp = client.get(f"/api/files/{f.id}/shared-with")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auto-share on mention
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAutoShareOnMention:
    """Tests that @mentioning a user in a comment auto-shares the file."""

    def test_mention_auto_shares_with_viewer(self, client, db_session, monkeypatch):
        """When multi_user_enabled is True, mentioning a user auto-shares the file."""
        import app.api.comments as comments_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(comments_mod, "get_current_owner_id", lambda req: "alice")
        monkeypatch.setattr(comments_mod, "get_current_user_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")

        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "Hey @bob, please look at this."},
        )
        assert resp.status_code == 201

        # bob should now have a viewer share on the file
        share = (
            db_session.query(FileShare)
            .filter(FileShare.file_id == f.id, FileShare.shared_with_user_id == "bob")
            .first()
        )
        assert share is not None
        assert share.role == FILE_SHARE_ROLE_VIEWER

    def test_mention_does_not_duplicate_share(self, client, db_session, monkeypatch):
        """Mentioning a user that already has a share does not create a duplicate."""
        import app.api.comments as comments_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(comments_mod, "get_current_owner_id", lambda req: "alice")
        monkeypatch.setattr(comments_mod, "get_current_user_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")
        existing = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="editor")
        db_session.add(existing)
        db_session.commit()
        existing_id = existing.id

        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "Hey @bob again!"},
        )
        assert resp.status_code == 201

        shares = (
            db_session.query(FileShare).filter(FileShare.file_id == f.id, FileShare.shared_with_user_id == "bob").all()
        )
        assert len(shares) == 1
        assert shares[0].id == existing_id
        assert shares[0].role == "editor"  # role unchanged

    def test_mention_skipped_when_single_user_mode(self, client, db_session, monkeypatch):
        import app.api.comments as comments_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", False)
        monkeypatch.setattr(comments_mod, "get_current_owner_id", lambda req: "alice")
        monkeypatch.setattr(comments_mod, "get_current_user_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")

        resp = client.post(
            f"/api/files/{f.id}/comments",
            json={"body": "Hey @carol, look here."},
        )
        assert resp.status_code == 201

        share = (
            db_session.query(FileShare)
            .filter(FileShare.file_id == f.id, FileShare.shared_with_user_id == "carol")
            .first()
        )
        assert share is None


# ---------------------------------------------------------------------------
# Delete file – owner-only enforcement
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeleteFileOwnerOnly:
    """Ensure non-owners (shared viewers/editors) cannot delete files."""

    def test_owner_can_delete_in_multi_user_mode(self, client, db_session, monkeypatch):
        import app.api.files as files_mod
        import app.utils.user_scope as user_scope_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(real_settings, "allow_file_delete", True)
        monkeypatch.setattr(files_mod, "get_current_owner_id", lambda req: "alice")
        monkeypatch.setattr(user_scope_mod, "get_current_owner_id", lambda req: "alice")

        f = _create_file(db_session, owner_id="alice")

        resp = client.delete(f"/api/files/{f.id}")
        assert resp.status_code == 200

    def test_viewer_cannot_delete(self, client, db_session, monkeypatch):
        import app.api.files as files_mod
        import app.utils.user_scope as user_scope_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(real_settings, "allow_file_delete", True)
        monkeypatch.setattr(files_mod, "get_current_owner_id", lambda req: "bob")
        monkeypatch.setattr(user_scope_mod, "get_current_owner_id", lambda req: "bob")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="bob", role="viewer")
        db_session.add(share)
        db_session.commit()

        resp = client.delete(f"/api/files/{f.id}")
        assert resp.status_code == 403

    def test_editor_cannot_delete(self, client, db_session, monkeypatch):
        import app.api.files as files_mod
        import app.utils.user_scope as user_scope_mod
        from app.config import settings as real_settings

        monkeypatch.setattr(real_settings, "multi_user_enabled", True)
        monkeypatch.setattr(real_settings, "allow_file_delete", True)
        monkeypatch.setattr(files_mod, "get_current_owner_id", lambda req: "carol")
        monkeypatch.setattr(user_scope_mod, "get_current_owner_id", lambda req: "carol")

        f = _create_file(db_session, owner_id="alice")
        share = FileShare(file_id=f.id, owner_id="alice", shared_with_user_id="carol", role="editor")
        db_session.add(share)
        db_session.commit()

        resp = client.delete(f"/api/files/{f.id}")
        assert resp.status_code == 403
