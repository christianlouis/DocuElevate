"""Tests for app/tasks/check_credentials.py module."""

import json
import os
from unittest.mock import Mock, patch

import pytest

from app.tasks.check_credentials import (
    MockRequest,
    check_credentials,
    get_failure_state,
    save_failure_state,
    sync_test_azure_connection,
    sync_test_openai_connection,
    unwrap_decorated_function,
)


@pytest.mark.unit
class TestMockRequest:
    """Tests for MockRequest class."""

    def test_mock_request_has_session(self):
        """Test MockRequest has session attribute."""
        req = MockRequest()
        assert "user" in req.session
        assert req.session["user"]["id"] == "credential_checker"

    def test_mock_request_has_attributes(self):
        """Test MockRequest has required attributes."""
        req = MockRequest()
        assert req.app is None
        assert isinstance(req.headers, dict)
        assert isinstance(req.query_params, dict)

    @pytest.mark.asyncio
    async def test_mock_request_json(self):
        """Test MockRequest.json() returns empty dict."""
        req = MockRequest()
        result = await req.json()
        assert result == {}

    @pytest.mark.asyncio
    async def test_mock_request_form(self):
        """Test MockRequest.form() returns empty dict."""
        req = MockRequest()
        result = await req.form()
        assert result == {}


@pytest.mark.unit
class TestGetFailureState:
    """Tests for get_failure_state function."""

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_failure_state.json")
    def test_returns_empty_dict_when_no_file(self):
        """Test returns empty dict when file doesn't exist."""
        # Ensure file doesn't exist
        if os.path.exists("/tmp/test_failure_state.json"):
            os.remove("/tmp/test_failure_state.json")
        result = get_failure_state()
        assert result == {}

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_failure_state.json")
    def test_reads_existing_state(self):
        """Test reads state from existing file."""
        state = {"OpenAI": {"count": 2, "last_notified": 12345}}
        with open("/tmp/test_failure_state.json", "w") as f:
            json.dump(state, f)

        result = get_failure_state()
        assert result == state

        # Clean up
        os.remove("/tmp/test_failure_state.json")

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_failure_state_invalid.json")
    def test_handles_invalid_json(self):
        """Test handles invalid JSON file."""
        with open("/tmp/test_failure_state_invalid.json", "w") as f:
            f.write("invalid json {")

        result = get_failure_state()
        assert result == {}

        # Clean up
        os.remove("/tmp/test_failure_state_invalid.json")


@pytest.mark.unit
class TestSaveFailureState:
    """Tests for save_failure_state function."""

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/tmp/test_failure_state_save.json")
    def test_saves_state_to_file(self):
        """Test saves state to file."""
        state = {"OpenAI": {"count": 1, "last_notified": 0}}
        save_failure_state(state)

        with open("/tmp/test_failure_state_save.json", "r") as f:
            loaded = json.load(f)
        assert loaded == state

        # Clean up
        os.remove("/tmp/test_failure_state_save.json")

    @patch("app.tasks.check_credentials.FAILURE_STATE_FILE", "/invalid/path/test.json")
    def test_handles_save_error(self):
        """Test handles save error gracefully."""
        state = {"OpenAI": {"count": 1}}
        # Should not raise exception
        save_failure_state(state)


@pytest.mark.unit
class TestUnwrapDecoratedFunction:
    """Tests for unwrap_decorated_function."""

    def test_returns_same_function_if_not_decorated(self):
        """Test returns same function if not decorated."""

        def my_func():
            return "hello"

        result = unwrap_decorated_function(my_func)
        assert result is my_func

    def test_unwraps_decorated_function(self):
        """Test unwraps decorated function."""

        def inner():
            return "hello"

        def wrapper():
            return inner()

        wrapper.__wrapped__ = inner

        result = unwrap_decorated_function(wrapper)
        assert result is inner

    def test_unwraps_multiple_levels(self):
        """Test unwraps multiple levels of decoration."""

        def original():
            return "hello"

        def middle():
            return original()

        middle.__wrapped__ = original

        def outer():
            return middle()

        outer.__wrapped__ = middle

        result = unwrap_decorated_function(outer)
        assert result is original


