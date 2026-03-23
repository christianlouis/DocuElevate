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

    def test_sensitive_flags_correct(self):
        """Test that sensitive flag is set correctly for each setting."""
        settings_map = {s["key"]: s for s in get_required_settings()}
        # Sensitive settings
        assert settings_map["session_secret"]["sensitive"] is True
        assert settings_map["admin_password"]["sensitive"] is True
        assert settings_map["openai_api_key"]["sensitive"] is True
        # Non-sensitive settings
        assert settings_map["database_url"]["sensitive"] is False
        assert settings_map["redis_url"]["sensitive"] is False
        assert settings_map["workdir"]["sensitive"] is False
        assert settings_map["admin_username"]["sensitive"] is False

    def test_wizard_step_assignments(self):
        """Test that settings are assigned to the correct wizard steps."""
        settings_map = {s["key"]: s for s in get_required_settings()}
        # Step 1: Core infrastructure
        assert settings_map["database_url"]["wizard_step"] == 1
        assert settings_map["redis_url"]["wizard_step"] == 1
        assert settings_map["workdir"]["wizard_step"] == 1
        assert settings_map["gotenberg_url"]["wizard_step"] == 1
        # Step 2: Security
        assert settings_map["session_secret"]["wizard_step"] == 2
        assert settings_map["admin_username"]["wizard_step"] == 2
        assert settings_map["admin_password"]["wizard_step"] == 2
        # Step 3: AI Services
        assert settings_map["ai_provider"]["wizard_step"] == 3
        assert settings_map["openai_api_key"]["wizard_step"] == 3
        assert settings_map["openai_model"]["wizard_step"] == 3

    def test_wizard_categories_correct(self):
        """Test that wizard categories are set correctly."""
        settings_map = {s["key"]: s for s in get_required_settings()}
        assert settings_map["database_url"]["wizard_category"] == "Core Infrastructure"
        assert settings_map["session_secret"]["wizard_category"] == "Security"
        assert settings_map["ai_provider"]["wizard_category"] == "AI Services"

    def test_ai_provider_has_options(self):
        """Test that ai_provider setting has a list of options."""
        settings_map = {s["key"]: s for s in get_required_settings()}
        ai_provider = settings_map["ai_provider"]
        assert "options" in ai_provider
        assert isinstance(ai_provider["options"], list)
        assert len(ai_provider["options"]) > 0
        assert "openai" in ai_provider["options"]

    def test_settings_have_string_type(self):
        """Test that all settings have the 'string' type."""
        for setting in get_required_settings():
            assert setting["type"] == "string", f"Expected string type for {setting['key']}"

    def test_total_settings_count(self):
        """Test that the expected number of required settings is returned."""
        # Ensures no accidental additions or removals
        result = get_required_settings()
        assert len(result) == 10


