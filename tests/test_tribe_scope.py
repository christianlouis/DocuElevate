from unittest.mock import MagicMock, patch

import pytest

from app.config import settings
from app.models import FileRecord, TribeMembership
from app.utils.tribe_scope import canonical_tribe_name, ensure_document_scope, shared_tribe_id
from app.utils.user_scope import apply_owner_filter


@pytest.mark.unit
def test_personal_scope_is_stable_and_creates_membership(db_session):
    first = ensure_document_scope(db_session, "alice")
    second = ensure_document_scope(db_session, "alice")

    assert first == second
    assert db_session.query(TribeMembership).filter_by(user_id="alice", tribe_id=first[1]).count() == 1


@pytest.mark.unit
def test_shared_tribe_identity_uses_unicode_canonicalization():
    assert canonical_tribe_name("  Familie  Straße ") == canonical_tribe_name("Familie STRASSE")
    assert shared_tribe_id("Familie Straße") == shared_tribe_id("Familie STRASSE")


@pytest.mark.unit
def test_private_flag_is_canonical_inside_shared_tribe(db_session):
    tenant_id, tribe_id = ensure_document_scope(db_session, "alice")
    db_session.add(TribeMembership(tenant_id=tenant_id, tribe_id=tribe_id, user_id="bob", role="member"))
    public = FileRecord(
        filehash="public",
        local_filename="/tmp/public.pdf",
        file_size=1,
        owner_id="alice",
        tenant_id=tenant_id,
        tribe_id=tribe_id,
        is_private=False,
    )
    private = FileRecord(
        filehash="private",
        local_filename="/tmp/private.pdf",
        file_size=1,
        owner_id="alice",
        tenant_id=tenant_id,
        tribe_id=tribe_id,
        is_private=True,
    )
    db_session.add_all([public, private])
    db_session.commit()

    request = MagicMock()
    request.session = {"user": {"preferred_username": "bob"}}
    with patch.object(settings, "multi_user_enabled", True):
        visible = apply_owner_filter(db_session.query(FileRecord), request).all()

    assert [record.filehash for record in visible] == ["public"]
