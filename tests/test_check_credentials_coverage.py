"""Comprehensive tests for app/tasks/check_credentials.py to improve coverage."""

import json
import os
import time
from unittest.mock import MagicMock, mock_open, patch

import pytest


@pytest.mark.unit
class TestMockRequestClass:
    """Tests for MockRequest class."""

    def test_session_has_user(self):
        """Test MockRequest has user in session."""
        from app.tasks.check_credentials import MockRequest

        req = MockRequest()
        assert req.session["user"]["id"] == "credential_checker"

    def test_attributes(self):
        """Test MockRequest has expected attributes."""
        from app.tasks.check_credentials import MockRequest

        req = MockRequest()
        assert req.app is None
        assert isinstance(req.headers, dict)
        assert isinstance(req.query_params, dict)
        assert isinstance(req.path_params, dict)

    @pytest.mark.asyncio
    async def test_json_method(self):
        """Test json() returns empty dict."""
        from app.tasks.check_credentials import MockRequest

        req = MockRequest()
        result = await req.json()
        assert result == {}

    @pytest.mark.asyncio
    async def test_form_method(self):
        """Test form() returns empty dict."""
        from app.tasks.check_credentials import MockRequest

        req = MockRequest()
        result = await req.form()
        assert result == {}


@pytest.mark.unit
class TestGetFailureState:
    """Tests for get_failure_state function."""

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_cred_state_1.json")
    def test_returns_empty_when_no_file(self):
        """Test returns empty dict when file doesn't exist."""
        from app.tasks.check_credentials import get_failure_state

        if os.path.exists("/tmp/test_cred_state_1.json"):
            os.remove("/tmp/test_cred_state_1.json")
        result = get_failure_state()
        assert result == {}

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_cred_state_2.json")
    def test_reads_existing_state(self):
        """Test reads state from existing file."""
        from app.tasks.check_credentials import get_failure_state

        state = {"OpenAI": {"count": 3, "last_notified": 12345}}
        with open("/tmp/test_cred_state_2.json", "w") as f:
            json.dump(state, f)

        result = get_failure_state()
        assert result == state
        os.remove("/tmp/test_cred_state_2.json")

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_cred_state_3.json")
    @patch("builtins.open", side_effect=Exception("Permission denied"))
    @patch("app.tasks.check_credentials.os.path.exists", return_value=True)
    def test_returns_empty_on_read_error(self, mock_exists, mock_file):
        """Test returns empty dict on read error."""
        from app.tasks.check_credentials import get_failure_state

        result = get_failure_state()
        assert result == {}


@pytest.mark.unit
class TestSaveFailureState:
    """Tests for save_failure_state function."""

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_cred_save_1.json")
    def test_saves_state(self):
        """Test saves state to file."""
        from app.tasks.check_credentials import save_failure_state

        state = {"TestService": {"count": 1, "last_notified": 0}}
        save_failure_state(state)

        with open("/tmp/test_cred_save_1.json", "r") as f:
            loaded = json.load(f)
        assert loaded == state
        os.remove("/tmp/test_cred_save_1.json")

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/nonexistent/dir/state.json")
    def test_handles_write_error(self):
        """Test handles write error gracefully."""
        from app.tasks.check_credentials import save_failure_state

        # Should not raise
        save_failure_state({"test": {"count": 1}})


@pytest.mark.unit
class TestUnwrapDecoratedFunction:
    """Tests for unwrap_decorated_function."""

    def test_unwraps_single_level(self):
        """Test unwraps single level of decoration."""
        from app.tasks.check_credentials import unwrap_decorated_function

        def inner():
            return "inner"

        def wrapper():
            return inner()

        wrapper.__wrapped__ = inner

        result = unwrap_decorated_function(wrapper)
        assert result is inner

    def test_returns_undecorated(self):
        """Test returns same function if not decorated."""
        from app.tasks.check_credentials import unwrap_decorated_function

        def my_func():
            return "hello"

        result = unwrap_decorated_function(my_func)
        assert result is my_func

    def test_unwraps_multiple_levels(self):
        """Test unwraps nested decorators."""
        from app.tasks.check_credentials import unwrap_decorated_function

        def original():
            pass

        def mid():
            pass

        mid.__wrapped__ = original

        def outer():
            pass

        outer.__wrapped__ = mid

        result = unwrap_decorated_function(outer)
        assert result is original


