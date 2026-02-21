"""
Unit tests for configuration and security validation.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.unit
class TestConfigurationValidation:
    """Tests for configuration validation."""

    def test_session_secret_required_with_auth(self):
        """Test that SESSION_SECRET is required when auth is enabled."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                database_url="sqlite:///test.db",
                redis_url="redis://localhost:6379",
                openai_api_key="test",
                azure_ai_key="test",
                azure_region="test",
                azure_endpoint="https://test.example.com",
                gotenberg_url="http://localhost:3000",
                workdir="/tmp",
                auth_enabled=True,
                session_secret=None,
            )
        assert "SESSION_SECRET must be set" in str(exc_info.value)

    def test_session_secret_minimum_length(self):
        """Test that SESSION_SECRET must be at least 32 characters."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                database_url="sqlite:///test.db",
                redis_url="redis://localhost:6379",
                openai_api_key="test",
                azure_ai_key="test",
                azure_region="test",
                azure_endpoint="https://test.example.com",
                gotenberg_url="http://localhost:3000",
                workdir="/tmp",
                auth_enabled=True,
                session_secret="short",
            )
        assert "at least 32 characters" in str(exc_info.value)

    def test_valid_configuration(self):
        """Test that valid configuration is accepted."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test_key",
            azure_ai_key="test_key",
            azure_region="eastus",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=True,
            session_secret="a" * 32,  # 32 character secret
        )
        assert config.auth_enabled is True
        assert len(config.session_secret) == 32

    def test_auth_disabled_no_session_secret_required(self):
        """Test that SESSION_SECRET is not required when auth is disabled."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test_key",
            azure_ai_key="test_key",
            azure_region="eastus",
            azure_endpoint="https://test.cognitiveservices.azure.com/",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            session_secret=None,
        )
        assert config.auth_enabled is False
        assert config.session_secret is None


@pytest.mark.unit
class TestBuildMetadataConfiguration:
    """Tests for build metadata configuration."""

    def test_version_from_environment(self, monkeypatch):
        """Test that version is read from APP_VERSION environment variable."""
        monkeypatch.setenv("APP_VERSION", "1.2.3-test")
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.version == "1.2.3-test"

    def test_build_date_from_environment(self, monkeypatch):
        """Test that build_date is read from BUILD_DATE environment variable."""
        monkeypatch.setenv("BUILD_DATE", "2026-01-15")
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.build_date == "2026-01-15"

    def test_build_date_with_time_from_environment(self, monkeypatch):
        """Test that build_date supports ISO 8601 format with time."""
        monkeypatch.setenv("BUILD_DATE", "2026-01-15T10:30:00Z")
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.build_date == "2026-01-15T10:30:00Z"

    def test_git_sha_from_environment(self, monkeypatch):
        """Test that git_sha is read from GIT_COMMIT_SHA environment variable."""
        monkeypatch.setenv("GIT_COMMIT_SHA", "abc1234")
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        assert config.git_sha == "abc1234"

    def test_git_sha_default(self, monkeypatch, tmp_path):
        """Test that git_sha defaults to 'unknown' when not set."""
        # Mock the file system to ensure no GIT_SHA file exists
        import app.config

        monkeypatch.setattr(app.config.os.path, "dirname", lambda x: str(tmp_path))

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        # When no file or env var exists, should return "unknown"
        assert config.git_sha == "unknown"

    def test_version_default_when_no_file_or_env(self, monkeypatch, tmp_path):
        """Test that version defaults to 'unknown' when no VERSION file or env var exists."""
        import app.config

        monkeypatch.setattr(app.config.os.path, "dirname", lambda x: str(tmp_path))

        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        # When no file or env var exists, should return "unknown"
        assert config.version == "unknown"

    def test_runtime_info_property(self):
        """Test that runtime_info returns build information."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )
        runtime_info = config.runtime_info
        # Should contain version, build_date, and git_sha in some form
        assert "Version:" in runtime_info or config.version in runtime_info


@pytest.mark.unit
class TestNotificationConfiguration:
    """Tests for notification configuration parsing."""

    def test_notification_urls_from_string(self):
        """Test parsing notification URLs from comma-separated string."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            notification_urls="discord://webhook1,telegram://webhook2",
        )
        assert len(config.notification_urls) == 2
        assert "discord://webhook1" in config.notification_urls
        assert "telegram://webhook2" in config.notification_urls

    def test_notification_urls_from_list(self):
        """Test that notification URLs can be provided as a list."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
            notification_urls=["discord://webhook1", "telegram://webhook2"],
        )
        assert len(config.notification_urls) == 2


