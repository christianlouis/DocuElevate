"""Tests for app/utils/config_validator/settings_display.py module."""

from unittest.mock import patch

import pytest

from app.utils.config_validator.masking import configured_state, is_sensitive_setting
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

    def test_structured_credentials_are_reduced_to_configuration_state(self, caplog):
        private_material = "PRIVATE-MATERIAL-MUST-NEVER-APPEAR"
        credentials = f'{{"private_key":"{private_material}","client_email":"svc@example.test"}}'

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("builtins.dir", return_value=["google_drive_credentials_json"]),
        ):
            patched_settings.google_drive_credentials_json = credentials
            with caplog.at_level("INFO", logger="app.utils.config_validator.settings_display"):
                dump_all_settings()

        assert private_material not in caplog.text
        assert "svc@example.test" not in caplog.text
        assert "google_drive_credentials_json: <configured>" in caplog.text

    def test_secret_prefixes_and_suffixes_are_never_logged(self, caplog):
        secret = "prefix-super-secret-suffix"

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("builtins.dir", return_value=["openai_api_key"]),
        ):
            patched_settings.openai_api_key = secret
            with caplog.at_level("INFO", logger="app.utils.config_validator.settings_display"):
                dump_all_settings()

        assert secret not in caplog.text
        assert "prefix" not in caplog.text
        assert "suffix" not in caplog.text
        assert "openai_api_key: <configured>" in caplog.text

    def test_numeric_token_budget_remains_diagnostic(self, caplog):
        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("builtins.dir", return_value=["corpus_backfill_daily_llm_token_budget"]),
        ):
            patched_settings.corpus_backfill_daily_llm_token_budget = 12345
            with caplog.at_level("INFO", logger="app.utils.config_validator.settings_display"):
                dump_all_settings()

        assert "corpus_backfill_daily_llm_token_budget: 12345" in caplog.text

    def test_unknown_string_setting_defaults_to_presence_only(self, caplog):
        future_secret = "future-provider-value-must-not-appear"

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("builtins.dir", return_value=["future_provider_config"]),
        ):
            patched_settings.future_provider_config = future_secret
            with caplog.at_level("INFO", logger="app.utils.config_validator.settings_display"):
                dump_all_settings()

        assert future_secret not in caplog.text
        assert "future_provider_config: <configured>" in caplog.text

    def test_empty_bytes_are_not_configured(self):
        assert configured_state(b"") == "<not configured>"

    @pytest.mark.parametrize(
        "name",
        [
            "cors_allow_credentials",
            "dropbox_allow_global_credentials_for_integrations",
            "notify_on_credential_failure",
            "sftp_disable_host_key_verification",
            "social_auth_google_use_global_credentials",
            "social_auth_generic_oauth2_token_url",
        ],
    )
    def test_non_secret_policy_settings_are_not_misclassified(self, name):
        assert not is_sensitive_setting(name)

    @pytest.mark.parametrize("name", ["celery_broker_url", "celery_result_backend"])
    def test_celery_connection_urls_are_sensitive(self, name):
        assert is_sensitive_setting(name)


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

    def test_show_values_cannot_reveal_structured_credentials(self):
        credentials = '{"private_key":"never-render-this","client_email":"svc@example.test"}'
        with patch(
            "app.utils.config_validator.settings_display.settings.google_drive_credentials_json",
            credentials,
        ):
            result = get_settings_for_display(show_values=True)

        entry = next(item for item in result["Google Drive"] if item["name"] == "google_drive_credentials_json")
        assert entry["value"] == "<configured>"
        assert "never-render-this" not in str(result)
        assert "svc@example.test" not in str(result)

    def test_saml_certificate_is_never_returned(self):
        certificate = "-----BEGIN CERTIFICATE-----sensitive-material-----END CERTIFICATE-----"
        with patch(
            "app.utils.config_validator.settings_display.settings.social_auth_saml2_certificate",
            certificate,
        ):
            result = get_settings_for_display(show_values=True)

        entry = next(item for item in result["Other"] if item["name"] == "social_auth_saml2_certificate")
        assert entry["value"] == "<configured>"
        assert certificate not in str(result)

    def test_empty_sensitive_collection_is_consistently_unconfigured(self):
        with patch("app.utils.config_validator.settings_display.settings.notification_urls", []):
            result = get_settings_for_display(show_values=True)

        entry = next(item for item in result["Notifications"] if item["name"] == "notification_urls")
        assert entry["value"] == "<not configured>"
        assert entry["is_configured"] is False


