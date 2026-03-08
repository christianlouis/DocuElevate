"""Comprehensive unit tests for app/tasks/finalize_document_storage.py module."""

from unittest.mock import MagicMock, patch

import pytest

from app.tasks.finalize_document_storage import finalize_document_storage

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_file_record(file_id: int = 123, owner_id=None):
    """Return a lightweight MagicMock that mimics a FileRecord."""
    rec = MagicMock()
    rec.id = file_id
    rec.owner_id = owner_id
    return rec


@pytest.mark.unit
class TestFinalizeDocumentStorage:
    """Tests for finalize_document_storage Celery task."""

    @pytest.fixture(autouse=True)
    def _patch_celery_tasks(self, mocker):
        """Prevent all lazy-imported Celery tasks from actually connecting to Redis."""
        mocker.patch("app.tasks.compute_embedding.compute_document_embedding")
        mocker.patch("app.tasks.convert_to_pdfa.convert_to_pdfa", create=True)

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_successful_finalization(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test successful document finalization with all services configured."""
        mock_get_services.return_value = {
            "dropbox": True,
            "google_drive": True,
            "nextcloud": False,
            "s3": True,
        }

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(123, owner_id=None)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

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

                    # owner_id=None → global routing
                    mock_send_all.delay.assert_called_once_with("/workdir/processed/test_document.pdf", True, 123)
                    mock_send_user.delay.assert_not_called()

                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    assert notify_args["filename"] == "test_document.pdf"
                    assert notify_args["file_size"] == 102400
                    assert notify_args["metadata"] == metadata
                    assert "Dropbox" in notify_args["destinations"]
                    assert "Google Drive" in notify_args["destinations"]
                    assert "S3" in notify_args["destinations"]

                    assert result["status"] == "Completed"
                    assert result["file"] == "/workdir/processed/test_document.pdf"

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_retrieves_file_id_from_database_when_not_provided(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test file_id retrieval from database when not provided."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(456, owner_id=None)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=50000):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="doc.pdf"):
                    with patch(
                        "app.tasks.finalize_document_storage.os.path.join", return_value="/tmp/tmp/original.pdf"
                    ):
                        with patch("app.tasks.finalize_document_storage.settings") as mock_settings:
                            mock_settings.workdir = "/tmp"
                            mock_settings.enable_pdfa_conversion = False

                            finalize_document_storage.request.id = "test-task-id"

                            result = finalize_document_storage.__wrapped__(
                                original_file="/tmp/original.pdf",
                                processed_file="/workdir/processed/doc.pdf",
                                metadata={"filename": "doc.pdf"},
                                file_id=None,  # Not provided
                            )

                            # Verify database was queried
                            mock_db.query.assert_called_once()

                            # Verify send_to_all was called (global routing — no user destinations)
                            mock_send_all.delay.assert_called_once()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_no_configured_services(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test handles case when no services are configured."""
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

                    # Should still queue global uploads (even if none configured)
                    mock_send_all.delay.assert_called_once()

                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    assert notify_args["destinations"] == []

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_get_configured_services_exception(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test handles exception when getting configured services."""
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

                    assert result["status"] == "Completed"

                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    assert "configured destinations" in notify_args["destinations"]

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_notification_failure(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test handles notification failure gracefully."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

                    assert result["status"] == "Completed"
                    mock_send_all.delay.assert_called_once()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_handles_missing_file(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test handles case when processed file doesn't exist."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=False):
            with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="missing.pdf"):
                finalize_document_storage.request.id = "test-task-id"

                result = finalize_document_storage.__wrapped__(
                    original_file="/tmp/original.pdf",
                    processed_file="/workdir/processed/missing.pdf",
                    metadata={"filename": "missing.pdf"},
                    file_id=303,
                )

                mock_send_all.delay.assert_called_once()

                mock_notify.assert_called_once()
                notify_args = mock_notify.call_args[1]
                assert notify_args["file_size"] == 0

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_formats_service_names_for_display(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """Test that service names are formatted correctly for display."""
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

                    mock_notify.assert_called_once()
                    notify_args = mock_notify.call_args[1]
                    destinations = notify_args["destinations"]
                    assert "Google Drive" in destinations
                    assert "One Drive" in destinations
                    assert "Next Cloud" not in destinations

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_passes_delete_after_flag_to_send_all(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
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

                    mock_send_all.delay.assert_called_once_with("/workdir/processed/file.pdf", True, 505)

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_pdfa_enabled_does_not_regress_finalize_step_to_in_progress(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """
        Regression test: when PDF/A conversion is enabled, the finalize_document_storage
        step must NOT be logged as in_progress after it has already been logged as success.
        """
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=1024):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="doc.pdf"):
                    with patch("app.tasks.finalize_document_storage.settings") as mock_settings:
                        mock_settings.workdir = "/tmp"
                        mock_settings.enable_pdfa_conversion = True

                        mock_convert = MagicMock()
                        with patch(
                            "app.tasks.finalize_document_storage.convert_to_pdfa",
                            mock_convert,
                            create=True,
                        ):
                            finalize_document_storage.request.id = "test-task-id"

                            finalize_document_storage.__wrapped__(
                                original_file="/tmp/original.pdf",
                                processed_file="/workdir/processed/doc.pdf",
                                metadata={"filename": "doc.pdf"},
                                file_id=606,
                            )

                        # Collect all logged calls for finalize_document_storage step
                        finalize_calls = [
                            c for c in mock_log_progress.call_args_list if c.args[1] == "finalize_document_storage"
                        ]

                        statuses = [c.args[2] for c in finalize_calls]
                        assert "success" in statuses, "finalize_document_storage must be logged as success"
                        assert statuses[-1] == "success", (
                            "finalize_document_storage must not be regressed to in_progress after success; "
                            f"got statuses: {statuses}"
                        )


@pytest.mark.unit
class TestFinalizeDocumentStorageUserRouting:
    """Tests for user-specific destination routing in finalize_document_storage."""

    @pytest.fixture(autouse=True)
    def _patch_celery_tasks(self, mocker):
        """Prevent all lazy-imported Celery tasks from actually connecting to Redis."""
        mocker.patch("app.tasks.compute_embedding.compute_document_embedding")
        mocker.patch("app.tasks.convert_to_pdfa.convert_to_pdfa", create=True)

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=2)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_routes_to_user_destinations_when_owner_has_integrations(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """When a user has active DESTINATION integrations, use them instead of global config."""
        mock_get_services.return_value = {"dropbox": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(100, owner_id="alice@example.com")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=1024):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="doc.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/doc.pdf",
                        metadata={"filename": "doc.pdf"},
                        file_id=100,
                    )

        mock_send_user.delay.assert_called_once_with("/workdir/processed/doc.pdf", "alice@example.com", 100)
        mock_send_all.delay.assert_not_called()
        assert result["status"] == "Completed"

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_falls_back_to_global_when_owner_has_no_integrations(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """When a user has no active DESTINATION integrations, fall back to global config."""
        mock_get_services.return_value = {"s3": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(200, owner_id="bob@example.com")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=2048):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="file.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/file.pdf",
                        metadata={"filename": "file.pdf"},
                        file_id=200,
                    )

        mock_send_all.delay.assert_called_once_with("/workdir/processed/file.pdf", True, 200)
        mock_send_user.delay.assert_not_called()
        assert result["status"] == "Completed"

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count", return_value=0)
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_falls_back_to_global_when_no_owner(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """When a document has no owner (single-user mode), global destinations are used."""
        mock_get_services.return_value = {"nextcloud": True}

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(300, owner_id=None)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=512):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="scan.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/scan.pdf",
                        metadata={"filename": "scan.pdf"},
                        file_id=300,
                    )

        mock_send_all.delay.assert_called_once_with("/workdir/processed/scan.pdf", True, 300)
        mock_send_user.delay.assert_not_called()
        # get_user_destination_count must NOT be called when owner_id is None
        mock_get_dest_count.assert_not_called()

    @patch("app.tasks.finalize_document_storage.notify_file_processed")
    @patch("app.tasks.finalize_document_storage.send_to_user_destinations")
    @patch("app.tasks.finalize_document_storage.send_to_all_destinations")
    @patch("app.tasks.finalize_document_storage.get_user_destination_count")
    @patch("app.tasks.finalize_document_storage.get_configured_services_from_validator")
    @patch("app.tasks.finalize_document_storage.log_task_progress")
    @patch("app.tasks.finalize_document_storage.SessionLocal")
    def test_falls_back_to_global_when_count_lookup_fails(
        self,
        mock_session_local,
        mock_log_progress,
        mock_get_services,
        mock_get_dest_count,
        mock_send_all,
        mock_send_user,
        mock_notify,
    ):
        """When get_user_destination_count raises, fall back to global routing gracefully."""
        mock_get_services.return_value = {"s3": True}
        mock_get_dest_count.side_effect = Exception("DB connection error")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = _make_file_record(400, owner_id="charlie@example.com")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file_record

        with patch("app.tasks.finalize_document_storage.os.path.exists", return_value=True):
            with patch("app.tasks.finalize_document_storage.os.path.getsize", return_value=4096):
                with patch("app.tasks.finalize_document_storage.os.path.basename", return_value="file.pdf"):
                    finalize_document_storage.request.id = "test-task-id"

                    result = finalize_document_storage.__wrapped__(
                        original_file="/tmp/original.pdf",
                        processed_file="/workdir/processed/file.pdf",
                        metadata={"filename": "file.pdf"},
                        file_id=400,
                    )

        mock_send_all.delay.assert_called_once_with("/workdir/processed/file.pdf", True, 400)
        mock_send_user.delay.assert_not_called()
        assert result["status"] == "Completed"
