"""Comprehensive unit tests for app/tasks/extract_metadata_with_gpt.py module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.extract_metadata_with_gpt import extract_json_from_text, extract_metadata_with_gpt


@pytest.mark.unit
class TestExtractJsonFromText:
    """Tests for extract_json_from_text function."""

    def test_extracts_json_from_backticks_with_json_tag(self):
        """Test extraction of JSON from triple-backtick block with json tag."""
        text = '```json\n{"key": "value", "num": 123}\n```'
        result = extract_json_from_text(text)
        assert result == '{"key": "value", "num": 123}'

    def test_extracts_json_from_backticks_no_lang(self):
        """Test extraction from backticks without language tag."""
        text = '```\n{"key": "value"}\n```'
        result = extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_extracts_json_from_raw_text(self):
        """Test extraction from raw text with JSON."""
        text = 'Here is the result: {"key": "value", "nested": {"a": 1}} end.'
        result = extract_json_from_text(text)
        assert result == '{"key": "value", "nested": {"a": 1}}'

    def test_returns_none_for_no_json(self):
        """Test returns None when no JSON found."""
        text = "No JSON here at all, just plain text."
        result = extract_json_from_text(text)
        assert result is None

    def test_returns_none_for_incomplete_json(self):
        """Test returns None for incomplete JSON structures."""
        text = "Only opening brace: { but no closing"
        result = extract_json_from_text(text)
        assert result is None

    def test_extracts_complex_nested_json(self):
        """Test extraction of complex nested JSON."""
        text = '{"filename": "2024-01-01_Invoice", "tags": ["test", "invoice"], "metadata": {"amount": 100, "currency": "USD"}}'
        result = extract_json_from_text(text)
        parsed = json.loads(result)
        assert parsed["filename"] == "2024-01-01_Invoice"
        assert "tags" in parsed
        assert "metadata" in parsed
        assert parsed["metadata"]["amount"] == 100

    def test_extracts_first_json_when_multiple_present(self):
        """Test that extraction finds the outermost JSON object."""
        text = 'First: {"a": 1} and second: {"b": 2}'
        result = extract_json_from_text(text)
        # Should extract from first { to last }
        assert result is not None
        assert "{" in result and "}" in result


@pytest.mark.unit
class TestExtractMetadataWithGpt:
    """Tests for extract_metadata_with_gpt Celery task."""

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_successful_metadata_extraction(self, mock_client, mock_log_progress, mock_embed_task):
        """Test successful metadata extraction with valid GPT response."""
        # Mock the OpenAI client response
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps({
            "filename": "2024-01-15_Invoice_Amazon",
            "empfaenger": "John Doe",
            "absender": "Amazon",
            "correspondent": "Amazon",
            "kommunikationsart": "Rechnung",
            "kommunikationskategorie": "Finanz_und_Vertragsdokumente",
            "document_type": "Invoice",
            "tags": ["invoice", "amazon", "online-shopping"],
            "language": "de",
            "title": "Amazon Purchase Invoice",
            "confidence_score": 95,
            "reference_number": "INV-2024-001",
            "monetary_amounts": ["99.99 EUR"]
        })
        mock_client.chat.completions.create.return_value = mock_completion

        # Set task request context directly on the Celery task
        extract_metadata_with_gpt.request.id = "test-task-id"

        # Call the underlying function directly (not through Celery)
        result = extract_metadata_with_gpt.__wrapped__("test_invoice.pdf", "Invoice from Amazon for 99.99 EUR", 123)

        # Verify OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0
        assert len(call_args[1]["messages"]) == 2

        # Verify metadata was extracted correctly
        assert result["s3_file"] == "test_invoice.pdf"
        assert "metadata" in result
        assert result["metadata"]["document_type"] == "Invoice"
        assert result["metadata"]["correspondent"] == "Amazon"

        # Verify embed task was queued
        mock_embed_task.delay.assert_called_once()

        # Verify task progress was logged
        assert mock_log_progress.call_count >= 3

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_handles_json_in_backticks(self, mock_client, mock_log_progress, mock_embed_task):
        """Test extraction handles JSON wrapped in markdown code blocks."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = '```json\n{"filename": "test.pdf", "document_type": "Unknown"}\n```'
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 456)

        assert result["metadata"]["filename"] == "test.pdf"
        assert result["metadata"]["document_type"] == "Unknown"
        mock_embed_task.delay.assert_called_once()

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_handles_invalid_json_response(self, mock_client, mock_log_progress, mock_embed_task):
        """Test handling of invalid JSON in GPT response."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = "This is not valid JSON at all"
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 789)

        assert result == {}
        mock_embed_task.delay.assert_not_called()
        # Verify failure was logged
        failure_calls = [call for call in mock_log_progress.call_args_list if "failure" in str(call)]
        assert len(failure_calls) > 0

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_handles_openai_api_exception(self, mock_client, mock_log_progress, mock_embed_task):
        """Test handling of OpenAI API exceptions."""
        mock_client.chat.completions.create.side_effect = Exception("API Error: Rate limit exceeded")

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 101)

        assert result == {}
        mock_embed_task.delay.assert_not_called()
        # Verify exception was logged
        failure_calls = [call for call in mock_log_progress.call_args_list if "failure" in str(call)]
        assert len(failure_calls) > 0

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    @patch("app.tasks.extract_metadata_with_gpt.SessionLocal")
    def test_retrieves_file_id_from_database_when_not_provided(
        self, mock_session_local, mock_client, mock_log_progress, mock_embed_task
    ):
        """Test file_id retrieval from database when not provided."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = '{"filename": "test.pdf", "document_type": "Unknown"}'
        mock_client.chat.completions.create.return_value = mock_completion

        # Mock database session
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_file_record = MagicMock()
        mock_file_record.id = 999
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_file_record

        # Mock file existence
        with patch("app.tasks.extract_metadata_with_gpt.os.path.exists", return_value=True):
            with patch("app.tasks.extract_metadata_with_gpt.settings.workdir", "/tmp"):
                extract_metadata_with_gpt.request.id = "test-task-id"

                result = extract_metadata_with_gpt.__wrapped__(
                    filename="test.pdf",
                    cleaned_text="Sample text",
                    file_id=None  # Not provided
                )

                assert result["metadata"]["filename"] == "test.pdf"
                # Verify database was queried
                mock_db.query.assert_called_once()

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_validates_filename_security(self, mock_client, mock_log_progress, mock_embed_task):
        """Test filename validation to prevent path traversal."""
        mock_completion = MagicMock()
        # Try to inject a malicious filename
        mock_completion.choices[0].message.content = json.dumps({
            "filename": "../../../etc/passwd",
            "document_type": "Invoice"
        })
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 202)

        # Filename should be sanitized (empty or safe)
        assert result["metadata"]["filename"] == ""
        mock_embed_task.delay.assert_called_once()

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_validates_filename_with_dots(self, mock_client, mock_log_progress, mock_embed_task):
        """Test filename validation rejects '..' in filenames."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps({
            "filename": "test..invoice.pdf",
            "document_type": "Invoice"
        })
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 303)

        # Filename with .. should be rejected
        assert result["metadata"]["filename"] == ""

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_accepts_valid_filename(self, mock_client, mock_log_progress, mock_embed_task):
        """Test that valid filenames are accepted."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = json.dumps({
            "filename": "2024-01-15_Invoice_Amazon.pdf",
            "document_type": "Invoice"
        })
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 404)

        # Valid filename should be preserved
        assert result["metadata"]["filename"] == "2024-01-15_Invoice_Amazon.pdf"

    @patch("app.tasks.extract_metadata_with_gpt.embed_metadata_into_pdf")
    @patch("app.tasks.extract_metadata_with_gpt.log_task_progress")
    @patch("app.tasks.extract_metadata_with_gpt.client")
    def test_handles_malformed_json_with_valid_structure(self, mock_client, mock_log_progress, mock_embed_task):
        """Test handling of JSON that's parseable but missing expected fields."""
        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = '{"unexpected_field": "value"}'
        mock_client.chat.completions.create.return_value = mock_completion

        extract_metadata_with_gpt.request.id = "test-task-id"

        result = extract_metadata_with_gpt.__wrapped__("test.pdf", "Sample text", 505)

        # Should still extract the JSON even if fields are unexpected
        assert "metadata" in result
        assert result["metadata"]["unexpected_field"] == "value"
