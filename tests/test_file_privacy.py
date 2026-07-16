"""Owner-controlled file privacy API tests."""

from unittest.mock import patch

import pytest

from app.models import FileRecord


def _file(db_session, owner_id="alice") -> FileRecord:
    record = FileRecord(
        owner_id=owner_id,
        filehash="privacy-hash",
        original_filename="privacy.pdf",
        local_filename="/tmp/privacy.pdf",
        file_size=123,
        mime_type="application/pdf",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


@pytest.mark.unit
def test_owner_can_set_and_clear_private_flag(client, db_session):
    record = _file(db_session)
    with (
        patch("app.api.files.get_current_owner_id", return_value="alice"),
        patch("app.utils.user_scope.settings.multi_user_enabled", True),
    ):
        response = client.put(f"/api/files/{record.id}/privacy", json={"is_private": True})
        assert response.status_code == 200
        assert response.json() == {"file_id": record.id, "is_private": True}
        db_session.refresh(record)
        assert record.is_private is True

        response = client.put(f"/api/files/{record.id}/privacy", json={"is_private": False})
        assert response.status_code == 200
        db_session.refresh(record)
        assert record.is_private is False


@pytest.mark.unit
def test_admin_cannot_change_another_owners_private_flag(client, db_session):
    record = _file(db_session)
    with (
        patch("app.api.files.get_current_owner_id", return_value="admin"),
        patch("app.utils.user_scope.settings.multi_user_enabled", True),
    ):
        response = client.put(f"/api/files/{record.id}/privacy", json={"is_private": True})
    assert response.status_code == 403
    db_session.refresh(record)
    assert record.is_private is False
