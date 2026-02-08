"""
Tests for setup wizard utilities
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestSetupWizardUtilities:
    """Tests for setup wizard utility functions."""

    def test_get_required_settings(self):
        """Test getting list of required settings."""
        from app.utils.setup_wizard import get_required_settings

        settings = get_required_settings()

        assert len(settings) > 0
        assert all("key" in s for s in settings)
        assert all("label" in s for s in settings)
        assert all("wizard_step" in s for s in settings)

    def test_get_required_settings_has_critical_keys(self):
        """Test that required settings include critical keys."""
        from app.utils.setup_wizard import get_required_settings

        settings = get_required_settings()
        keys = [s["key"] for s in settings]

        assert "database_url" in keys
        assert "workdir" in keys
        assert "session_secret" in keys
        assert "admin_password" in keys

    @patch("app.utils.setup_wizard.settings")
    def test_is_setup_required_missing_password(self, mock_settings):
        """Test setup required when admin password is missing."""
        from app.utils.setup_wizard import is_setup_required

        mock_settings.session_secret = "valid_secret_key_at_least_32_chars"
        mock_settings.admin_password = None
        mock_settings.openai_api_key = "sk-valid"
        mock_settings.azure_ai_key = "valid-key"

        result = is_setup_required()

        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_is_setup_required_placeholder_values(self, mock_settings):
        """Test setup required when using placeholder values."""
        from app.utils.setup_wizard import is_setup_required

        mock_settings.session_secret = "valid_secret"
        mock_settings.admin_password = "valid_password"
        mock_settings.openai_api_key = "test-key"  # Placeholder
        mock_settings.azure_ai_key = "valid-key"

        result = is_setup_required()

        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_is_setup_required_all_configured(self, mock_settings):
        """Test setup not required when all settings are configured."""
        from app.utils.setup_wizard import is_setup_required

        mock_settings.session_secret = "valid_secret_key_at_least_32_characters"
        mock_settings.admin_password = "strong_password"
        mock_settings.openai_api_key = "sk-real_key_here"
        mock_settings.azure_ai_key = "real-azure-key"

        result = is_setup_required()

        assert result is False

    @patch("app.utils.setup_wizard.settings")
    def test_is_setup_required_insecure_session_secret(self, mock_settings):
        """Test setup required with insecure session secret."""
        from app.utils.setup_wizard import is_setup_required

        mock_settings.session_secret = "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"
        mock_settings.admin_password = "valid"
        mock_settings.openai_api_key = "valid"
        mock_settings.azure_ai_key = "valid"

        result = is_setup_required()

        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_get_missing_required_settings(self, mock_settings):
        """Test getting list of missing settings."""
        from app.utils.setup_wizard import get_missing_required_settings

        # Mock all settings as None
        for attr in ["database_url", "redis_url", "workdir", "session_secret", "admin_password"]:
            setattr(mock_settings, attr, None)

        missing = get_missing_required_settings()

        assert len(missing) > 0
        assert "session_secret" in missing
        assert "admin_password" in missing

    def test_get_wizard_steps(self):
        """Test getting wizard steps organized by step number."""
        from app.utils.setup_wizard import get_wizard_steps

        steps = get_wizard_steps()

        assert isinstance(steps, dict)
        assert len(steps) > 0
        assert 1 in steps  # Step 1 should exist
        assert all(isinstance(step_settings, list) for step_settings in steps.values())

    def test_get_wizard_steps_organization(self):
        """Test that wizard steps are properly organized."""
        from app.utils.setup_wizard import get_wizard_steps

        steps = get_wizard_steps()

        # Check that each step has settings
        for step_num, settings in steps.items():
            assert len(settings) > 0
            # All settings in a step should have the same step number
            assert all(s.get("wizard_step") == step_num for s in settings)

    @patch("app.utils.setup_wizard.settings", side_effect=Exception("Settings error"))
    def test_is_setup_required_handles_error(self, mock_settings):
        """Test that is_setup_required handles errors gracefully."""
        from app.utils.setup_wizard import is_setup_required

        # Should return False (fail open) on error
        result = is_setup_required()

        assert result is False
