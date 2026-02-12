"""Tests for app/utils/config_loader.py module."""

import pytest

from app.utils.config_loader import convert_setting_value


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
