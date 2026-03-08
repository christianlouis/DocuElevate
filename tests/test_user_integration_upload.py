"""Unit tests for app/tasks/upload_to_user_integration.py and related helpers."""

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_integration(
    int_id: int = 1,
    int_type=None,
    owner_id: str = "user@example.com",
    name: str = "My Integration",
    config_dict: dict | None = None,
    creds_dict: dict | None = None,
):
    """Build a MagicMock resembling a UserIntegration row."""
    from app.models import IntegrationDirection, IntegrationType

    if int_type is None:
        int_type = IntegrationType.S3
    rec = MagicMock()
    rec.id = int_id
    rec.integration_type = int_type
    rec.owner_id = owner_id
    rec.name = name
    rec.config = json.dumps(config_dict or {})
    rec.credentials = json.dumps(creds_dict or {})  # plain JSON in tests (not encrypted)
    rec.is_active = True
    rec.direction = IntegrationDirection.DESTINATION
    # Prevent last_used_at / last_error from being MagicMock initially
    rec.last_used_at = None
    rec.last_error = None
    return rec


def _run_upload_task(file_path: str, integration_id: int, file_id: int | None = None):
    """Call the upload_to_user_integration task's __wrapped__ function directly."""
    from app.tasks.upload_to_user_integration import upload_to_user_integration

    upload_to_user_integration.request.id = "test-task-id"
    return upload_to_user_integration.__wrapped__(
        file_path=file_path,
        integration_id=integration_id,
        file_id=file_id,
    )


