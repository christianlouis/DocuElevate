"""Only the requested owned destination is retried."""

from unittest.mock import MagicMock, patch

import pytest

from app.models import DestinationDeliveryPart, FileRecord, UserIntegration


@pytest.fixture
def destination_document(db_session, tmp_path):
    path = tmp_path / "processed.pdf"
    path.write_bytes(b"pdf")
    file = FileRecord(
        filehash="retry-destination",
        original_filename="doc.pdf",
        local_filename=str(path),
        processed_file_path=str(path),
        file_size=3,
        mime_type="application/pdf",
        owner_id="test-owner",
    )
    destination = UserIntegration(
        owner_id="test-owner", direction="DESTINATION", integration_type="EMAIL", name="Mail", is_active=True
    )
    db_session.add_all([file, destination])
    db_session.commit()
    return file, destination


def test_retry_queues_only_destination(client, destination_document):
    file, destination = destination_document
    with patch(
        "app.tasks.upload_to_user_integration.upload_to_user_integration.delay", return_value=MagicMock(id="retry")
    ) as queue:
        response = client.post(
            f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_user_integration_{destination.id}"
        )
    assert response.status_code == 200, response.text
    queue.assert_called_once_with(file.processed_file_path, destination.id, file_id=file.id)


@pytest.mark.parametrize("state", ["sending", "unknown", "accepted"])
def test_retry_blocks_uncertain_or_completed_delivery(client, db_session, destination_document, state):
    file, destination = destination_document
    db_session.add(
        DestinationDeliveryPart(
            file_id=file.id,
            integration_id=destination.id,
            content_hash="a" * 64,
            policy_hash="b" * 64,
            part_number=1,
            part_count=1,
            filename="doc.pdf",
            size_bytes=100,
            status=state,
        )
    )
    db_session.commit()
    with patch("app.tasks.upload_to_user_integration.upload_to_user_integration.delay") as queue:
        response = client.post(
            f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_user_integration_{destination.id}"
        )
    assert response.status_code == 409, response.text
    queue.assert_not_called()


def test_retry_rejects_other_owners_destination(client, db_session, destination_document):
    file, destination = destination_document
    destination.owner_id = "someone-else"
    db_session.commit()
    response = client.post(
        f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_user_integration_{destination.id}"
    )
    assert response.status_code == 404
