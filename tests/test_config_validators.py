"""Tests for app/utils/config_validator/validators.py module."""
import pytest
from unittest.mock import patch

from app.utils.config_validator.validators import (
    validate_storage_configs,
    validate_email_config,
    validate_notification_config,
    check_all_configs,
)


@pytest.mark.unit
class TestValidateStorageConfigs:
    """Tests for validate_storage_configs function."""

    def test_returns_dict(self):
        """Test returns a dictionary."""
        result = validate_storage_configs()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        """Test has expected provider keys."""
        result = validate_storage_configs()
        expected_keys = ["dropbox", "nextcloud", "sftp", "s3", "ftp", "webdav", "google_drive", "onedrive"]
        for key in expected_keys:
            assert key in result

    def test_values_are_lists(self):
        """Test that values are lists of issues."""
        result = validate_storage_configs()
        for key, issues in result.items():
            assert isinstance(issues, list)


@pytest.mark.unit
class TestValidateEmailConfig:
    """Tests for validate_email_config function."""

    def test_returns_list(self):
        """Test returns a list."""
        result = validate_email_config()
        assert isinstance(result, list)


@pytest.mark.unit
class TestValidateNotificationConfig:
    """Tests for validate_notification_config function."""

    def test_returns_list(self):
        """Test returns a list."""
        result = validate_notification_config()
        assert isinstance(result, list)


@pytest.mark.unit
class TestCheckAllConfigs:
    """Tests for check_all_configs function."""

    def test_returns_dict(self):
        """Test returns a dictionary."""
        result = check_all_configs()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        """Test has expected keys."""
        result = check_all_configs()
        assert "storage" in result
        assert "email" in result
        assert "notification" in result
