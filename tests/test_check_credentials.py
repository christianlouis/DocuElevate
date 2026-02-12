"""Tests for app/tasks/check_credentials.py module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.check_credentials import (
    MockRequest,
    get_failure_state,
    save_failure_state,
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
