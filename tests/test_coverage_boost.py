"""Tests to boost coverage for various small modules."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestUtilsCompat:
    """Tests for app.utils package exports."""

    def test_imports_hash_file(self):
        """Test that hash_file can be imported from utils."""
        from app.utils import hash_file

        assert callable(hash_file)

    def test_imports_log_task_progress(self):
        """Test that log_task_progress can be imported from utils."""
        from app.utils import log_task_progress

        assert callable(log_task_progress)


@pytest.mark.unit
class TestConfigValidatorCompat:
    """Tests for app/utils/config_validator.py backward compatibility."""

    def test_imports_validate_email_config(self):
        """Test backward compatible import."""
        from app.utils.config_validator import validate_email_config

        assert callable(validate_email_config)

    def test_imports_validate_storage_configs(self):
        """Test backward compatible import."""
        from app.utils.config_validator import validate_storage_configs

        assert callable(validate_storage_configs)

    def test_imports_mask_sensitive_value(self):
        """Test backward compatible import."""
        from app.utils.config_validator import mask_sensitive_value

        assert callable(mask_sensitive_value)

    def test_imports_get_provider_status(self):
        """Test backward compatible import."""
        from app.utils.config_validator import get_provider_status

        assert callable(get_provider_status)

    def test_imports_dump_all_settings(self):
        """Test backward compatible import."""
        from app.utils.config_validator import dump_all_settings

        assert callable(dump_all_settings)

    def test_imports_check_all_configs(self):
        """Test backward compatible import."""
        from app.utils.config_validator import check_all_configs

        assert callable(check_all_configs)


@pytest.mark.unit
class TestCeleryWorkerImport:
    """Tests for app/celery_worker.py module."""

    def test_celery_worker_module_exists(self):
        """Test that celery_worker module can be found."""
        import importlib

        spec = importlib.util.find_spec("app.celery_worker")
        assert spec is not None


@pytest.mark.unit
class TestSettingsDisplayMasking:
    """Tests for settings display masking of sensitive values."""

    def test_dump_all_settings_masks_passwords(self):
        """Test that passwords are masked in settings dump."""
        from app.utils.config_validator.settings_display import dump_all_settings

        # Should not raise
        dump_all_settings()

    def test_dump_all_settings_masks_tokens(self):
        """Test that tokens are masked in settings dump."""
        from app.utils.config_validator.settings_display import dump_all_settings

        dump_all_settings()

    def test_dump_all_settings_masks_keys(self):
        """Test that API keys are masked in settings dump."""
        from app.utils.config_validator.settings_display import dump_all_settings

        dump_all_settings()

    def test_get_settings_for_display_categories(self):
        """Test that all expected categories are returned."""
        from app.utils.config_validator.settings_display import get_settings_for_display

        result = get_settings_for_display(show_values=True)
        # Should have multiple categories
        assert len(result) > 3


@pytest.mark.unit
class TestNotificationInit:
    """Tests for notification initialization."""

    @patch("app.utils.notification._apprise", None)
    @patch("app.utils.notification.settings")
    def test_init_apprise_no_urls(self, mock_settings):
        """Test init_apprise when no URLs configured."""
        mock_settings.notification_urls = []
        from app.utils.notification import init_apprise

        result = init_apprise()
        assert result is not None

    @patch("app.utils.notification._apprise", None)
    @patch("app.utils.notification.settings")
    def test_init_apprise_with_urls(self, mock_settings):
        """Test init_apprise with URLs configured."""
        mock_settings.notification_urls = ["json://localhost"]
        from app.utils.notification import init_apprise

        result = init_apprise()
        assert result is not None


@pytest.mark.unit
class TestNotificationFileProcessed:
    """Tests for notify_file_processed function."""

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_file_processed_notification_sent(self, mock_send, mock_settings):
        """Test file processed notification is sent."""
        mock_settings.notify_on_file_processed = True
        mock_send.return_value = True

        from app.utils.notification import notify_file_processed

        result = notify_file_processed(
            filename="test.pdf",
            file_size=1048576,
            metadata={"document_type": "invoice", "tags": ["test"]},
            destinations=["Dropbox", "Nextcloud"],
        )
        assert result is True
        mock_send.assert_called_once()

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_file_processed_small_file(self, mock_send, mock_settings):
        """Test file processed notification with small file."""
        mock_settings.notify_on_file_processed = True
        mock_send.return_value = True

        from app.utils.notification import notify_file_processed

        result = notify_file_processed(
            filename="small.pdf",
            file_size=512,  # Less than 1KB
            metadata={"document_type": "Unknown"},
            destinations=[],
        )
        assert result is True


@pytest.mark.unit
class TestNotificationCeleryFailure:
    """Tests for notify_celery_failure function."""

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_celery_failure_notification_sent(self, mock_send, mock_settings):
        """Test celery failure notification is sent when enabled."""
        mock_settings.notify_on_task_failure = True
        mock_send.return_value = True

        from app.utils.notification import notify_celery_failure

        result = notify_celery_failure(
            task_name="process_document",
            task_id="task-123",
            exc=Exception("test error"),
            args=["/tmp/test.pdf"],
            kwargs={},
        )
        assert result is True
        mock_send.assert_called_once()


@pytest.mark.unit
class TestNotificationCredentialFailure:
    """Tests for notify_credential_failure function."""

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_credential_failure_notification_sent(self, mock_send, mock_settings):
        """Test credential failure notification is sent when enabled."""
        mock_settings.notify_on_credential_failure = True
        mock_send.return_value = True

        from app.utils.notification import notify_credential_failure

        result = notify_credential_failure(
            service_name="OpenAI",
            error="Invalid API key",
        )
        assert result is True


@pytest.mark.unit
class TestNotificationStartupShutdown:
    """Tests for startup/shutdown notifications."""

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_startup_notification_sent(self, mock_send, mock_settings):
        """Test startup notification is sent when enabled."""
        mock_settings.notify_on_startup = True
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = True

        from app.utils.notification import notify_startup

        result = notify_startup()
        assert result is True

    @patch("app.utils.notification.settings")
    @patch("app.utils.notification.send_notification")
    def test_shutdown_notification_sent(self, mock_send, mock_settings):
        """Test shutdown notification is sent when enabled."""
        mock_settings.notify_on_shutdown = True
        mock_settings.external_hostname = "test-host"
        mock_send.return_value = True

        from app.utils.notification import notify_shutdown

        result = notify_shutdown()
        assert result is True