@pytest.mark.unit
class TestSyncTestFunctions:
    """Tests for sync test wrapper functions."""

    @patch("app.tasks.check_credentials.test_openai_connection")
    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    @patch("app.tasks.check_credentials.asyncio.run")
    def test_sync_test_openai_connection(self, mock_asyncio_run, mock_unwrap, mock_test_func):
        """Test sync wrapper for OpenAI connection test."""
        mock_inner = Mock()
        mock_inner.return_value = {"status": "success"}
        mock_unwrap.return_value = mock_inner

        # Mock as sync function
        import inspect

        with patch.object(inspect, "iscoroutinefunction", return_value=False):
            result = sync_test_openai_connection()

        mock_inner.assert_called_once()

    @patch("app.tasks.check_credentials.test_azure_connection")
    @patch("app.tasks.check_credentials.unwrap_decorated_function")
    def test_sync_test_azure_connection(self, mock_unwrap, mock_test_func):
        """Test sync wrapper for Azure connection test."""
        mock_inner = Mock()
        mock_inner.return_value = {"status": "success"}
        mock_unwrap.return_value = mock_inner

        import inspect

        with patch.object(inspect, "iscoroutinefunction", return_value=False):
            result = sync_test_azure_connection()

        mock_inner.assert_called_once()


@pytest.mark.unit
class TestCheckCredentialsTask:
    """Tests for check_credentials task."""

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.sync_test_azure_connection")
    @patch("app.tasks.check_credentials.sync_test_dropbox_token")
    @patch("app.tasks.check_credentials.sync_test_google_drive_token")
    @patch("app.tasks.check_credentials.sync_test_onedrive_token")
    def test_checks_all_configured_services(
        self,
        mock_onedrive,
        mock_gdrive,
        mock_dropbox,
        mock_azure,
        mock_openai,
        mock_storage_configs,
        mock_provider_status,
        mock_get_state,
        mock_save_state,
    ):
        """Test checks all configured services."""
        mock_get_state.return_value = {}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": True},
            "Dropbox": {"configured": True},
            "Google Drive": {"configured": True},
            "OneDrive": {"configured": True},
        }
        mock_storage_configs.return_value = {"dropbox": [], "google_drive": [], "onedrive": []}

        # All tests succeed
        mock_openai.return_value = {"status": "success"}
        mock_azure.return_value = {"status": "success"}
        mock_dropbox.return_value = {"status": "success"}
        mock_gdrive.return_value = {"status": "success"}
        mock_onedrive.return_value = {"status": "success"}

        result = check_credentials()

        assert result["checked"] == 5
        assert result["failures"] == 0

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_tracks_failures(
        self, mock_openai, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test tracks credential failures."""
        mock_get_state.return_value = {}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        mock_openai.return_value = {"status": "error", "message": "Invalid API key"}

        result = check_credentials()

        assert result["checked"] == 1
        assert result["failures"] == 1

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    def test_skips_unconfigured_services(
        self, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test skips unconfigured services."""
        mock_get_state.return_value = {}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": False},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        result = check_credentials()

        assert result["checked"] == 0
        assert result["unconfigured"] == 5

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_sends_notifications_on_failure(
        self, mock_notify, mock_openai, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test sends notifications on credential failure."""
        mock_get_state.return_value = {}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        mock_openai.return_value = {"status": "error", "message": "Invalid API key"}

        check_credentials()

        mock_notify.assert_called_once()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    @patch("app.tasks.check_credentials.notify_credential_failure")
    def test_suppresses_notifications_after_threshold(
        self, mock_notify, mock_openai, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test suppresses notifications after failure threshold."""
        # Existing state with 4 failures
        mock_get_state.return_value = {"OpenAI": {"count": 4, "last_notified": 12345}}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        mock_openai.return_value = {"status": "error", "message": "Invalid API key"}

        check_credentials()

        # Notification should be suppressed (already notified 3 times)
        mock_notify.assert_not_called()

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_tracks_recovery(
        self, mock_openai, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test tracks service recovery."""
        # Existing state with failures
        mock_get_state.return_value = {"OpenAI": {"count": 2, "last_notified": 12345}}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        # Service is now valid
        mock_openai.return_value = {"status": "success"}

        result = check_credentials()

        assert result["failures"] == 0

    @patch("app.tasks.check_credentials.save_failure_state")
    @patch("app.tasks.check_credentials.get_failure_state")
    @patch("app.tasks.check_credentials.get_provider_status")
    @patch("app.tasks.check_credentials.validate_storage_configs")
    @patch("app.tasks.check_credentials.sync_test_openai_connection")
    def test_handles_exception_during_check(
        self, mock_openai, mock_storage_configs, mock_provider_status, mock_get_state, mock_save_state
    ):
        """Test handles exception during credential check."""
        mock_get_state.return_value = {}
        mock_provider_status.return_value = {
            "OpenAI": {"configured": True},
            "Azure AI": {"configured": False},
            "Dropbox": {"configured": False},
            "Google Drive": {"configured": False},
            "OneDrive": {"configured": False},
        }
        mock_storage_configs.return_value = {}

        mock_openai.side_effect = Exception("Network error")

        result = check_credentials()

        # Should still complete and record the error
        assert result["failures"] == 1
        assert "OpenAI" in result["results"]
        assert result["results"]["OpenAI"]["status"] == "error"
