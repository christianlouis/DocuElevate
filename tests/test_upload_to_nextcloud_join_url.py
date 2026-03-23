import os
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.upload_to_nextcloud import upload_to_nextcloud


@pytest.fixture
def mock_settings():
    with patch("app.tasks.upload_to_nextcloud.settings") as mock:
        mock.nextcloud_upload_url = "http://nextcloud.local/"
        mock.nextcloud_username = "testuser"
        mock.nextcloud_password = "testpassword"
        mock.nextcloud_folder = "uploads"
        mock.workdir = "/tmp/workdir"
        mock.http_request_timeout = 30
        yield mock


@pytest.fixture
def mock_requests():
    with patch("app.tasks.upload_to_nextcloud.requests") as mock:
        # Mock PROPFIND to always return false (file doesn't exist)
        mock.request.return_value = MagicMock(text="<response></response>")

        # Mock PUT to return success
        put_response = MagicMock()
        put_response.status_code = 201
        mock.put.return_value = put_response
        yield mock


def test_upload_to_nextcloud_url_construction(mock_settings, mock_requests):
    file_path = "/tmp/workdir/test_file.txt"

    # Create dummy file
    os.makedirs("/tmp/workdir", exist_ok=True)
    with open(file_path, "w") as f:
        f.write("test content")

    # Call the task directly
    with patch("celery.app.task.Task.request", new_callable=MagicMock) as mock_req:
        mock_req.id = "test-task-123"
        result = upload_to_nextcloud(file_path)

    assert result["status"] == "Completed"
    assert result["nextcloud_path"] == "uploads/test_file.txt"

    # Verify requests.put was called with the correct URL
    mock_requests.put.assert_called_once()
    args, kwargs = mock_requests.put.call_args
    url = args[0]
    assert url == "http://nextcloud.local/uploads/test_file.txt"
