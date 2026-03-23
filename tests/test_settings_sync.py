from unittest.mock import MagicMock, patch

import pytest

import app.utils.settings_sync
from app.utils.settings_sync import (
    SETTINGS_VERSION_KEY,
    notify_settings_updated,
    register_settings_reload_signal,
)


@pytest.fixture
def reset_last_seen_version():
    """Reset the global variable before and after tests."""
    app.utils.settings_sync._last_seen_version = ""
    yield
    app.utils.settings_sync._last_seen_version = ""


@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
@patch("app.utils.settings_sync.time.time", return_value=12345.0)
def test_notify_settings_updated_success(mock_time, mock_ensure_ocr, mock_reload, mock_redis):
    # Setup mock redis instance
    mock_redis_instance = MagicMock()
    mock_redis.return_value = mock_redis_instance

    notify_settings_updated()

    # Verify redis calls
    mock_redis.assert_called_once()
    mock_redis_instance.set.assert_called_once_with(SETTINGS_VERSION_KEY, "12345.0")

    # Verify other calls
    mock_reload.assert_called_once()
    mock_ensure_ocr.assert_called_once()


@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_notify_settings_updated_redis_failure(mock_ensure_ocr, mock_reload, mock_redis, caplog):
    # Setup mock redis to fail
    mock_redis.side_effect = Exception("Redis connection failed")

    notify_settings_updated()

    # Verification: should continue and call reload and ocr despite redis failure
    mock_reload.assert_called_once()
    mock_ensure_ocr.assert_called_once()
    assert "Could not publish settings update to Redis: Redis connection failed" in caplog.text


@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_notify_settings_updated_reload_failure(mock_ensure_ocr, mock_reload, mock_redis, caplog):
    # Setup reload to fail
    mock_reload.side_effect = Exception("Reload failed")

    mock_redis_instance = MagicMock()
    mock_redis.return_value = mock_redis_instance

    notify_settings_updated()

    # Verification: redis should be called, reload fails, ocr should still be called
    mock_redis_instance.set.assert_called_once()
    mock_ensure_ocr.assert_called_once()
    assert "Could not reload in-process settings: Reload failed" in caplog.text


@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_notify_settings_updated_ocr_failure(mock_ensure_ocr, mock_reload, mock_redis, caplog):
    # Setup ocr check to fail
    mock_ensure_ocr.side_effect = Exception("OCR check failed")

    mock_redis_instance = MagicMock()
    mock_redis.return_value = mock_redis_instance

    notify_settings_updated()

    # Verification: all should be called, ocr failure logged
    mock_redis_instance.set.assert_called_once()
    mock_reload.assert_called_once()
    assert "Could not schedule OCR language check: OCR check failed" in caplog.text


@patch("app.utils.settings_sync.task_prerun.connect")
def test_register_settings_reload_signal(mock_connect):
    register_settings_reload_signal()
    # It should register a signal with task_prerun
    mock_connect.assert_called_once_with(weak=False)


@patch("app.utils.settings_sync.task_prerun.connect")
@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_reload_if_stale_new_version(mock_ensure_ocr, mock_reload, mock_redis, mock_connect, reset_last_seen_version):
    # Capture the registered callback
    mock_decorator = MagicMock()
    mock_connect.return_value = mock_decorator

    register_settings_reload_signal()

    mock_connect.assert_called_once_with(weak=False)
    # Get the callback function
    callback = mock_decorator.call_args[0][0]

    # Setup redis to return a new version
    mock_redis_instance = MagicMock()
    mock_redis_instance.get.return_value = b"new_version"
    mock_redis.return_value = mock_redis_instance

    # Initial state check
    assert app.utils.settings_sync._last_seen_version == ""

    # Call the callback
    callback(sender="test")

    # Verification
    mock_redis_instance.get.assert_called_once_with(SETTINGS_VERSION_KEY)
    mock_reload.assert_called_once()
    mock_ensure_ocr.assert_called_once()
    assert app.utils.settings_sync._last_seen_version == "new_version"


@patch("app.utils.settings_sync.task_prerun.connect")
@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_reload_if_stale_same_version(mock_ensure_ocr, mock_reload, mock_redis, mock_connect, reset_last_seen_version):
    # Set initial state
    app.utils.settings_sync._last_seen_version = "existing_version"

    mock_decorator = MagicMock()
    mock_connect.return_value = mock_decorator
    register_settings_reload_signal()
    callback = mock_decorator.call_args[0][0]

    # Setup redis to return the SAME version
    mock_redis_instance = MagicMock()
    mock_redis_instance.get.return_value = b"existing_version"
    mock_redis.return_value = mock_redis_instance

    # Call the callback
    callback(sender="test")

    # Verification
    mock_redis_instance.get.assert_called_once_with(SETTINGS_VERSION_KEY)
    # Should NOT reload or check OCR
    mock_reload.assert_not_called()
    mock_ensure_ocr.assert_not_called()
    assert app.utils.settings_sync._last_seen_version == "existing_version"


@patch("app.utils.settings_sync.task_prerun.connect")
@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
def test_reload_if_stale_redis_error(mock_reload, mock_redis, mock_connect, reset_last_seen_version, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    mock_decorator = MagicMock()
    mock_connect.return_value = mock_decorator
    register_settings_reload_signal()
    callback = mock_decorator.call_args[0][0]

    # Setup redis to fail
    mock_redis.side_effect = Exception("Redis error")

    # Call the callback
    callback(sender="test")

    # Verification
    mock_reload.assert_not_called()
    assert "Settings version check skipped: Redis error" in caplog.text


@patch("app.utils.settings_sync.task_prerun.connect")
@patch("app.utils.settings_sync.redis.from_url")
@patch("app.utils.config_loader.reload_settings_from_db")
@patch("app.utils.ocr_language_manager.ensure_ocr_languages_async")
def test_reload_if_stale_ocr_error(
    mock_ensure_ocr, mock_reload, mock_redis, mock_connect, reset_last_seen_version, caplog
):
    mock_decorator = MagicMock()
    mock_connect.return_value = mock_decorator
    register_settings_reload_signal()
    callback = mock_decorator.call_args[0][0]

    # Setup redis to return a new version
    mock_redis_instance = MagicMock()
    mock_redis_instance.get.return_value = b"new_version"
    mock_redis.return_value = mock_redis_instance

    # Setup OCR check to fail
    mock_ensure_ocr.side_effect = Exception("OCR error")

    # Call the callback
    callback(sender="test")

    # Verification
    mock_reload.assert_called_once()
    mock_ensure_ocr.assert_called_once()
    assert "Could not schedule OCR language check on worker: OCR error" in caplog.text
    assert app.utils.settings_sync._last_seen_version == "new_version"