@pytest.mark.unit
class TestSyncTestWrappers:
    """Tests for sync test wrapper functions."""

    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_openai_calls_inner(self, mock_unwrap):
        """Test sync_test_openai_connection calls unwrapped function."""
        from app.tasks.check_credentials import sync_test_openai_connection

        mock_inner = MagicMock(return_value={"status": "success", "message": "OK"})
        mock_unwrap.return_value = mock_inner

        result = sync_test_openai_connection()
        assert result["status"] == "success"
        mock_inner.assert_called_once()

    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_azure_calls_inner(self, mock_unwrap):
        """Test sync_test_azure_connection calls unwrapped function."""
        from app.tasks.check_credentials import sync_test_azure_connection

        mock_inner = MagicMock(return_value={"status": "error", "message": "Fail"})
        mock_unwrap.return_value = mock_inner

        result = sync_test_azure_connection()
        assert result["status"] == "error"

    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_dropbox_calls_inner(self, mock_unwrap):
        """Test sync_test_dropbox_token calls unwrapped function."""
        from app.tasks.check_credentials import sync_test_dropbox_token

        mock_inner = MagicMock(return_value={"status": "success"})
        mock_unwrap.return_value = mock_inner

        result = sync_test_dropbox_token()
        assert result["status"] == "success"

    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_google_drive_calls_inner(self, mock_unwrap):
        """Test sync_test_google_drive_token calls unwrapped function."""
        from app.tasks.check_credentials import sync_test_google_drive_token

        mock_inner = MagicMock(return_value={"status": "success"})
        mock_unwrap.return_value = mock_inner

        result = sync_test_google_drive_token()
        assert result["status"] == "success"

    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_onedrive_calls_inner(self, mock_unwrap):
        """Test sync_test_onedrive_token calls unwrapped function."""
        from app.tasks.check_credentials import sync_test_onedrive_token

        mock_inner = MagicMock(return_value={"status": "success"})
        mock_unwrap.return_value = mock_inner

        result = sync_test_onedrive_token()
        assert result["status"] == "success"


@pytest.mark.unit
class TestCheckCredentialsTask:
    """Tests for check_credentials Celery task."""

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    def test_all_unconfigured(self, mock_provider, mock_storage, mock_state, mock_save):
        """Test when all services are unconfigured."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": False},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {}

        result = check_credentials()
        assert result["checked"] == 0
        assert result["unconfigured"] == 5
        assert result["failures"] == 0

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_service_valid(self, mock_openai, mock_provider, mock_storage, mock_state, mock_save):
        """Test when a configured service is valid."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {}
        mock_openai.return_value = {"status": "success", "message": "OK"}

        result = check_credentials()
        assert result["checked"] == 1
        assert result["failures"] == 0
        assert result["results"]["OpenAI"]["status"] == "valid"

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_service_invalid_first_failure(
        self, mock_notify, mock_openai, mock_provider, mock_storage, mock_state, mock_save
    ):
        """Test when a configured service fails for the first time."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {}
        mock_openai.return_value = {"status": "error", "message": "API key invalid"}

        result = check_credentials()
        assert result["failures"] == 1
        assert result["results"]["OpenAI"]["status"] == "invalid"
        mock_notify.assert_called_once()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_service_invalid_suppressed_notification(
        self, mock_notify, mock_openai, mock_provider, mock_storage, mock_state, mock_save
    ):
        """Test notification suppressed after 3 consecutive failures."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        # Already failed 4 times
        mock_state.return_value = {"OpenAI": {"count": 4, "last_notified": 12345, "recovered": False}}
        mock_openai.return_value = {"status": "error", "message": "Still invalid"}

        result = check_credentials()
        assert result["failures"] == 1
        # Notification should not be sent (count > 3 and not recovered)
        mock_notify.assert_not_called()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_service_recovery(self, mock_openai, mock_provider, mock_storage, mock_state, mock_save):
        """Test service recovery after previous failures."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {"OpenAI": {"count": 3, "last_notified": 12345}}
        mock_openai.return_value = {"status": "success", "message": "OK"}

        result = check_credentials()
        assert result["failures"] == 0
        assert result["results"]["OpenAI"]["status"] == "valid"

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_service_exception(self, mock_notify, mock_openai, mock_provider, mock_storage, mock_state, mock_save):
        """Test handling when service check raises exception."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {}
        mock_openai.side_effect = Exception("Connection timeout")

        result = check_credentials()
        assert result["failures"] == 1
        assert result["results"]["OpenAI"]["status"] == "error"
        mock_notify.assert_called_once()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_recovered_service_re_notifies(
        self, mock_notify, mock_openai, mock_provider, mock_storage, mock_state, mock_save
    ):
        """Test that recovered service re-notifies on next failure."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        # Service was recovered (count > 3 but recovered flag is True)
        mock_state.return_value = {"OpenAI": {"count": 5, "last_notified": 12345, "recovered": True}}
        mock_openai.return_value = {"status": "error", "message": "Failed again"}

        result = check_credentials()
        assert result["failures"] == 1
        # Should re-notify because recovered was True
        mock_notify.assert_called_once()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    def test_unconfigured_with_config_issues(self, mock_provider, mock_storage, mock_state, mock_save):
        """Test unconfigured service with config issues."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": False},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {"dropbox": ["Missing DROPBOX_APP_KEY", "Missing DROPBOX_APP_SECRET"]}
        mock_state.return_value = {}

        result = check_credentials()
        assert result["results"]["Dropbox"]["status"] == "unconfigured"
        assert "Missing DROPBOX_APP_KEY" in result["results"]["Dropbox"]["message"]

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_previously_failed_now_recovered_clears_state(
        self, mock_openai, mock_provider, mock_storage, mock_state, mock_save
    ):
        """Test that recovery resets failure count."""
        from app.tasks.check_credentials import check_credentials

        mock_provider.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage.return_value = {}
        mock_state.return_value = {"OpenAI": {"count": 2, "last_notified": 12345}}
        mock_openai.return_value = {"status": "success", "message": "OK"}

        result = check_credentials()
        # Verify save was called with recovered state
        save_call_args = mock_save.call_args[0][0]
        assert save_call_args["OpenAI"]["count"] == 0
        assert save_call_args["OpenAI"]["recovered"] is True