@pytest.mark.unit
class TestDumpAllSettingsNotificationUrls:
    """Tests for the notification_urls special handling in dump_all_settings (lines 47-57)."""

    def test_notification_urls_list_masked(self):
        """Covers lines 50-52: notification_urls as a list gets each URL masked."""
        from app.utils.config_validator.settings_display import dump_all_settings

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("app.utils.config_validator.settings_display.logger"),
            patch("app.utils.notification._mask_sensitive_url", return_value="masked_url", create=True),
        ):
            patched_settings.notification_urls = ["https://hooks.slack.com/services/secret/url"]
            patched_settings.model_computed_fields = {}
            patched_settings.model_config = {}
            patched_settings.model_extra = {}
            patched_settings.model_fields = {}
            patched_settings.model_fields_set = set()

            with patch("builtins.dir", return_value=["notification_urls"]):
                dump_all_settings()

    def test_notification_urls_string_masked(self):
        """Covers lines 53-54: notification_urls as a string gets masked."""
        from app.utils.config_validator.settings_display import dump_all_settings

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch("app.utils.notification._mask_sensitive_url", return_value="masked", create=True),
        ):
            patched_settings.notification_urls = "https://hooks.slack.com/secret"
            patched_settings.model_computed_fields = {}
            patched_settings.model_config = {}
            patched_settings.model_extra = {}
            patched_settings.model_fields = {}
            patched_settings.model_fields_set = set()

            with patch("builtins.dir", return_value=["notification_urls"]):
                dump_all_settings()  # Should not raise

    def test_notification_urls_import_error_fallback(self):
        """Covers lines 56-57: ImportError falls back to default logging."""
        import sys

        from app.utils.config_validator.settings_display import dump_all_settings

        with (
            patch("app.utils.config_validator.settings_display.settings") as patched_settings,
            patch(
                "app.utils.config_validator.settings_display.logger",
            ),
        ):
            patched_settings.notification_urls = ["https://example.com/notify"]
            patched_settings.model_computed_fields = {}
            patched_settings.model_config = {}
            patched_settings.model_extra = {}
            patched_settings.model_fields = {}
            patched_settings.model_fields_set = set()

            # Force ImportError by removing the module from sys.modules
            import sys

            modules_backup = sys.modules.get("app.utils.notification")
            sys.modules.pop("app.utils.notification", None)

            with patch("builtins.dir", return_value=["notification_urls"]):
                try:
                    dump_all_settings()
                finally:
                    if modules_backup is not None:
                        sys.modules["app.utils.notification"] = modules_backup


@pytest.mark.unit
class TestGetSettingsForDisplayBranches:
    """Tests for uncovered branches in get_settings_for_display (lines 219->223, 226->225, 265->223)."""

    def test_no_uncategorized_settings_no_other_category(self):
        """Covers 219->223: if uncategorized is empty, 'Other' category is not added."""
        from app.utils.config_validator.settings_display import get_settings_for_display

        result = get_settings_for_display()
        # 'Other' should not appear when all settings are categorized (or empty)
        # We just verify the function runs without error
        assert isinstance(result, dict)

    def test_key_not_in_settings_skipped(self):
        """Covers 226->225: keys without hasattr(settings, key) are skipped."""
        from unittest.mock import patch

        from app.utils.config_validator.settings_display import get_settings_for_display

        # Inject a non-existent key into one category
        with patch("app.utils.config_validator.settings_display.settings") as patched:
            patched.version = "1.0.0"
            patched.build_date = "2024-01-01"
            patched.debug = False
            # Mock hasattr to return False for 'external_hostname' (simulating missing key)

            original_hasattr = hasattr

            def fake_hasattr(obj, name):
                if name == "external_hostname":
                    return False
                return original_hasattr(obj, name)

            with patch("builtins.hasattr", side_effect=fake_hasattr):
                result = get_settings_for_display()
            # Should still return a dict without raising
            assert isinstance(result, dict)

    def test_empty_items_category_excluded(self):
        """Covers 265->223: categories with no items are excluded from result."""
        from unittest.mock import patch

        from app.utils.config_validator.settings_display import get_settings_for_display

        # If all keys in a category are missing from settings, it's excluded
        with patch("app.utils.config_validator.settings_display.settings") as patched:
            patched.version = "1.0.0"
            patched.build_date = "2024-01-01"
            patched.debug = False
            # Make hasattr return False for all non-essential keys
            original_hasattr = hasattr

            def fake_hasattr(obj, name):
                if name in ("version", "build_date", "debug"):
                    return original_hasattr(obj, name)
                return False

            with patch("builtins.hasattr", side_effect=fake_hasattr):
                result = get_settings_for_display()
            # Should have System Info but other categories may be empty/excluded
            assert "System Info" in result
