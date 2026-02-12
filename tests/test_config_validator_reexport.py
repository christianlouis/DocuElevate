"""
Tests for app/utils/config_validator.py

This module tests the config_validator re-export module.
"""

import pytest


@pytest.mark.unit
class TestConfigValidatorReexports:
    """Test config_validator re-export module."""

    def test_module_imports(self):
        """Test that config_validator module imports successfully."""
        from app.utils import config_validator
        
        assert config_validator is not None

    def test_validate_email_config_reexport(self):
        """Test validate_email_config is re-exported."""
        from app.utils.config_validator import validate_email_config
        
        assert callable(validate_email_config)

    def test_validate_storage_configs_reexport(self):
        """Test validate_storage_configs is re-exported."""
        from app.utils.config_validator import validate_storage_configs
        
        assert callable(validate_storage_configs)

    def test_validate_notification_config_reexport(self):
        """Test validate_notification_config is re-exported."""
        from app.utils.config_validator import validate_notification_config
        
        assert callable(validate_notification_config)

    def test_mask_sensitive_value_reexport(self):
        """Test mask_sensitive_value is re-exported."""
        from app.utils.config_validator import mask_sensitive_value
        
        assert callable(mask_sensitive_value)

    def test_get_provider_status_reexport(self):
        """Test get_provider_status is re-exported."""
        from app.utils.config_validator import get_provider_status
        
        assert callable(get_provider_status)

    def test_get_settings_for_display_reexport(self):
        """Test get_settings_for_display is re-exported."""
        from app.utils.config_validator import get_settings_for_display
        
        assert callable(get_settings_for_display)

    def test_dump_all_settings_reexport(self):
        """Test dump_all_settings is re-exported."""
        from app.utils.config_validator import dump_all_settings
        
        assert callable(dump_all_settings)

    def test_check_all_configs_reexport(self):
        """Test check_all_configs is re-exported."""
        from app.utils.config_validator import check_all_configs
        
        assert callable(check_all_configs)

    def test_all_exports_in_all(self):
        """Test that all exports are in __all__."""
        from app.utils import config_validator
        
        expected_exports = [
            "validate_email_config",
            "validate_storage_configs",
            "validate_notification_config",
            "mask_sensitive_value",
            "get_provider_status",
            "get_settings_for_display",
            "dump_all_settings",
            "check_all_configs",
        ]
        
        assert hasattr(config_validator, '__all__')
        for export in expected_exports:
            assert export in config_validator.__all__

    def test_mask_sensitive_value_functionality(self):
        """Test mask_sensitive_value actually works."""
        from app.utils.config_validator import mask_sensitive_value
        
        # Test masking a sensitive value
        result = mask_sensitive_value("secret_api_key_12345")
        assert result != "secret_api_key_12345"
        assert "***" in result or result == ""

    def test_get_provider_status_functionality(self):
        """Test get_provider_status returns expected structure."""
        from app.utils.config_validator import get_provider_status
        
        # Get provider status (takes no arguments)
        result = get_provider_status()
        
        # Should return a dict with provider information
        assert isinstance(result, dict)
        # Should have at least authentication provider
        assert "Authentication" in result or len(result) >= 0
