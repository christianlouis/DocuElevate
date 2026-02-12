"""
Tests for app/utils/config_validator.py module coverage.

Ensures all imports and __all__ exports in the re-export module are exercised
so coverage tools track the module as covered.
"""

import pytest


@pytest.mark.unit
class TestConfigValidatorModuleCoverage:
    """Ensure every line in config_validator.py is exercised by coverage."""

    def test_all_imports_and_exports_exercised(self):
        """Import every symbol from config_validator to ensure line coverage."""
        # These imports exercise lines 7-17 (import statements)
        from app.utils.config_validator import (
            check_all_configs,
            dump_all_settings,
            get_provider_status,
            get_settings_for_display,
            mask_sensitive_value,
            validate_email_config,
            validate_notification_config,
            validate_storage_configs,
        )

        # Verify all functions are callable (exercises the __all__ list, lines 19-28)
        for fn in [
            validate_email_config,
            validate_storage_configs,
            validate_notification_config,
            mask_sensitive_value,
            get_provider_status,
            get_settings_for_display,
            dump_all_settings,
            check_all_configs,
        ]:
            assert callable(fn)

    def test_all_list_contents(self):
        """Verify __all__ is correctly defined and complete."""
        import app.utils.config_validator as mod

        expected = {
            "validate_email_config",
            "validate_storage_configs",
            "validate_notification_config",
            "validate_auth_config",
            "mask_sensitive_value",
            "get_provider_status",
            "get_settings_for_display",
            "dump_all_settings",
            "check_all_configs",
        }
        assert set(mod.__all__) == expected

    def test_mask_sensitive_value_returns_masked(self):
        """Test that mask_sensitive_value masks a real value."""
        from app.utils.config_validator import mask_sensitive_value

        result = mask_sensitive_value("my_secret_value_12345")
        assert "my_secret_value_12345" != result

    def test_validate_storage_configs_returns_dict(self):
        """Test validate_storage_configs returns a dict."""
        from app.utils.config_validator import validate_storage_configs

        result = validate_storage_configs()
        assert isinstance(result, dict)

    def test_validate_email_config_returns_list(self):
        """Test validate_email_config returns a list."""
        from app.utils.config_validator import validate_email_config

        result = validate_email_config()
        assert isinstance(result, list)

    def test_validate_notification_config_returns_list(self):
        """Test validate_notification_config returns a list."""
        from app.utils.config_validator import validate_notification_config

        result = validate_notification_config()
        assert isinstance(result, list)

    def test_get_provider_status_returns_dict(self):
        """Test get_provider_status returns a dict."""
        from app.utils.config_validator import get_provider_status

        result = get_provider_status()
        assert isinstance(result, dict)

    def test_check_all_configs_returns_dict(self):
        """Test check_all_configs returns a dict."""
        from app.utils.config_validator import check_all_configs

        result = check_all_configs()
        assert isinstance(result, dict)