@pytest.mark.unit
class TestIsSetupRequired:
    """Tests for is_setup_required function."""

    def test_returns_boolean(self):
        """Test that is_setup_required returns a boolean."""
        result = is_setup_required()
        assert isinstance(result, bool)

    def test_setup_required_when_admin_password_is_none(self):
        """Test that setup is required when admin_password is None (test environment default)."""
        # In the test environment, admin_password defaults to None which is a placeholder value
        result = is_setup_required()
        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_setup_not_required_with_real_values(self, mock_settings):
        """Test that setup is not required when both critical settings have real values.

        is_setup_required() only checks session_secret and admin_password, so only
        these two attributes need to be configured on the mock.
        """
        mock_settings.session_secret = "a_very_long_real_session_secret_that_is_definitely_not_placeholder"
        mock_settings.admin_password = "my_real_secure_password_123"
        result = is_setup_required()
        assert result is False

    @patch("app.utils.setup_wizard.settings")
    def test_setup_required_with_insecure_session_secret(self, mock_settings):
        """Test that setup is required when session_secret is the insecure default."""
        mock_settings.session_secret = "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"
        mock_settings.admin_password = "real_password_123"
        result = is_setup_required()
        assert result is True

    @pytest.mark.parametrize(
        "placeholder",
        [None, "", "your_secure_password", "changeme", "admin"],
    )
    @patch("app.utils.setup_wizard.settings")
    def test_setup_required_for_each_admin_password_placeholder(self, mock_settings, placeholder):
        """Test that setup is required for each admin_password placeholder value."""
        mock_settings.session_secret = "a_very_long_real_session_secret_that_is_definitely_not_placeholder"
        mock_settings.admin_password = placeholder
        result = is_setup_required()
        assert result is True

    @patch("app.utils.setup_wizard.settings")
    def test_handles_exception_gracefully(self, mock_settings):
        """Test that exceptions are handled gracefully and return False (fail open)."""

        def raise_error():
            raise RuntimeError("boom")

        type(mock_settings).session_secret = property(lambda s: raise_error())
        # This should not raise - it returns False on error (fail open)
        result = is_setup_required()
        assert result is False


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

    @patch("app.utils.setup_wizard.settings")
    def test_returns_empty_when_all_configured(self, mock_settings):
        """Test that returns empty list when all settings are properly configured."""
        mock_settings.database_url = "sqlite:///./real.db"
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "a_very_long_real_session_secret_minimum_32_chars"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = "real_secure_password_456"
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "sk-real-key-12345"
        mock_settings.openai_model = "gpt-4o-mini"
        result = get_missing_required_settings()
        assert result == []

    @patch("app.utils.setup_wizard.settings")
    def test_detects_none_value_as_missing(self, mock_settings):
        """Test that a None value is detected as missing."""
        mock_settings.database_url = None
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "a_very_long_real_session_secret_minimum_32_chars"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = "real_secure_password_456"
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "sk-real-key-12345"
        mock_settings.openai_model = "gpt-4o-mini"
        missing = get_missing_required_settings()
        assert "database_url" in missing

    @patch("app.utils.setup_wizard.settings")
    def test_detects_empty_string_as_missing(self, mock_settings):
        """Test that an empty string value is detected as missing."""
        mock_settings.database_url = "sqlite:///./real.db"
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "a_very_long_real_session_secret_minimum_32_chars"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = ""
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "sk-real-key-12345"
        mock_settings.openai_model = "gpt-4o-mini"
        missing = get_missing_required_settings()
        assert "admin_password" in missing

    @patch("app.utils.setup_wizard.settings")
    def test_detects_insecure_default_as_missing(self, mock_settings):
        """Test that the insecure default session_secret is detected as missing."""
        mock_settings.database_url = "sqlite:///./real.db"
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "INSECURE_DEFAULT_FOR_DEVELOPMENT_ONLY_DO_NOT_USE_IN_PRODUCTION_MINIMUM_32_CHARS"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = "real_secure_password_456"
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "sk-real-key-12345"
        mock_settings.openai_model = "gpt-4o-mini"
        missing = get_missing_required_settings()
        assert "session_secret" in missing

    @patch("app.utils.setup_wizard.settings")
    def test_detects_placeholder_bracket_format_as_missing(self, mock_settings):
        """Test that <KEY_NAME> formatted placeholders are detected as missing."""
        mock_settings.database_url = "sqlite:///./real.db"
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "a_very_long_real_session_secret_minimum_32_chars"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = "real_secure_password_456"
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "<OPENAI_API_KEY>"
        mock_settings.openai_model = "gpt-4o-mini"
        missing = get_missing_required_settings()
        assert "openai_api_key" in missing

    @patch("app.utils.setup_wizard.settings")
    def test_detects_test_key_placeholder_as_missing(self, mock_settings):
        """Test that 'test-key' is detected as a missing placeholder."""
        mock_settings.database_url = "sqlite:///./real.db"
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_settings.workdir = "/data/workdir"
        mock_settings.gotenberg_url = "http://gotenberg:3000"
        mock_settings.session_secret = "a_very_long_real_session_secret_minimum_32_chars"
        mock_settings.admin_username = "admin"
        mock_settings.admin_password = "real_secure_password_456"
        mock_settings.ai_provider = "openai"
        mock_settings.openai_api_key = "test-key"
        mock_settings.openai_model = "gpt-4o-mini"
        missing = get_missing_required_settings()
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

    def test_has_three_steps(self):
        """Test that there are exactly three wizard steps."""
        steps = get_wizard_steps()
        assert len(steps) == 3
        assert set(steps.keys()) == {1, 2, 3}

    def test_step_1_contains_infrastructure_settings(self):
        """Test that step 1 contains the core infrastructure settings."""
        steps = get_wizard_steps()
        step_1_keys = [s["key"] for s in steps[1]]
        assert "database_url" in step_1_keys
        assert "redis_url" in step_1_keys
        assert "workdir" in step_1_keys
        assert "gotenberg_url" in step_1_keys

    def test_step_2_contains_security_settings(self):
        """Test that step 2 contains the security settings."""
        steps = get_wizard_steps()
        step_2_keys = [s["key"] for s in steps[2]]
        assert "session_secret" in step_2_keys
        assert "admin_username" in step_2_keys
        assert "admin_password" in step_2_keys

    def test_step_3_contains_ai_settings(self):
        """Test that step 3 contains the AI service settings."""
        steps = get_wizard_steps()
        step_3_keys = [s["key"] for s in steps[3]]
        assert "ai_provider" in step_3_keys
        assert "openai_api_key" in step_3_keys
        assert "openai_model" in step_3_keys

    def test_settings_not_duplicated_across_steps(self):
        """Test that no setting appears in more than one step."""
        steps = get_wizard_steps()
        all_keys = []
        for settings_list in steps.values():
            all_keys.extend([s["key"] for s in settings_list])
        assert len(all_keys) == len(set(all_keys)), "Some settings appear in multiple steps"
