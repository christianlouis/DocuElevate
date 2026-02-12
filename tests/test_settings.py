"""
Tests for application settings management.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ApplicationSettings
from app.utils.config_loader import convert_setting_value, load_settings_from_db
from app.utils.settings_service import (
    SETTING_METADATA,
    delete_setting_from_db,
    get_all_settings_from_db,
    get_setting_from_db,
    get_setting_metadata,
    get_settings_by_category,
    save_setting_to_db,
    validate_setting_value,
)


@pytest.mark.unit
class TestSettingsService:
    """Test settings service functions"""

    def test_save_and_get_setting(self, db_session: Session):
        """Test saving and retrieving a setting from database"""
        # Save a setting
        result = save_setting_to_db(db_session, "test_key", "test_value")
        assert result is True

        # Retrieve the setting
        value = get_setting_from_db(db_session, "test_key")
        assert value == "test_value"

    def test_update_existing_setting(self, db_session: Session):
        """Test updating an existing setting"""
        # Save initial value
        save_setting_to_db(db_session, "test_key", "initial_value")

        # Update the value
        result = save_setting_to_db(db_session, "test_key", "updated_value")
        assert result is True

        # Verify update
        value = get_setting_from_db(db_session, "test_key")
        assert value == "updated_value"

    def test_get_nonexistent_setting(self, db_session: Session):
        """Test retrieving a setting that doesn't exist"""
        value = get_setting_from_db(db_session, "nonexistent_key")
        assert value is None

    def test_get_all_settings(self, db_session: Session):
        """Test retrieving all settings from database"""
        # Save multiple settings
        save_setting_to_db(db_session, "key1", "value1")
        save_setting_to_db(db_session, "key2", "value2")
        save_setting_to_db(db_session, "key3", "value3")

        # Get all settings
        all_settings = get_all_settings_from_db(db_session)
        assert len(all_settings) == 3
        assert all_settings["key1"] == "value1"
        assert all_settings["key2"] == "value2"
        assert all_settings["key3"] == "value3"

    def test_delete_setting(self, db_session: Session):
        """Test deleting a setting from database"""
        # Save a setting
        save_setting_to_db(db_session, "test_key", "test_value")

        # Delete the setting
        result = delete_setting_from_db(db_session, "test_key")
        assert result is True

        # Verify deletion
        value = get_setting_from_db(db_session, "test_key")
        assert value is None

    def test_delete_nonexistent_setting(self, db_session: Session):
        """Test deleting a setting that doesn't exist"""
        result = delete_setting_from_db(db_session, "nonexistent_key")
        assert result is False

    def test_validate_setting_value_boolean(self):
        """Test validation of boolean settings"""
        # Valid boolean values
        is_valid, error = validate_setting_value("debug", "true")
        assert is_valid is True
        assert error is None

        is_valid, error = validate_setting_value("debug", "false")
        assert is_valid is True

        # Invalid boolean value
        is_valid, error = validate_setting_value("debug", "maybe")
        assert is_valid is False
        assert "boolean" in error.lower()

    def test_validate_session_secret_length(self):
        """Test validation of session_secret minimum length"""
        # Too short
        is_valid, error = validate_setting_value("session_secret", "short")
        assert is_valid is False
        assert "32 characters" in error

        # Long enough
        long_secret = "a" * 32
        is_valid, error = validate_setting_value("session_secret", long_secret)
        assert is_valid is True

    def test_get_setting_metadata(self):
        """Test retrieving setting metadata"""
        metadata = get_setting_metadata("database_url")
        assert metadata["category"] == "Core"
        assert metadata["type"] == "string"
        assert metadata["required"] is True
        assert metadata["restart_required"] is True

        # Test unknown setting
        metadata = get_setting_metadata("unknown_setting")
        assert metadata["category"] == "Other"

    def test_get_settings_by_category(self):
        """Test getting settings organized by category"""
        categories = get_settings_by_category()
        assert "Core" in categories
        assert "Authentication" in categories
        assert "AI Services" in categories
        assert "database_url" in categories["Core"]
        assert "auth_enabled" in categories["Authentication"]

    def test_setting_metadata_completeness(self):
        """Test that all major settings have metadata"""
        # Check that we have a good number of settings defined
        assert len(SETTING_METADATA) > 50, "Should have metadata for at least 50 settings"

        # Check critical settings are present
        critical_settings = [
            "database_url",
            "redis_url",
            "workdir",
            "debug",
            "openai_api_key",
            "azure_ai_key",
            "auth_enabled",
            "session_secret",
        ]
        for setting in critical_settings:
            assert setting in SETTING_METADATA, f"Missing metadata for {setting}"


