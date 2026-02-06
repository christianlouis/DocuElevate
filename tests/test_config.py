"""
Unit tests for configuration and security validation.
"""
import pytest
import os
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
                session_secret=None
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
                session_secret="short"
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
            session_secret="a" * 32  # 32 character secret
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
            session_secret=None
        )
        assert config.auth_enabled is False
        assert config.session_secret is None


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
            notification_urls="discord://webhook1,telegram://webhook2"
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
            notification_urls=["discord://webhook1", "telegram://webhook2"]
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
            auth_enabled=False
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
            auth_enabled=False
        )
        
        # Should not raise an error
        assert config.database_url == "sqlite:///test.db"
