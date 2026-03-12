"""Tests for app/api/imap_profiles.py and app/utils/allowed_types category helpers."""


import pytest

from app.utils.allowed_types import (
    ALL_CATEGORIES,
    DEFAULT_CATEGORIES,
    FILE_TYPE_CATEGORIES,
    get_allowed_types_for_categories,
)


@pytest.mark.unit
class TestFileTypeCategories:
    """Tests for FILE_TYPE_CATEGORIES and get_allowed_types_for_categories."""

    def test_all_category_keys_present(self):
        """Test that the six expected categories exist."""
        assert set(FILE_TYPE_CATEGORIES.keys()) == {"pdf", "office", "opendocument", "text", "web", "images"}

    def test_each_category_has_required_fields(self):
        """Test that every category entry has label, description, mime_types, extensions."""
        for key, info in FILE_TYPE_CATEGORIES.items():
            assert "label" in info, f"Category '{key}' missing 'label'"
            assert "description" in info, f"Category '{key}' missing 'description'"
            assert "mime_types" in info, f"Category '{key}' missing 'mime_types'"
            assert "extensions" in info, f"Category '{key}' missing 'extensions'"

    def test_pdf_category_contains_pdf_mime(self):
        """Test that the pdf category includes application/pdf."""
        assert "application/pdf" in FILE_TYPE_CATEGORIES["pdf"]["mime_types"]
        assert ".pdf" in FILE_TYPE_CATEGORIES["pdf"]["extensions"]

    def test_images_category_contains_jpeg(self):
        """Test that the images category includes image/jpeg."""
        assert "image/jpeg" in FILE_TYPE_CATEGORIES["images"]["mime_types"]
        assert ".jpg" in FILE_TYPE_CATEGORIES["images"]["extensions"]
        assert ".png" in FILE_TYPE_CATEGORIES["images"]["extensions"]

    def test_get_allowed_types_for_default_categories(self):
        """Test that DEFAULT_CATEGORIES excludes image MIME types."""
        mime_types, extensions = get_allowed_types_for_categories(DEFAULT_CATEGORIES)
        assert "application/pdf" in mime_types
        assert "application/msword" in mime_types
        # images should NOT be in the default
        assert "image/jpeg" not in mime_types
        assert ".jpg" not in extensions

    def test_get_allowed_types_for_all_categories(self):
        """Test that ALL_CATEGORIES includes image MIME types."""
        mime_types, extensions = get_allowed_types_for_categories(ALL_CATEGORIES)
        assert "image/jpeg" in mime_types
        assert ".jpg" in extensions
        assert "application/pdf" in mime_types

    def test_get_allowed_types_returns_frozensets(self):
        """Test that returned sets are frozensets."""
        mime_types, extensions = get_allowed_types_for_categories(["pdf"])
        assert isinstance(mime_types, frozenset)
        assert isinstance(extensions, frozenset)

    def test_get_allowed_types_unknown_category_ignored(self):
        """Test that unknown category keys are silently ignored."""
        mime_types, extensions = get_allowed_types_for_categories(["pdf", "nonexistent_category"])
        assert "application/pdf" in mime_types  # 'pdf' still works
        # No crash for unknown key

    def test_get_allowed_types_empty_list(self):
        """Test empty category list returns empty sets."""
        mime_types, extensions = get_allowed_types_for_categories([])
        assert mime_types == frozenset()
        assert extensions == frozenset()

    def test_default_categories_excludes_images(self):
        """Test that DEFAULT_CATEGORIES does not include 'images'."""
        assert "images" not in DEFAULT_CATEGORIES

    def test_all_categories_includes_images(self):
        """Test that ALL_CATEGORIES includes 'images'."""
        assert "images" in ALL_CATEGORIES

    def test_all_categories_is_superset_of_default(self):
        """Test that ALL_CATEGORIES contains all DEFAULT_CATEGORIES."""
        for cat in DEFAULT_CATEGORIES:
            assert cat in ALL_CATEGORIES


@pytest.mark.unit
class TestImapProfilesApiLogic:
    """Tests for ingestion profile validation helpers."""

    def test_validate_categories_accepts_valid_keys(self):
        """Test that valid category keys pass validation."""
        from app.api.imap_profiles import _validate_categories

        result = _validate_categories(["pdf", "office", "images"])
        assert set(result) == {"pdf", "office", "images"}

    def test_validate_categories_rejects_unknown_key(self):
        """Test that unknown category keys raise 422."""
        from fastapi import HTTPException

        from app.api.imap_profiles import _validate_categories

        with pytest.raises(HTTPException) as exc_info:
            _validate_categories(["pdf", "nonexistent"])
        assert exc_info.value.status_code == 422
        assert "nonexistent" in str(exc_info.value.detail)

    def test_validate_categories_deduplicates(self):
        """Test that duplicate category keys are de-duplicated while preserving order."""
        from app.api.imap_profiles import _validate_categories

        result = _validate_categories(["pdf", "pdf", "office", "pdf"])
        assert result == ["pdf", "office"]

    def test_to_response_serializes_profile(self, tmp_path):
        """Test _to_response produces expected dict shape."""
        from unittest.mock import MagicMock

        from app.api.imap_profiles import _to_response

        profile = MagicMock()
        profile.id = 42
        profile.name = "My Profile"
        profile.description = "Test description"
        profile.owner_id = "user@example.com"
        profile.allowed_categories = '["pdf","office"]'
        profile.is_builtin = False
        profile.created_at = None
        profile.updated_at = None

        result = _to_response(profile)
        assert result["id"] == 42
        assert result["name"] == "My Profile"
        assert result["allowed_categories"] == ["pdf", "office"]
        assert len(result["categories_detail"]) == 2
        assert result["categories_detail"][0]["key"] == "pdf"
        assert result["is_builtin"] is False

    def test_to_response_handles_invalid_categories_json(self):
        """Test _to_response gracefully handles invalid JSON in allowed_categories."""
        from unittest.mock import MagicMock

        from app.api.imap_profiles import _to_response

        profile = MagicMock()
        profile.id = 1
        profile.name = "Broken"
        profile.description = None
        profile.owner_id = None
        profile.allowed_categories = "this is not valid json {"
        profile.is_builtin = True
        profile.created_at = None
        profile.updated_at = None

        result = _to_response(profile)
        assert result["allowed_categories"] == []