# ---------------------------------------------------------------------------
# Tests for upload_to_user_integration task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadToUserIntegration:
    """Unit tests for the upload_to_user_integration Celery task."""

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_raises_file_not_found(self, mock_session_local, mock_log_progress):
        """FileNotFoundError is raised when the file does not exist."""
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db

        with pytest.raises(FileNotFoundError):
            _run_upload_task("/nonexistent/file.pdf", integration_id=1)

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_raises_value_error_when_integration_not_found(self, mock_session_local, mock_log_progress, tmp_path):
        """ValueError is raised when the integration record does not exist."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            _run_upload_task(str(test_file), integration_id=99)

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_skips_imap_source_type(self, mock_session_local, mock_log_progress, tmp_path):
        """Integration types with no registered handler return status='Skipped'."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType

        integration = _make_integration(int_id=2, int_type=IntegrationType.IMAP)

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        result = _run_upload_task(str(test_file), integration_id=2)

        assert result["status"] == "Skipped"

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_dispatches_to_correct_handler(self, mock_session_local, mock_log_progress, tmp_path):
        """The correct handler is called for a given integration type."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType
        from app.tasks.upload_to_user_integration import _UPLOAD_HANDLERS

        integration = _make_integration(
            int_id=3,
            int_type=IntegrationType.S3,
            config_dict={"bucket": "my-bucket", "region": "us-east-1"},
            creds_dict={"access_key_id": "AKI...", "secret_access_key": "secret"},
        )

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        mock_handler = MagicMock(return_value={"status": "Completed", "s3_key": "doc.pdf"})

        with patch.dict(_UPLOAD_HANDLERS, {IntegrationType.S3: mock_handler}):
            result = _run_upload_task(str(test_file), integration_id=3, file_id=42)

        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        assert call_args[0] == str(test_file)  # file_path
        assert call_args[1]["bucket"] == "my-bucket"  # cfg
        assert call_args[2]["access_key_id"] == "AKI..."  # creds
        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_persists_last_used_at_on_success(self, mock_session_local, mock_log_progress, tmp_path):
        """On success, last_used_at is updated and last_error is cleared."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType
        from app.tasks.upload_to_user_integration import _UPLOAD_HANDLERS

        integration = _make_integration(int_id=4, int_type=IntegrationType.S3)
        integration.last_error = "previous error"

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        mock_handler = MagicMock(return_value={"status": "Completed"})

        with patch.dict(_UPLOAD_HANDLERS, {IntegrationType.S3: mock_handler}):
            result = _run_upload_task(str(test_file), integration_id=4, file_id=10)

        assert result["status"] == "Completed"
        assert integration.last_used_at is not None
        assert integration.last_error is None

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_persists_error_and_reraises_on_failure(self, mock_session_local, mock_log_progress, tmp_path):
        """On failure, last_error is persisted on the integration and the exception is re-raised."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType
        from app.tasks.upload_to_user_integration import _UPLOAD_HANDLERS

        integration = _make_integration(int_id=5, int_type=IntegrationType.DROPBOX)

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        mock_handler = MagicMock(side_effect=RuntimeError("Dropbox token expired"))

        with patch.dict(_UPLOAD_HANDLERS, {IntegrationType.DROPBOX: mock_handler}):
            with pytest.raises(RuntimeError, match="Dropbox token expired"):
                _run_upload_task(str(test_file), integration_id=5, file_id=20)

        assert integration.last_error == "Dropbox token expired"

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_invalid_config_json_raises_value_error(self, mock_session_local, mock_log_progress, tmp_path):
        """ValueError is raised when integration.config contains invalid JSON."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType

        integration = _make_integration(int_id=6, int_type=IntegrationType.S3)
        integration.config = "NOT JSON"  # corrupt config

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        with pytest.raises(ValueError, match="invalid JSON in config"):
            _run_upload_task(str(test_file), integration_id=6)

    @patch("app.tasks.upload_to_user_integration.log_task_progress")
    @patch("app.tasks.upload_to_user_integration.decrypt_value")
    @patch("app.tasks.upload_to_user_integration.SessionLocal")
    def test_uses_decrypt_value_for_credentials(self, mock_session_local, mock_decrypt, mock_log_progress, tmp_path):
        """credentials are decrypted using decrypt_value before being parsed as JSON."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        from app.models import IntegrationType
        from app.tasks.upload_to_user_integration import _UPLOAD_HANDLERS

        integration = _make_integration(
            int_id=7,
            int_type=IntegrationType.S3,
            config_dict={"bucket": "b", "region": "eu-west-1"},
        )
        # Simulate encrypted credentials stored in DB
        integration.credentials = "enc:encrypted-value"
        # decrypt_value should return plain JSON
        mock_decrypt.return_value = json.dumps({"access_key_id": "AKI...", "secret_access_key": "S"})

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = integration

        mock_handler = MagicMock(return_value={"status": "Completed"})

        with patch.dict(_UPLOAD_HANDLERS, {IntegrationType.S3: mock_handler}):
            _run_upload_task(str(test_file), integration_id=7)

        mock_decrypt.assert_called_once_with("enc:encrypted-value")
        # Handler should receive decrypted credentials
        _, _, creds, _ = mock_handler.call_args[0]
        assert creds["access_key_id"] == "AKI..."


# ---------------------------------------------------------------------------
# Tests for send_to_user_destinations task
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendToUserDestinations:
    """Unit tests for the send_to_user_destinations Celery task."""

    def _run_task(self, file_path: str, owner_id: str, file_id: int | None = None):
        """Call the task's __wrapped__ function directly."""
        from app.tasks.send_to_all import send_to_user_destinations

        send_to_user_destinations.request.id = "test-task-id"
        return send_to_user_destinations.__wrapped__(
            file_path=file_path,
            owner_id=owner_id,
            file_id=file_id,
        )

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    def test_raises_file_not_found(self, mock_session_local, mock_log_progress):
        """FileNotFoundError is raised when file does not exist."""
        with pytest.raises(FileNotFoundError):
            self._run_task("/nonexistent/file.pdf", owner_id="user@example.com")

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    def test_returns_zero_when_no_integrations(self, mock_session_local, mock_log_progress, tmp_path):
        """Returns queued=0 when there are no active DESTINATION integrations."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = self._run_task(str(test_file), owner_id="nobody@example.com", file_id=1)

        assert result["queued"] == 0
        assert result["status"] == "Queued"

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    def test_dispatches_one_task_per_integration(self, mock_session_local, mock_log_progress, tmp_path):
        """One upload_to_user_integration.delay call is made per active DESTINATION integration."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF")

        from app.models import IntegrationType

        int1 = _make_integration(int_id=10, int_type=IntegrationType.S3, name="S3 Backup")
        int2 = _make_integration(int_id=11, int_type=IntegrationType.DROPBOX, name="Dropbox")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = [int1, int2]

        mock_celery_task = MagicMock()
        mock_celery_task.delay.return_value = MagicMock(id="celery-task-id")

        # The lazy import inside send_to_user_destinations uses:
        # "from app.tasks.upload_to_user_integration import upload_to_user_integration"
        # We must patch at the source module so the local import picks up the mock.
        with patch(
            "app.tasks.upload_to_user_integration.upload_to_user_integration",
            mock_celery_task,
        ):
            result = self._run_task(str(test_file), owner_id="user@example.com", file_id=99)

        assert result["queued"] == 2
        assert mock_celery_task.delay.call_count == 2
        # Verify correct arguments
        mock_celery_task.delay.assert_any_call(str(test_file), 10, 99)
        mock_celery_task.delay.assert_any_call(str(test_file), 11, 99)

    @patch("app.tasks.send_to_all.log_task_progress")
    @patch("app.tasks.send_to_all.SessionLocal")
    def test_continues_on_individual_dispatch_failure(self, mock_session_local, mock_log_progress, tmp_path):
        """If queuing one integration fails, the others are still queued."""
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF")

        from app.models import IntegrationType

        int1 = _make_integration(int_id=20, int_type=IntegrationType.S3, name="S3")
        int2 = _make_integration(int_id=21, int_type=IntegrationType.DROPBOX, name="Dropbox")

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = [int1, int2]

        mock_celery_task = MagicMock()
        # First call fails, second succeeds
        mock_celery_task.delay.side_effect = [RuntimeError("connection refused"), MagicMock(id="ok")]

        with patch(
            "app.tasks.upload_to_user_integration.upload_to_user_integration",
            mock_celery_task,
        ):
            result = self._run_task(str(test_file), owner_id="user@example.com", file_id=50)

        # Only 1 successfully queued (the second one)
        assert result["queued"] == 1
        assert "integration_20_error" in result["tasks"]


# ---------------------------------------------------------------------------
# Tests for get_user_destination_count helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetUserDestinationCount:
    """Unit tests for the get_user_destination_count helper function."""

    @patch("app.tasks.send_to_all.SessionLocal")
    def test_returns_count_from_db(self, mock_session_local):
        """Returns the number of active DESTINATION integrations for an owner."""
        from app.tasks.send_to_all import get_user_destination_count

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.count.return_value = 3

        assert get_user_destination_count("user@example.com") == 3

    @patch("app.tasks.send_to_all.SessionLocal")
    def test_returns_zero_when_no_integrations(self, mock_session_local):
        """Returns 0 when no active DESTINATION integrations are configured."""
        from app.tasks.send_to_all import get_user_destination_count

        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        assert get_user_destination_count("empty@example.com") == 0
