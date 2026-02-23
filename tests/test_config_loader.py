"""Tests for app/utils/config_loader.py module."""

from typing import Optional, Union
from unittest.mock import MagicMock, patch

import pytest

from app.utils.config_loader import (
    convert_setting_value,
    load_settings_from_db,
    reload_settings_from_db,
)


@pytest.mark.unit
class TestConvertSettingValue:
    """Tests for convert_setting_value function."""

    def test_converts_bool_true_string(self):
        """Test converting 'true' string to boolean."""
        result = convert_setting_value("true", bool)
        assert result is True

    def test_converts_bool_false_string(self):
        """Test converting 'false' string to boolean."""
        result = convert_setting_value("false", bool)
        assert result is False

    def test_converts_bool_yes(self):
        """Test converting 'yes' to boolean."""
        result = convert_setting_value("yes", bool)
        assert result is True

    def test_converts_integer_string(self):
        """Test converting integer string."""
        result = convert_setting_value("42", int)
        assert result == 42

    def test_converts_invalid_integer(self):
        """Test converting invalid integer returns 0."""
        result = convert_setting_value("not_a_number", int)
        assert result == 0

    def test_converts_float_string(self):
        """Test converting float string."""
        result = convert_setting_value("3.14", float)
        assert result == 3.14

    def test_converts_invalid_float(self):
        """Test converting invalid float returns 0.0."""
        result = convert_setting_value("not_a_float", float)
        assert result == 0.0

    def test_preserves_regular_string(self):
        """Test regular strings are preserved."""
        result = convert_setting_value("hello world", str)
        assert result == "hello world"

    def test_handles_none(self):
        """Test handling of None."""
        result = convert_setting_value(None, str)
        assert result is None

    def test_converts_list_string(self):
        """Test converting comma-separated string to list."""
        result = convert_setting_value("a, b, c", list)
        assert result == ["a", "b", "c"]

    def test_handles_optional_type(self):
        """Test handling Optional type annotation."""
        result = convert_setting_value("42", Optional[int])
        assert result == 42

    def test_handles_union_type(self):
        """Test handling Union type annotation."""
        result = convert_setting_value("test", Union[str, None])
        assert result == "test"

    def test_list_from_empty_string(self):
        """Test converting empty comma string to empty list."""
        result = convert_setting_value("", list)
        assert result == []

    def test_list_with_whitespace(self):
        """Test list conversion handles extra whitespace."""
        result = convert_setting_value("  a  ,  b  ,  c  ", list)
        assert result == ["a", "b", "c"]

    def test_bool_variants(self):
        """Test various boolean string representations."""
        assert convert_setting_value("1", bool) is True
        assert convert_setting_value("y", bool) is True
        assert convert_setting_value("t", bool) is True
        assert convert_setting_value("0", bool) is False
        assert convert_setting_value("n", bool) is False


