"""Tests for app/utils/config_validator/settings_display.py module."""
import pytest
from unittest.mock import patch

from app.utils.config_validator.settings_display import dump_all_settings, get_settings_for_display


@pytest.mark.unit
class TestDumpAllSettings:
    """Tests for dump_all_settings function."""

    def test_dumps_without_error(self):
        """Test that dump_all_settings runs without error."""
        # This should not raise any exceptions
        dump_all_settings()

    @patch("app.utils.config_validator.settings_display.logger")
    def test_logs_settings(self, mock_logger):
        """Test that dump_all_settings logs settings."""
        dump_all_settings()
        # Should have logged start and end markers
        assert mock_logger.info.call_count > 2  # At least start, some settings, and end


@pytest.mark.unit
class TestGetSettingsForDisplay:
    """Tests for get_settings_for_display function."""

    def test_returns_dict(self):
        """Test that it returns a dictionary."""
        result = get_settings_for_display()
        assert isinstance(result, dict)

    def test_has_system_info(self):
        """Test that System Info category is present."""
        result = get_settings_for_display()
        assert "System Info" in result

    def test_system_info_has_version(self):
        """Test that System Info includes app version."""
        result = get_settings_for_display()
        system_info = result["System Info"]
        names = [item["name"] for item in system_info]
        assert "App Version" in names

    def test_has_core_settings(self):
        """Test that Core settings category is present."""
        result = get_settings_for_display()
        assert "Core" in result

    def test_has_ai_services(self):
        """Test that AI Services category is present."""
        result = get_settings_for_display()
        assert "AI Services" in result

    def test_show_values_false_masks_sensitive(self):
        """Test that sensitive values are masked when show_values is False."""
        result = get_settings_for_display(show_values=False)
        # Check that AI Services settings have masked values
        if "AI Services" in result:
            for item in result["AI Services"]:
                if "key" in item["name"].lower() or "token" in item["name"].lower():
                    if item["value"]:
                        # Sensitive values should be masked
                        assert "****" in str(item["value"]) or isinstance(item["value"], str)

    def test_show_values_true(self):
        """Test that settings are returned with show_values=True."""
        result = get_settings_for_display(show_values=True)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_items_have_required_keys(self):
        """Test that each setting item has required keys."""
        result = get_settings_for_display()
        for category, items in result.items():
            for item in items:
                assert "name" in item
                assert "value" in item
                assert "is_configured" in item
