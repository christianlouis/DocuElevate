"""
Tests for simple re-export modules (app/frontend.py, app/utils/config_validator.py)

These modules are simple re-exports of functions from other modules.
We test that imports work correctly, including the app.utils package.
"""

import pytest


@pytest.mark.unit
class TestUtilsReexports:
    """Test that app.utils package exports work correctly"""

    def test_hash_file_import(self):
        """Test that hash_file can be imported from app.utils"""
        from app.utils import hash_file

        # Function should exist and be callable
        assert callable(hash_file)

    def test_log_task_progress_import(self):
        """Test that log_task_progress can be imported from app.utils"""
        from app.utils import log_task_progress

        # Function should exist and be callable
        assert callable(log_task_progress)

    def test_utils_package_exports(self):
        """Test that utils package exports expected functions"""
        # The utils package should export functions via __init__.py
        import app.utils

        # Package should exist and have expected attributes
        assert hasattr(app.utils, "hash_file")
        assert hasattr(app.utils, "log_task_progress")


@pytest.mark.unit
class TestFrontendReexports:
    """Test that app/frontend.py re-exports work correctly"""

    def test_router_import(self):
        """Test that router can be imported from app.frontend"""
        from app.frontend import router

        # Router should exist
        assert router is not None

    def test_frontend_module_imports(self):
        """Test that frontend module can be imported"""
        import app.frontend

        # Module should exist and have router
        assert hasattr(app.frontend, "router")


@pytest.mark.unit
class TestConfigValidatorReexports:
    """Test that app/utils/config_validator.py re-exports work correctly"""

    def test_validate_email_config_import(self):
        """Test validate_email_config import"""
        from app.utils.config_validator import validate_email_config

        assert callable(validate_email_config)

    def test_validate_storage_configs_import(self):
        """Test validate_storage_configs import"""
        from app.utils.config_validator import validate_storage_configs

        assert callable(validate_storage_configs)

    def test_validate_notification_config_import(self):
        """Test validate_notification_config import"""
        from app.utils.config_validator import validate_notification_config

        assert callable(validate_notification_config)

    def test_mask_sensitive_value_import(self):
        """Test mask_sensitive_value import"""
        from app.utils.config_validator import mask_sensitive_value

        assert callable(mask_sensitive_value)

    def test_get_provider_status_import(self):
        """Test get_provider_status import"""
        from app.utils.config_validator import get_provider_status

        assert callable(get_provider_status)

    def test_get_settings_for_display_import(self):
        """Test get_settings_for_display import"""
        from app.utils.config_validator import get_settings_for_display

        assert callable(get_settings_for_display)

    def test_dump_all_settings_import(self):
        """Test dump_all_settings import"""
        from app.utils.config_validator import dump_all_settings

        assert callable(dump_all_settings)

    def test_check_all_configs_import(self):
        """Test check_all_configs import"""
        from app.utils.config_validator import check_all_configs

        assert callable(check_all_configs)

    def test_config_validator_all_exports(self):
        """Test that __all__ contains expected exports"""
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

        # Check that __all__ is defined and contains expected items
        if hasattr(config_validator, "__all__"):
            for export in expected_exports:
                assert export in config_validator.__all__

        # Also check direct imports work
        for export in expected_exports:
            assert hasattr(config_validator, export)
