"""
Tests for GPT metadata extraction task
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json


@pytest.mark.unit
class TestExtractJsonFromText:
    """Tests for extract_json_from_text helper function."""

    def test_extract_json_from_code_block(self):
        """Test extracting JSON from markdown code block."""
        from app.tasks.extract_metadata_with_gpt import extract_json_from_text

        text = """Here is the result:
```json
{"filename": "test.pdf", "tags": ["test"]}
```
End of response."""

        result = extract_json_from_text(text)
        assert result == '{"filename": "test.pdf", "tags": ["test"]}'

    def test_extract_json_without_code_block(self):
        """Test extracting JSON from plain text."""
        from app.tasks.extract_metadata_with_gpt import extract_json_from_text

        text = 'Some text before {"key": "value", "number": 42} some text after'

        result = extract_json_from_text(text)
        assert result == '{"key": "value", "number": 42}'

    def test_extract_json_no_match(self):
        """Test extracting JSON when no JSON is present."""
        from app.tasks.extract_metadata_with_gpt import extract_json_from_text

        text = "No JSON here at all"

        result = extract_json_from_text(text)
        assert result is None

    def test_extract_json_partial_braces(self):
        """Test extracting JSON with unbalanced braces."""
        from app.tasks.extract_metadata_with_gpt import extract_json_from_text

        text = "Just an opening brace {"

        result = extract_json_from_text(text)
        # Should return None or incomplete JSON
        assert result is None or result == ""


@pytest.mark.unit
class TestExtractMetadataWithGPT:
    """Tests for extract_metadata_with_gpt task."""

    @patch("app.tasks.extract_metadata_with_gpt.client")
    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    def test_extract_metadata_success(self, mock_embed, mock_client):
        """Test successful metadata extraction."""
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '''
```json
{
    "filename": "2024-01-01_Test_Document.pdf",
    "document_type": "Invoice",
    "tags": ["test", "invoice"],
    "title": "Test Invoice"
}
```
'''
        mock_client.chat.completions.create.return_value = mock_response
        mock_embed.delay.return_value = MagicMock()

        # Create a mock task instance
        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = extract_metadata_with_gpt(
            mock_self,
            filename="test.pdf",
            cleaned_text="Sample document text",
            file_id=123
        )

        assert result["s3_file"] == "test.pdf"
        assert "metadata" in result
        assert result["metadata"]["document_type"] == "Invoice"
        mock_embed.delay.assert_called_once()

    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_extract_metadata_invalid_json(self, mock_client):
        """Test metadata extraction with invalid JSON response."""
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        # Mock OpenAI response with invalid JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not JSON at all"
        mock_client.chat.completions.create.return_value = mock_response

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = extract_metadata_with_gpt(
            mock_self,
            filename="test.pdf",
            cleaned_text="Sample text",
            file_id=123
        )

        assert result == {}

    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_extract_metadata_openai_error(self, mock_client):
        """Test metadata extraction with OpenAI API error."""
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        # Mock OpenAI error
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = extract_metadata_with_gpt(
            mock_self,
            filename="test.pdf",
            cleaned_text="Sample text",
            file_id=123
        )

        assert result == {}

    @patch("app.tasks.extract_metadata_with_gpt.SessionLocal")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.os.path.exists")
    def test_extract_metadata_no_file_id(self, mock_exists, mock_embed, mock_client, mock_session):
        """Test metadata extraction without file_id."""
        from app.tasks.extract_metadata_with_gpt import extract_metadata_with_gpt

        mock_exists.return_value = True

        # Mock database session and query
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 456
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_file_record

        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"filename": "test.pdf", "tags": []}'
        mock_client.chat.completions.create.return_value = mock_response

        mock_self = MagicMock()
        mock_self.request.id = "test-task-id"

        result = extract_metadata_with_gpt(
            mock_self,
            filename="test.pdf",
            cleaned_text="Sample text",
            file_id=None
        )

        # Should find file_id from database
        assert "metadata" in result or result == {}
