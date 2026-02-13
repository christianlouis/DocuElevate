"""
Tests for app/tasks/upload_to_paperless.py module.

Covers helper functions (normalize_metadata_value, _is_duplicate_error, poll_task_for_document_id,
get_custom_field_id, set_document_custom_fields) and the upload_to_paperless Celery task.
"""

import json
import os
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest
import requests

from app.tasks.upload_to_paperless import (
    _get_headers,
    _is_duplicate_error,
    _paperless_api_url,
    get_custom_field_id,
    normalize_metadata_value,
    poll_task_for_document_id,
    set_document_custom_fields,
    upload_to_paperless,
)


@pytest.mark.unit
class TestNormalizeMetadataValue:
    """Tests for normalize_metadata_value function."""

    def test_none_returns_empty(self):
        """Test that None value returns empty string."""
        assert normalize_metadata_value(None) == ""

    def test_empty_string_returns_empty(self):
        """Test that empty string returns empty string."""
        assert normalize_metadata_value("") == ""

    def test_unknown_placeholder_returns_empty(self):
        """Test that 'Unknown' placeholder returns empty string."""
        assert normalize_metadata_value("Unknown") == ""

    def test_normal_string_passes_through(self):
        """Test normal string values pass through."""
        assert normalize_metadata_value("John Doe") == "John Doe"

    def test_integer_converted_to_string(self):
        """Test integer values are converted to string."""
        assert normalize_metadata_value(42) == "42"

    def test_float_converted_to_string(self):
        """Test float values are converted to string."""
        assert normalize_metadata_value(3.14) == "3.14"

    def test_boolean_converted_to_string(self):
        """Test boolean values are converted to string."""
        assert normalize_metadata_value(True) == "True"


@pytest.mark.unit
class TestIsDuplicateError:
    """Tests for _is_duplicate_error function."""

    def test_empty_message(self):
        """Test that empty/None message returns False."""
        assert _is_duplicate_error("") is False
        assert _is_duplicate_error(None) is False

    def test_duplicate_message(self):
        """Test detection of duplicate document message."""
        assert _is_duplicate_error("Not consuming duplicate document") is True

    def test_duplicate_case_insensitive(self):
        """Test case insensitive duplicate detection."""
        assert _is_duplicate_error("DUPLICATE document not consuming") is True

    def test_non_duplicate_message(self):
        """Test that non-duplicate messages return False."""
        assert _is_duplicate_error("Processing completed") is False

    def test_partial_match_not_duplicate(self):
        """Test that message with only 'duplicate' but not 'not consuming' returns False."""
        assert _is_duplicate_error("Found a duplicate") is False


@pytest.mark.unit
class TestGetHeaders:
    """Tests for _get_headers function."""

    def test_returns_auth_header(self):
        """Test that headers include authorization token."""
        with patch("app.tasks.upload_to_paperless.settings") as mock_settings:
            mock_settings.paperless_ngx_api_token = "test-token"
            headers = _get_headers()
            assert headers["Authorization"] == "Token test-token"


@pytest.mark.unit
class TestPaperlessApiUrl:
    """Tests for _paperless_api_url function."""

    def test_constructs_url(self):
        """Test URL construction."""
        with patch("app.tasks.upload_to_paperless.settings") as mock_settings:
            mock_settings.paperless_host = "http://paperless:8000"
            url = _paperless_api_url("/api/documents/")
            assert url == "http://paperless:8000/api/documents/"

    def test_strips_trailing_slash_from_host(self):
        """Test trailing slash is removed from host."""
        with patch("app.tasks.upload_to_paperless.settings") as mock_settings:
            mock_settings.paperless_host = "http://paperless:8000/"
            url = _paperless_api_url("/api/documents/")
            assert url == "http://paperless:8000/api/documents/"

    def test_adds_leading_slash_to_path(self):
        """Test leading slash is added to path if missing."""
        with patch("app.tasks.upload_to_paperless.settings") as mock_settings:
            mock_settings.paperless_host = "http://paperless:8000"
            url = _paperless_api_url("api/documents/")
            assert url == "http://paperless:8000/api/documents/"


