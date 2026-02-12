"""Comprehensive unit tests for app/tasks/finalize_document_storage.py module."""

from unittest.mock import MagicMock, patch

import pytest

from app.tasks.finalize_document_storage import finalize_document_storage


@pytest.mark.unit
class TestFinalizeDocumentStorage:
    """Tests for finalize_document_storage Celery task."""

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_successful_finalization(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test successful document finalization with all services configured."""
        # Mock configured services
        mock_get_services.return_value = {
            "dropbox": True,
            "google_drive": True,
            "nextcloud": False,
            "s3": True,
        }

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 123
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        # Mock file existence and size
        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=102400):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="test_document.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    metadata = {
                        "filename": "test_document.pdf",
                        "document_type": "Invoice",
                        "tags": ["invoice", "test"],
                    }

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/test_document.pdf",
                        metadata=metadata,
                        file_id=123,
                    )

                    # Verify send_to_all_destinations was queued
                    mock_send_all.delay.assert_called_once_with("/workdir/processed/test_document.pdf", True, 123)

                    # Verify notification was sent
                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    assert notify_args["filename"] == "test_document.pdf"
                    assert notify_args["file_size"] == 102400
                    assert notify_args["metadata"] == metadata
                    assert "Dropbox" in notify_args["destinations"]
                    assert "Google Drive" in notify_args["destinations"]
                    assert "S3" in notify_args["destinations"]

                    # Verify result
                    assert result["status"] == "Completed"
                    assert result["file"] == "/workdir/processed/test_document.pdf"

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_retrieves_file_id_from_database_when_not_provided(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test file_id retrieval from database when not provided."""
        mock_get_services.return_value = {"dropbox": True}

        # Mock database session to return a file record
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 456
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=50000):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="doc.pdf"):
                    with patch("app.tasks.finalize_document_storage.os.path.join", return_value="/tmp/tmp/original.pdf"):
                        with patch("app.tasks.finalize_document_storage.settings") as mock_settings:
                            mock_settings.workdir = "/tmp"

                            finalize_document_storage.request.id = "test-task-id"

                            result = finalize_document_storage.__wrapped__(
                                original_file="/tmp/original.pdf",
                                processed_file="/workdir/processed/doc.pdf",
                                metadata={"filename": "doc.pdf"},
                                file_id=None,  # Not provided
                            )

                            # Verify database was queried
                            mock_db.query.assert_called_once()

                            # Verify send_to_all was called with retrieved file_id
                            mock_send_all.delay.assert_called_once()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_no_configured_services(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test handles case when no services are configured."""
        # No services configured
        mock_get_services.return_value = {
            "dropbox": False,
            "google_drive": False,
            "nextcloud": False,
            "s3": False,
        }

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=1024):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="test.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/test.pdf",
                        metadata={"filename": "test.pdf"},
                        file_id=789,
                    )

                    # Should still queue uploads (even if none configured)
                    mock_send_all.delay.assert_called_once()

                    # Should still send notification
                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    # No services configured means empty destinations list
                    assert notify_args["destinations"] == []

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_get_configured_services_exception(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test handles exception when getting configured services."""
        # Simulate exception
        mock_get_services.side_effect = Exception("Service validation failed")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=2048):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="file.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/file.pdf",
                        metadata={"filename": "file.pdf"},
                        file_id=101,
                    )

                    # Should still complete successfully
                    assert result["status"] == "Completed"

                    # Should use fallback destinations
                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    assert "configured destinations" in notify_args["destinations"]

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_notification_failure(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test handles notification failure gracefully."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Simulate notification failure
        mock_notify.side_effect = Exception("Notification service unavailable")

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=4096):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="doc.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/doc.pdf",
                        metadata={"filename": "doc.pdf"},
                        file_id=202,
                    )

                    # Should still complete successfully despite notification failure
                    assert result["status"] == "Completed"

                    # Should still queue uploads
                    mock_send_all.delay.assert_called_once()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_missing_file(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test handles case when processed file doesn't exist."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # File doesn't exist
        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=False):
            with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="missing.pdf"):
                finalize_document_storage.request.id = "test-task-id"

                result = finalize_document_storage.__wrapped__(
                    original_file="/tmp/original.pdf",
                    processed_file="/workdir/processed/missing.pdf",
                    metadata={"filename": "missing.pdf"},
                    file_id=303,
                )

                # Should still queue uploads (send_to_all handles missing files)
                mock_send_all.delay.assert_called_once()

                # Notification should use file_size = 0
                mock_notify.assert_called_once()
                notify_args = mock_notify.call_args[1]
                assert notify_args["file_size"] == 0

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_formats_service_names_for_display(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test that service names are formatted correctly for display."""
        # Mock services with underscores in names
        mock_get_services.return_value = {
            "google_drive": True,
            "one_drive": True,
            "next_cloud": False,
        }

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=8192):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="test.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/test.pdf",
                        metadata={"filename": "test.pdf"},
                        file_id=404,
                    )

                    # Verify service names are formatted with spaces and title case
                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    destinations = notify_args["destinations"]
                    assert "Google Drive" in destinations
                    assert "One Drive" in destinations
                    assert "Next Cloud" not in destinations  # Not configured

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_passes_delete_after_flag_to_send_all(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_send_all,
        mock_notify,
    ):
        """Test that delete_after flag is correctly passed to send_to_all_destinations."""
        mock_get_services.return_value = {"s3": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=1024):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="file.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/file.pdf",
                        metadata={"filename": "file.pdf"},
                        file_id=505,
                    )

                    # Verify send_to_all was called with delete_after=True
                    mock_send_all.delay.assert_called_once_with("/workdir/processed/file.pdf", True, 505)
