"""Tests for app/tasks/embed_metadata_into_pdf.py module."""
import os
import pytest
from unittest.mock import patch, MagicMock

from app.tasks.embed_metadata_into_pdf import persist_metadata
from app.utils.filename_utils import get_unique_filepath_with_counter


@pytest.mark.unit
class TestUniqueFilepath:
    """Tests for unique filepath collision handling - now using get_unique_filepath_with_counter."""

    def test_returns_path_when_no_conflict(self, tmp_path):
        """Test returns original path when no conflict."""
        result = get_unique_filepath_with_counter(str(tmp_path), "test", ".pdf")
        assert result == str(tmp_path / "test.pdf")

    def test_appends_counter_on_conflict(self, tmp_path):
        """Test appends -0001 counter when file already exists."""
        # Create the initial file
        (tmp_path / "test.pdf").touch()
        result = get_unique_filepath_with_counter(str(tmp_path), "test", ".pdf")
        assert result == str(tmp_path / "test-0001.pdf")

    def test_increments_counter(self, tmp_path):
        """Test increments counter for multiple conflicts."""
        (tmp_path / "test.pdf").touch()
        (tmp_path / "test-0001.pdf").touch()
        result = get_unique_filepath_with_counter(str(tmp_path), "test", ".pdf")
        assert result == str(tmp_path / "test-0002.pdf")


@pytest.mark.unit
class TestPersistMetadata:
    """Tests for persist_metadata function."""

    def test_saves_metadata_as_json(self, tmp_path):
        """Test that metadata is saved as JSON file."""
        import json

        pdf_path = str(tmp_path / "test.pdf")
        metadata = {"document_type": "invoice", "tags": ["test"]}

        result = persist_metadata(metadata, pdf_path)
        assert result == str(tmp_path / "test.json")
        assert os.path.exists(result)

        with open(result) as f:
            loaded = json.load(f)
        assert loaded == metadata

    def test_json_filename_matches_pdf(self, tmp_path):
        """Test that JSON filename matches PDF filename."""
        pdf_path = str(tmp_path / "2024-01-01_Invoice.pdf")
        metadata = {"title": "Invoice"}

        result = persist_metadata(metadata, pdf_path)
        assert result.endswith("2024-01-01_Invoice.json")