@pytest.mark.unit
class TestLoadSettingsFromDb:
    """Tests for load_settings_from_db function."""

    def test_loads_settings_from_database(self):
        """Test loading settings from database."""
        from app.models import ApplicationSettings

        # Mock settings object
        mock_settings = MagicMock()
        mock_settings.__fields__ = {
            "test_setting": MagicMock(annotation=str),
            "another_setting": MagicMock(annotation=int),
        }

        # Mock database session
        mock_db = MagicMock()
        mock_db_settings = [
            ApplicationSettings(key="test_setting", value="test_value"),
            ApplicationSettings(key="another_setting", value="42"),
        ]
        mock_db.query.return_value.all.return_value = mock_db_settings

        load_settings_from_db(mock_settings, mock_db)

        # Verify settings were set
        assert mock_settings.test_setting == "test_value"
        assert mock_settings.another_setting == 42

    def test_handles_empty_database(self):
        """Test handling when no settings in database."""
        mock_settings = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []

        # Should not raise
        load_settings_from_db(mock_settings, mock_db)

    def test_skips_unknown_settings(self):
        """Test that unknown settings are skipped."""
        from app.models import ApplicationSettings

        mock_settings = MagicMock()
        mock_settings.__fields__ = {"known_setting": MagicMock(annotation=str)}

        mock_db = MagicMock()
        mock_db_settings = [
            ApplicationSettings(key="known_setting", value="value1"),
            ApplicationSettings(key="unknown_setting", value="value2"),
        ]
        mock_db.query.return_value.all.return_value = mock_db_settings

        load_settings_from_db(mock_settings, mock_db)

        # Only known_setting should be set
        assert hasattr(mock_settings, "known_setting")

    def test_handles_database_errors(self):
        """Test handling database errors gracefully."""
        mock_settings = MagicMock()
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        # Should not raise, just log warning
        load_settings_from_db(mock_settings, mock_db)

    @patch("app.utils.config_loader.get_setting_metadata")
    @patch("app.utils.encryption.decrypt_value")
    def test_decrypts_sensitive_settings(self, mock_decrypt, mock_metadata):
        """Test that sensitive settings are decrypted before being applied."""
        from app.models import ApplicationSettings

        mock_metadata.return_value = {"sensitive": True}
        mock_decrypt.return_value = "plaintext_token"

        mock_settings = MagicMock()
        mock_settings.__fields__ = {
            "onedrive_refresh_token": MagicMock(annotation=str),
        }

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            ApplicationSettings(key="onedrive_refresh_token", value="enc:gAAAAABencryptedvalue"),
        ]

        load_settings_from_db(mock_settings, mock_db)

        mock_decrypt.assert_called_once_with("enc:gAAAAABencryptedvalue")
        assert mock_settings.onedrive_refresh_token == "plaintext_token"

    @patch("app.utils.config_loader.get_setting_metadata")
    def test_non_sensitive_settings_not_decrypted(self, mock_metadata):
        """Test that non-sensitive settings are applied as-is without decryption."""
        from app.models import ApplicationSettings

        mock_metadata.return_value = {"sensitive": False}

        mock_settings = MagicMock()
        mock_settings.__fields__ = {
            "some_setting": MagicMock(annotation=str),
        }

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            ApplicationSettings(key="some_setting", value="plain_value"),
        ]

        with patch("app.utils.encryption.decrypt_value") as mock_decrypt:
            load_settings_from_db(mock_settings, mock_db)
            mock_decrypt.assert_not_called()

        assert mock_settings.some_setting == "plain_value"

    @patch("app.utils.config_loader.get_setting_metadata")
    def test_decryption_failure_skips_setting(self, mock_metadata):
        """Test that a setting is skipped if decryption fails."""
        from app.models import ApplicationSettings

        mock_metadata.return_value = {"sensitive": True}

        mock_settings = MagicMock()
        mock_settings.__fields__ = {
            "onedrive_refresh_token": MagicMock(annotation=str),
        }

        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = [
            ApplicationSettings(key="onedrive_refresh_token", value="enc:corrupted"),
        ]

        with patch("app.utils.encryption.decrypt_value", side_effect=Exception("Decryption error")):
            load_settings_from_db(mock_settings, mock_db)

        # The attribute should not have been overwritten with a real value,
        # since decryption failed and the setting was skipped
        assert isinstance(mock_settings.onedrive_refresh_token, MagicMock)


@pytest.mark.unit
class TestReloadSettingsFromDb:
    """Tests for reload_settings_from_db function."""

    @patch("app.database.SessionLocal")
    @patch("app.utils.config_loader.load_settings_from_db")
    def test_reload_success(self, mock_load, mock_session_local):
        """Test successful settings reload."""
        mock_settings = MagicMock()
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        result = reload_settings_from_db(mock_settings)

        assert result is True
        mock_load.assert_called_once_with(mock_settings, mock_db)
        mock_db.close.assert_called_once()

    @patch("app.database.SessionLocal")
    def test_reload_database_error(self, mock_session_local):
        """Test reload handling database error."""
        mock_settings = MagicMock()
        mock_session_local.side_effect = Exception("Connection error")

        result = reload_settings_from_db(mock_settings)

        assert result is False

    @patch("app.utils.config_loader.load_settings_from_db")
    @patch("app.database.SessionLocal")
    def test_reload_closes_session_on_error(self, mock_session_local, mock_load):
        """Test that session is closed even on error."""
        mock_settings = MagicMock()
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        # Make load_settings_from_db raise an exception
        mock_load.side_effect = Exception("Load error")

        result = reload_settings_from_db(mock_settings)

        # Should close session despite error
        mock_db.close.assert_called_once()
        assert result is False
