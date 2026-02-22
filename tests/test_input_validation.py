"""
Unit and integration tests for app/utils/input_validation.py.

Covers all validators: sort field/order, search query, task ID, and setting key.
"""

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# validate_sort_field
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSortField:
    """Tests for validate_sort_field."""

    def test_accepts_valid_sort_fields(self):
        """All declared sort fields should be accepted."""
        from app.utils.input_validation import ALLOWED_SORT_FIELDS, validate_sort_field

        for field in ALLOWED_SORT_FIELDS:
            assert validate_sort_field(field) == field

    def test_rejects_unknown_field(self):
        """An unknown sort field should raise 422."""
        from app.utils.input_validation import validate_sort_field

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_field("nonexistent_field")
        assert exc_info.value.status_code == 422

    def test_rejects_sql_injection_attempt(self):
        """A SQL-injection-style field name should raise 422."""
        from app.utils.input_validation import validate_sort_field

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_field("id; DROP TABLE files; --")
        assert exc_info.value.status_code == 422

    def test_rejects_empty_string(self):
        """An empty string should raise 422."""
        from app.utils.input_validation import validate_sort_field

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_field("")
        assert exc_info.value.status_code == 422

    def test_error_message_lists_allowed_values(self):
        """Error detail should mention the allowed values."""
        from app.utils.input_validation import validate_sort_field

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_field("bad_field")
        assert "created_at" in exc_info.value.detail


# ---------------------------------------------------------------------------
# validate_sort_order
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSortOrder:
    """Tests for validate_sort_order."""

    def test_accepts_asc(self):
        from app.utils.input_validation import validate_sort_order

        assert validate_sort_order("asc") == "asc"

    def test_accepts_desc(self):
        from app.utils.input_validation import validate_sort_order

        assert validate_sort_order("desc") == "desc"

    def test_rejects_uppercase_asc(self):
        """Validation is case-sensitive; 'ASC' should be rejected."""
        from app.utils.input_validation import validate_sort_order

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_order("ASC")
        assert exc_info.value.status_code == 422

    def test_rejects_arbitrary_string(self):
        from app.utils.input_validation import validate_sort_order

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_order("random")
        assert exc_info.value.status_code == 422

    def test_rejects_empty_string(self):
        from app.utils.input_validation import validate_sort_order

        with pytest.raises(HTTPException) as exc_info:
            validate_sort_order("")
        assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# validate_search_query
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSearchQuery:
    """Tests for validate_search_query."""

    def test_returns_none_for_none_input(self):
        from app.utils.input_validation import validate_search_query

        assert validate_search_query(None) is None

    def test_returns_none_for_blank_string(self):
        from app.utils.input_validation import validate_search_query

        assert validate_search_query("   ") is None

    def test_strips_whitespace(self):
        from app.utils.input_validation import validate_search_query

        assert validate_search_query("  hello  ") == "hello"

    def test_accepts_normal_query(self):
        from app.utils.input_validation import validate_search_query

        assert validate_search_query("invoice 2024") == "invoice 2024"

    def test_rejects_too_long_query(self):
        """A query longer than 255 characters should raise 422."""
        from app.utils.input_validation import MAX_SEARCH_QUERY_LENGTH, validate_search_query

        long_query = "a" * (MAX_SEARCH_QUERY_LENGTH + 1)
        with pytest.raises(HTTPException) as exc_info:
            validate_search_query(long_query)
        assert exc_info.value.status_code == 422

    def test_accepts_query_at_max_length(self):
        """A query exactly at the maximum length should be accepted."""
        from app.utils.input_validation import MAX_SEARCH_QUERY_LENGTH, validate_search_query

        exact_query = "a" * MAX_SEARCH_QUERY_LENGTH
        assert validate_search_query(exact_query) == exact_query


# ---------------------------------------------------------------------------
# validate_task_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateTaskId:
    """Tests for validate_task_id."""

    def test_accepts_valid_uuid(self):
        from app.utils.input_validation import validate_task_id

        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        assert validate_task_id(valid_uuid) == valid_uuid

    def test_accepts_uppercase_uuid(self):
        """UUID validation should be case-insensitive."""
        from app.utils.input_validation import validate_task_id

        upper_uuid = "550E8400-E29B-41D4-A716-446655440000"
        assert validate_task_id(upper_uuid) == upper_uuid

    def test_rejects_non_v4_uuid(self):
        """A syntactically valid UUID with a version other than 4 should be rejected."""
        from app.utils.input_validation import validate_task_id

        # Version 1 UUID (version digit is '1', not '4')
        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("550e8400-e29b-11d4-a716-446655440000")
        assert exc_info.value.status_code == 422

    def test_rejects_short_string(self):
        from app.utils.input_validation import validate_task_id

        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("abc-123")
        assert exc_info.value.status_code == 422

    def test_rejects_sql_injection(self):
        from app.utils.input_validation import validate_task_id

        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("'; DROP TABLE processing_logs; --")
        assert exc_info.value.status_code == 422

    def test_rejects_path_traversal(self):
        from app.utils.input_validation import validate_task_id

        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("../../etc/passwd")
        assert exc_info.value.status_code == 422

    def test_rejects_empty_string(self):
        from app.utils.input_validation import validate_task_id

        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("")
        assert exc_info.value.status_code == 422

    def test_error_message_mentions_uuid(self):
        from app.utils.input_validation import validate_task_id

        with pytest.raises(HTTPException) as exc_info:
            validate_task_id("not-a-uuid")
        assert "UUID" in exc_info.value.detail


# ---------------------------------------------------------------------------
# validate_setting_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSettingKey:
    """Tests for validate_setting_key."""

    def test_accepts_known_setting_key(self):
        """A key that exists in SETTING_METADATA should be accepted."""
        from app.utils.input_validation import validate_setting_key

        # 'workdir' is always defined in SETTING_METADATA
        assert validate_setting_key("workdir") == "workdir"

    def test_rejects_unknown_key_with_404(self):
        """An unknown but syntactically valid key should raise 404."""
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("totally_unknown_key_xyz")
        assert exc_info.value.status_code == 404

    def test_rejects_key_with_special_characters(self):
        """A key with special characters (e.g., injection attempt) should raise 400."""
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("__class__")
        assert exc_info.value.status_code == 400

    def test_rejects_key_with_dot_notation(self):
        """Dot-separated attribute traversal should be rejected."""
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("model_fields")
        # model_fields is a Pydantic internal but not in SETTING_METADATA -> 404
        assert exc_info.value.status_code == 404

    def test_rejects_dunder_attributes(self):
        """Double-underscore attributes should be rejected (bad format)."""
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("__dict__")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_key(self):
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("")
        assert exc_info.value.status_code == 400

    def test_rejects_key_starting_with_digit(self):
        """Keys starting with a digit should be rejected."""
        from app.utils.input_validation import validate_setting_key

        with pytest.raises(HTTPException) as exc_info:
            validate_setting_key("1nvalid_key")
        assert exc_info.value.status_code == 400