@pytest.mark.unit
@pytest.mark.security
class TestSecurityConfiguration:
    """Tests for security-related configuration."""

    def test_no_default_credentials_in_config(self):
        """Test that no default credentials are present in configuration."""
        # This test ensures we don't accidentally have hardcoded credentials
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )

        # Ensure optional credentials are actually optional (None)
        assert config.dropbox_app_key is None
        assert config.dropbox_app_secret is None
        assert config.nextcloud_password is None
        assert config.paperless_ngx_api_token is None

    def test_optional_services_dont_require_credentials(self):
        """Test that application can start without optional service credentials."""
        config = Settings(
            database_url="sqlite:///test.db",
            redis_url="redis://localhost:6379",
            openai_api_key="test",
            azure_ai_key="test",
            azure_region="test",
            azure_endpoint="https://test.example.com",
            gotenberg_url="http://localhost:3000",
            workdir="/tmp",
            auth_enabled=False,
        )

        # Should not raise an error
        assert config.database_url == "sqlite:///test.db"


# ---------------------------------------------------------------------------
# Helpers shared across quote-stripping tests
# ---------------------------------------------------------------------------

_BASE_KWARGS = dict(
    auth_enabled=False,
    azure_ai_key="test",
    azure_region="eastus",
    azure_endpoint="https://test.example.com",
    gotenberg_url="http://localhost:3000",
    workdir="/tmp",
    openai_api_key="sk-test",
    redis_url="redis://localhost:6379",
)


@pytest.mark.unit
class TestOuterQuoteStripping:
    """
    Tests that Settings strips surrounding quotes from string env var values.

    In Kubernetes env vars can arrive with literal quote characters included
    (e.g. DATABASE_URL="postgresql://..." with the quotes as part of the value).
    Docker Compose strips these automatically; Kubernetes does not.
    """

    def test_double_quotes_stripped_from_url(self):
        """Double-quoted URL value has quotes removed."""
        config = Settings(
            database_url='"sqlite:///test.db"',
            **_BASE_KWARGS,
        )
        assert config.database_url == "sqlite:///test.db"

    def test_single_quotes_stripped_from_url(self):
        """Single-quoted URL value has quotes removed."""
        config = Settings(
            database_url="'sqlite:///test.db'",
            **_BASE_KWARGS,
        )
        assert config.database_url == "sqlite:///test.db"

    def test_double_quotes_stripped_from_optional_field(self):
        """Quotes are stripped from optional string fields too."""
        config = Settings(
            database_url="sqlite:///test.db",
            dropbox_app_key='"my-app-key"',
            **_BASE_KWARGS,
        )
        assert config.dropbox_app_key == "my-app-key"

    def test_unquoted_value_unchanged(self):
        """Values without surrounding quotes are left as-is."""
        config = Settings(
            database_url="sqlite:///test.db",
            **_BASE_KWARGS,
        )
        assert config.database_url == "sqlite:///test.db"

    def test_mismatched_quotes_not_stripped(self):
        """Mismatched quotes (open with one type, close with another) are NOT stripped."""
        raw = "\"sqlite:///test.db'"
        config = Settings(
            database_url=raw,
            **_BASE_KWARGS,
        )
        assert config.database_url == raw

    def test_single_quote_char_not_stripped(self):
        """A single-character string that is just one quote is NOT modified."""
        # A value of exactly one character cannot have matching outer quotes
        config = Settings(
            database_url="sqlite:///test.db",
            openai_model='"',
            **_BASE_KWARGS,
        )
        assert config.openai_model == '"'

    def test_multiple_fields_stripped_simultaneously(self):
        """Multiple quoted fields in the same config are all stripped."""
        config = Settings(
            database_url='"sqlite:///test.db"',
            redis_url='"redis://localhost:6379"',
            workdir='"/data/workdir"',
            **{k: v for k, v in _BASE_KWARGS.items() if k not in ("redis_url", "workdir")},
        )
        assert config.database_url == "sqlite:///test.db"
        assert config.redis_url == "redis://localhost:6379"
        assert config.workdir == "/data/workdir"