@pytest.mark.unit
class TestPollTaskForDocumentId:
    """Tests for poll_task_for_document_id function."""

    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_success_returns_document_id(self, mock_settings, mock_get, mock_sleep):
        """Test successful polling returns document ID."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = [{"status": "SUCCESS", "related_document": "42"}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = poll_task_for_document_id("test-task-id")
        assert result == 42

    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_success_with_paginated_response(self, mock_settings, mock_get, mock_sleep):
        """Test polling handles paginated API responses."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = {"results": [{"status": "SUCCESS", "related_document": "99"}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = poll_task_for_document_id("test-task-id")
        assert result == 99

    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_failure_raises_runtime_error(self, mock_settings, mock_get, mock_sleep):
        """Test that task failure raises RuntimeError."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = [{"status": "FAILURE", "result": "Processing error"}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="failed"):
            poll_task_for_document_id("test-task-id")

    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_duplicate_returns_none(self, mock_settings, mock_get, mock_sleep):
        """Test that duplicate document failure returns None."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = [{"status": "FAILURE", "result": "Not consuming duplicate document"}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = poll_task_for_document_id("test-task-id")
        assert result is None

    @patch("app.tasks.upload_to_paperless.POLL_MAX_ATTEMPTS", 2)
    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_timeout_raises_error(self, mock_settings, mock_get, mock_sleep):
        """Test that timeout raises TimeoutError."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        # Return empty results each time
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(TimeoutError):
            poll_task_for_document_id("test-task-id")

    @patch("app.tasks.upload_to_paperless.POLL_MAX_ATTEMPTS", 2)
    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_handles_request_exception(self, mock_settings, mock_get, mock_sleep):
        """Test that request exceptions are handled with retries."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(TimeoutError):
            poll_task_for_document_id("test-task-id")

    @patch("app.tasks.upload_to_paperless.time.sleep")
    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_success_without_document_id_raises(self, mock_settings, mock_get, mock_sleep):
        """Test success status without related_document raises RuntimeError."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = [{"status": "SUCCESS", "related_document": None}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="no doc ID found"):
            poll_task_for_document_id("test-task-id")


@pytest.mark.unit
class TestGetCustomFieldId:
    """Tests for get_custom_field_id function."""

    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_finds_field_by_name(self, mock_settings, mock_get):
        """Test finding a custom field by name."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = {"results": [{"name": "sender", "id": 5}, {"name": "date", "id": 6}]}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        assert get_custom_field_id("sender") == 5

    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_field_not_found_raises_value_error(self, mock_settings, mock_get):
        """Test that missing field raises ValueError."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="not found"):
            get_custom_field_id("nonexistent")

    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_handles_non_paginated_response(self, mock_settings, mock_get):
        """Test handling of non-paginated API response (list)."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_response = Mock()
        mock_response.json.return_value = [{"name": "sender", "id": 5}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        assert get_custom_field_id("sender") == 5

    @patch("app.tasks.upload_to_paperless.requests.get")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_request_exception_is_raised(self, mock_settings, mock_get):
        """Test that request exceptions are propagated."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        with pytest.raises(requests.exceptions.ConnectionError):
            get_custom_field_id("sender")


@pytest.mark.unit
class TestSetDocumentCustomFields:
    """Tests for set_document_custom_fields function."""

    @patch("app.tasks.upload_to_paperless.get_custom_field_id")
    @patch("app.tasks.upload_to_paperless.requests.patch")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_sets_custom_fields(self, mock_settings, mock_patch, mock_field_id):
        """Test setting custom fields on a document."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_field_id.return_value = 5
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_patch.return_value = mock_response

        set_document_custom_fields(42, {"sender": "John Doe"}, "task-123")

        mock_patch.assert_called_once()

    def test_empty_fields_returns_immediately(self):
        """Test that empty custom fields dict returns without API calls."""
        with patch("app.tasks.upload_to_paperless.requests.patch") as mock_patch:
            set_document_custom_fields(42, {}, "task-123")
            mock_patch.assert_not_called()

    @patch("app.tasks.upload_to_paperless.get_custom_field_id")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_skips_unknown_values(self, mock_settings, mock_field_id):
        """Test that 'Unknown' values are skipped."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        with patch("app.tasks.upload_to_paperless.requests.patch") as mock_patch:
            set_document_custom_fields(42, {"sender": "Unknown"}, "task-123")
            mock_patch.assert_not_called()

    @patch("app.tasks.upload_to_paperless.get_custom_field_id")
    @patch("app.tasks.upload_to_paperless.requests.patch")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_skips_field_not_found(self, mock_settings, mock_patch, mock_field_id):
        """Test that fields not found in Paperless are skipped."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_field_id.side_effect = ValueError("Custom field 'foo' not found")

        set_document_custom_fields(42, {"foo": "bar"}, "task-123")

        mock_patch.assert_not_called()

    @patch("app.tasks.upload_to_paperless.get_custom_field_id")
    @patch("app.tasks.upload_to_paperless.requests.patch")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_handles_patch_failure(self, mock_settings, mock_patch, mock_field_id):
        """Test that PATCH failure is logged but does not raise."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_field_id.return_value = 5

        mock_exc = requests.exceptions.HTTPError("500 Server Error")
        mock_exc.response = Mock()
        mock_exc.response.text = "Internal server error"
        mock_patch.side_effect = mock_exc

        # Should not raise
        set_document_custom_fields(42, {"sender": "John"}, "task-123")


@pytest.mark.unit
class TestUploadToPaperless:
    """Tests for upload_to_paperless Celery task."""

    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_file_not_found(self, mock_log):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            upload_to_paperless.__wrapped__("/nonexistent/file.pdf", file_id=1)

    @patch("app.tasks.upload_to_paperless.set_document_custom_fields")
    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_successful_upload(self, mock_log, mock_settings, mock_post, mock_poll, mock_set_fields, tmp_path):
        """Test successful upload to Paperless."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = None
        mock_settings.paperless_custom_field_absender = None

        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = 42

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        assert result["paperless_document_id"] == 42

    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_duplicate_document(self, mock_log, mock_settings, mock_post, mock_poll, tmp_path):
        """Test handling of duplicate document detection."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = None
        mock_settings.paperless_custom_field_absender = None

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = None  # Duplicate detected

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Duplicate"
        assert result["paperless_document_id"] is None

    @patch("app.tasks.upload_to_paperless.log_task_progress")
    @patch("app.tasks.upload_to_paperless.settings")
    def test_missing_config_raises_value_error(self, mock_settings, mock_log, tmp_path):
        """Test that missing Paperless config raises ValueError."""
        mock_settings.paperless_host = ""
        mock_settings.paperless_ngx_api_token = ""

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        with pytest.raises(ValueError, match="not fully configured"):
            upload_to_paperless.__wrapped__(str(test_file), file_id=1)

    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_upload_request_failure(self, mock_log, mock_settings, mock_post, tmp_path):
        """Test that failed HTTP request raises."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_exc = requests.exceptions.ConnectionError("Connection refused")
        mock_exc.response = None
        mock_post.side_effect = mock_exc

        with pytest.raises(requests.exceptions.ConnectionError):
            upload_to_paperless.__wrapped__(str(test_file), file_id=1)

    @patch("app.tasks.upload_to_paperless.set_document_custom_fields")
    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_loads_metadata_from_json(self, mock_log, mock_settings, mock_post, mock_poll, mock_set_fields, tmp_path):
        """Test that metadata is loaded from accompanying JSON file."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = json.dumps({"absender": "Sender"})
        mock_settings.paperless_custom_field_absender = None

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        # Create metadata JSON
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({"absender": "Test Sender", "date": "2024-01-01"}))

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = 42

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        mock_set_fields.assert_called_once()
        # Verify the custom fields include the mapped metadata
        call_args = mock_set_fields.call_args
        assert "Sender" in call_args[0][1]

    @patch("app.tasks.upload_to_paperless.set_document_custom_fields")
    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_legacy_absender_field(self, mock_log, mock_settings, mock_post, mock_poll, mock_set_fields, tmp_path):
        """Test legacy absender field configuration fallback."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = None
        mock_settings.paperless_custom_field_absender = "Absender"

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({"absender": "Legacy Sender"}))

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = 42

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"
        mock_set_fields.assert_called_once()
        call_args = mock_set_fields.call_args
        assert "Absender" in call_args[0][1]

    @patch("app.tasks.upload_to_paperless.set_document_custom_fields")
    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_invalid_json_mapping_handled(
        self, mock_log, mock_settings, mock_post, mock_poll, mock_set_fields, tmp_path
    ):
        """Test that invalid JSON mapping does not crash the task."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = "not-valid-json"
        mock_settings.paperless_custom_field_absender = None

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = 42

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        assert result["status"] == "Completed"

    @patch("app.tasks.upload_to_paperless.set_document_custom_fields")
    @patch("app.tasks.upload_to_paperless.poll_task_for_document_id")
    @patch("app.tasks.upload_to_paperless.requests.post")
    @patch("app.tasks.upload_to_paperless.settings")
    @patch("app.tasks.upload_to_paperless.log_task_progress")
    def test_custom_fields_failure_does_not_fail_upload(
        self, mock_log, mock_settings, mock_post, mock_poll, mock_set_fields, tmp_path
    ):
        """Test that custom field errors don't fail the entire upload."""
        mock_settings.paperless_host = "http://paperless:8000"
        mock_settings.paperless_ngx_api_token = "test-token"
        mock_settings.http_request_timeout = 30
        mock_settings.paperless_custom_fields_mapping = json.dumps({"absender": "Sender"})
        mock_settings.paperless_custom_field_absender = None

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps({"absender": "Test"}))

        mock_response = Mock()
        mock_response.text = '"task-uuid-123"'
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        mock_poll.return_value = 42
        mock_set_fields.side_effect = Exception("Custom fields error")

        result = upload_to_paperless.apply(args=[str(test_file)], kwargs={"file_id": 1}).get()

        # Upload should still succeed even though custom fields failed
        assert result["status"] == "Completed"