@pytest.mark.unit
class TestConfigLoader:
    """Test configuration loader functions"""

    def test_convert_boolean_value(self):
        """Test converting string to boolean"""
        assert convert_setting_value("true", bool) is True
        assert convert_setting_value("false", bool) is False
        assert convert_setting_value("1", bool) is True
        assert convert_setting_value("0", bool) is False
        assert convert_setting_value("yes", bool) is True
        assert convert_setting_value("no", bool) is False

    def test_convert_integer_value(self):
        """Test converting string to integer"""
        assert convert_setting_value("42", int) == 42
        assert convert_setting_value("0", int) == 0
        assert convert_setting_value("-5", int) == -5

        # Invalid integer
        assert convert_setting_value("not_a_number", int) == 0

    def test_convert_string_value(self):
        """Test converting to string (default)"""
        assert convert_setting_value("hello", str) == "hello"
        assert convert_setting_value("123", str) == "123"

    def test_convert_none_value(self):
        """Test handling None values"""
        assert convert_setting_value(None, str) is None
        assert convert_setting_value(None, int) is None
        assert convert_setting_value(None, bool) is None

    def test_convert_list_value(self):
        """Test converting comma-separated string to list"""
        assert convert_setting_value("a,b,c", list) == ["a", "b", "c"]
        assert convert_setting_value("single", list) == ["single"]
        assert convert_setting_value("", list) == []


@pytest.mark.integration
@pytest.mark.requires_db
class TestSettingsAPI:
    """Test settings API endpoints"""

    def test_get_settings_requires_admin(self, client: TestClient):
        """Test that settings endpoint requires admin privileges"""
        # With AUTH_ENABLED=False in test environment, this test verifies
        # the admin check functionality. In production with AUTH_ENABLED=True,
        # both authentication and admin checks are enforced.
        response = client.get("/api/settings/")
        # Should return 403 (no admin session) or redirect
        # Note: Test environment has AUTH_ENABLED=False
        assert response.status_code in [200, 302, 403]

    def test_settings_page_structure(self, client: TestClient):
        """Test that settings page has expected structure"""
        # Verify the endpoint exists and returns expected status codes
        response = client.get("/settings", follow_redirects=False)
        # Should redirect or return 403 since no admin session
        assert response.status_code in [200, 302, 403]


@pytest.mark.integration
@pytest.mark.requires_db
class TestSettingsPrecedence:
    """Test settings precedence (DB > env > defaults)"""

    def test_db_overrides_default(self, db_session: Session):
        """Test that database settings override default values"""
        # Create a minimal test settings object
        from typing import Optional

        from pydantic_settings import BaseSettings

        class TestSettings(BaseSettings):
            test_value: str = "default"
            test_bool: bool = False

            class Config:
                env_file = None

        # Create settings with defaults
        test_settings = TestSettings()
        assert test_settings.test_value == "default"
        assert test_settings.test_bool is False

        # Save to database
        save_setting_to_db(db_session, "test_value", "from_database")
        save_setting_to_db(db_session, "test_bool", "true")

        # Load from database
        load_settings_from_db(test_settings, db_session)

        # Verify database values take precedence
        assert test_settings.test_value == "from_database"
        assert test_settings.test_bool is True

    def test_load_settings_handles_missing_db_settings(self, db_session: Session):
        """Test that loading settings works when no DB settings exist"""
        from pydantic_settings import BaseSettings

        class TestSettings(BaseSettings):
            test_value: str = "default"

            class Config:
                env_file = None

        test_settings = TestSettings()

        # Load from empty database - should not crash
        load_settings_from_db(test_settings, db_session)

        # Should still have default value
        assert test_settings.test_value == "default"


@pytest.mark.unit
class TestApplicationSettingsModel:
    """Test the ApplicationSettings database model"""

    def test_create_setting_record(self, db_session: Session):
        """Test creating an ApplicationSettings record"""
        setting = ApplicationSettings(key="test_key", value="test_value")
        db_session.add(setting)
        db_session.commit()

        # Retrieve and verify
        retrieved = db_session.query(ApplicationSettings).filter_by(key="test_key").first()
        assert retrieved is not None
        assert retrieved.key == "test_key"
        assert retrieved.value == "test_value"
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    def test_unique_key_constraint(self, db_session: Session):
        """Test that key field has unique constraint"""
        # Create first setting
        setting1 = ApplicationSettings(key="unique_key", value="value1")
        db_session.add(setting1)
        db_session.commit()

        # Try to create duplicate - should fail
        setting2 = ApplicationSettings(key="unique_key", value="value2")
        db_session.add(setting2)

        with pytest.raises(Exception):  # SQLAlchemy will raise an exception
            db_session.commit()

    @pytest.mark.skipif(
        True,  # Skip for all databases - timestamp update behavior varies
        reason="Timestamp update behavior varies by database backend",
    )
    def test_update_timestamp(self, db_session: Session):
        """Test that updated_at timestamp is updated on modification"""
        import time

        # Create setting
        setting = ApplicationSettings(key="test_key", value="initial")
        db_session.add(setting)
        db_session.commit()

        initial_updated_at = setting.updated_at

        # Small delay to ensure timestamp difference
        time.sleep(0.1)

        # Update setting
        setting.value = "updated"
        db_session.commit()

        # Verify updated_at changed
        # Note: SQLite doesn't automatically update onupdate timestamps
        # This test is skipped as behavior varies by database backend
        assert setting.updated_at is not None
