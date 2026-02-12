"""Tests for app/utils/setup_wizard.py module."""

from unittest.mock import patch

import pytest

from app.utils.setup_wizard import (
    get_missing_required_settings,
    get_required_settings,
    get_wizard_steps,
    is_setup_required,
)


@pytest.mark.unit
class TestGetRequiredSettings:
    """Tests for get_required_settings function."""

    def test_returns_list(self):
        """Test that it returns a list."""
        result = get_required_settings()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_setting_has_required_keys(self):
        """Test that each setting has the expected keys."""
        required_keys = {"key", "label", "description", "type", "sensitive", "wizard_step", "wizard_category"}
        for setting in get_required_settings():
            assert required_keys.issubset(set(setting.keys())), f"Missing keys in {setting.get('key', 'unknown')}"

    def test_includes_critical_settings(self):
        """Test that critical settings are included."""
        keys = [s["key"] for s in get_required_settings()]
        assert "database_url" in keys
        assert "redis_url" in keys
        assert "session_secret" in keys
        assert "openai_api_key" in keys


@pytest.mark.unit
class TestIsSetupRequired:
    """Tests for is_setup_required function."""

    def test_returns_boolean(self):
        """Test that is_setup_required returns a boolean."""
        result = is_setup_required()
        assert isinstance(result, bool)

    def test_setup_required_with_test_key(self):
        """Test that setup is required when using test-key placeholder."""
        # In test environment, openai_api_key is "test-key" which is a placeholder
        result = is_setup_required()
        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_setup_not_required_with_real_values(self, mock_settings):
        """Test that setup is not required with real values."""
        mock_settings.session_secret = "a_very_long_real_session_secret_that_is_definitely_not_placeholder"
        mock_settings.admin_password = "my_real_secure_password_123"
        mock_settings.openai_api_key = "sk-real-key-12345"
        mock_settings.azure_ai_key = "real-azure-key-12345"
        result = is_setup_required()
        assert result is False

    @patch("app.utils.setup_wizard.settings")
    def test_handles_exception_gracefully(self, mock_settings):
        """Test that exceptions are handled gracefully."""
        mock_settings.session_secret = property(lambda self: (_ for _ in ()).throw(Exception("test")))
        # getattr on a mock with side_effect
        type(mock_settings).session_secret = property(lambda s: (_ for _ in ()).throw(RuntimeError("boom")))
        # This should not raise - it returns False on error
        result = is_setup_required()
        # May return True or False depending on which setting fails, but shouldn't raise
        assert isinstance(result, bool)


@pytest.mark.unit
class TestGetMissingRequiredSettings:
    """Tests for get_missing_required_settings function."""

    def test_returns_list(self):
        """Test that it returns a list."""
        result = get_missing_required_settings()
        assert isinstance(result, list)

    def test_includes_placeholder_settings(self):
        """Test that settings with placeholder values are included."""
        missing = get_missing_required_settings()
        # In test environment, openai_api_key is "test-key" which is a placeholder
        assert "openai_api_key" in missing


@pytest.mark.unit
class TestGetWizardSteps:
    """Tests for get_wizard_steps function."""

    def test_returns_dict(self):
        """Test that it returns a dictionary."""
        result = get_wizard_steps()
        assert isinstance(result, dict)

    def test_steps_are_numbered(self):
        """Test that steps are numbered starting from 1."""
        steps = get_wizard_steps()
        assert 1 in steps

    def test_each_step_has_settings(self):
        """Test that each step has a list of settings."""
        steps = get_wizard_steps()
        for step_num, settings_list in steps.items():
            assert isinstance(settings_list, list)
            assert len(settings_list) > 0

    def test_steps_cover_all_required_settings(self):
        """Test that all required settings are assigned to a step."""
        steps = get_wizard_steps()
        all_step_keys = []
        for settings_list in steps.values():
            all_step_keys.extend([s["key"] for s in settings_list])

        required_keys = [s["key"] for s in get_required_settings()]
        for key in required_keys:
            assert key in all_step_keys, f"Setting {key} not assigned to any wizard step"
