"""Tests for app/tasks/extract_metadata_with_gpt.py module."""
import pytest

from app.tasks.extract_metadata_with_gpt import extract_json_from_text


@pytest.mark.unit
class TestExtractJsonFromText:
    """Tests for extract_json_from_text function."""

    def test_extracts_json_from_backticks(self):
        """Test extraction of JSON from triple-backtick block."""
        text = '```json\n{"key": "value"}\n```'
        result = extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_extracts_json_from_backticks_no_lang(self):
        """Test extraction from backticks without language tag."""
        text = '```\n{"key": "value"}\n```'
        result = extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_extracts_json_from_raw_text(self):
        """Test extraction from raw text with JSON."""
        text = 'Here is the result: {"key": "value"} end.'
        result = extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_returns_none_for_no_json(self):
        """Test returns None when no JSON found."""
        text = "No JSON here at all."
        result = extract_json_from_text(text)
        assert result is None

    def test_extracts_complex_json(self):
        """Test extraction of complex JSON."""
        text = '{"filename": "2024-01-01_Invoice", "tags": ["test", "invoice"], "amount": 100}'
        result = extract_json_from_text(text)
        assert '"filename"' in result
        assert '"tags"' in result
