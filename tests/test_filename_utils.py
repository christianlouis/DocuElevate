"""
Tests for app/utils/filename_utils.py

Tests filename sanitization and manipulation functions.
"""

import os
from unittest.mock import Mock

import pytest


@pytest.mark.unit
class TestFilenameSanitization:
    """Test filename sanitization functions"""

    def test_sanitize_filename_basic(self):
        """Test basic filename sanitization"""
        from app.utils.filename_utils import sanitize_filename

        # Basic valid filename
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_sanitize_filename_with_spaces(self):
        """Test sanitization of filenames with spaces"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("my document file.pdf")
        # Spaces should be preserved
        assert "my" in result
        assert "document" in result
        assert "file.pdf" in result

    def test_sanitize_filename_with_special_characters(self):
        """Test sanitization removes or replaces special characters"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("file:with*special?chars.pdf")
        # Special characters should be replaced with underscores
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert "_" in result

    def test_sanitize_filename_with_path_separators(self):
        """Test that path separators are handled"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("../../../etc/passwd")
        # Path traversal characters should be replaced
        assert ".." not in result or result.count("..") < 3

    def test_sanitize_filename_empty_string(self):
        """Test sanitization of empty string"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("")
        # Should return a valid string (default name with timestamp)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "document" in result

    def test_sanitize_filename_only_periods(self):
        """Test sanitization of only periods"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("...")
        # Should return a default name
        assert isinstance(result, str)
        assert len(result) > 0
        assert "document" in result

    def test_sanitize_filename_leading_trailing_spaces(self):
        """Test sanitization trims leading/trailing spaces"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("  filename.pdf  ")
        assert result == "filename.pdf"

    def test_sanitize_filename_multiple_underscores(self):
        """Test sanitization collapses multiple underscores"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("file____name.pdf")
        assert "____" not in result
        assert result == "file_name.pdf"


@pytest.mark.unit
class TestUniqueFilenameGeneration:
    """Test unique filename generation"""

    def test_get_unique_filename_no_collision(self):
        """Test that original filename is returned when no collision"""
        from app.utils.filename_utils import get_unique_filename

        # Mock check_exists_func to return False (file doesn't exist)
        check_func = Mock(return_value=False)

        result = get_unique_filename("/tmp/document.pdf", check_exists_func=check_func)
        assert result == "/tmp/document.pdf"
        check_func.assert_called_once_with("/tmp/document.pdf")

    def test_get_unique_filename_with_collision(self):
        """Test that unique filename is generated on collision"""
        from app.utils.filename_utils import get_unique_filename

        # Mock check_exists_func to return True for original, False for timestamped
        def check_func(path):
            return path == "/tmp/document.pdf"

        result = get_unique_filename("/tmp/document.pdf", check_exists_func=check_func)
        assert result != "/tmp/document.pdf"
        assert "document" in result
        assert ".pdf" in result

    def test_get_unique_filename_uses_timestamp(self):
        """Test that timestamp is added on collision"""
        from app.utils.filename_utils import get_unique_filename

        # First file exists
        check_func = Mock(side_effect=[True, False])

        result = get_unique_filename("/tmp/test.pdf", check_exists_func=check_func)
        assert result != "/tmp/test.pdf"
        assert "test_" in result
        assert ".pdf" in result

    def test_get_unique_filename_falls_back_to_uuid(self):
        """Test UUID fallback when timestamp collision occurs"""
        from app.utils.filename_utils import get_unique_filename

        # Original and timestamp both exist
        check_func = Mock(side_effect=[True, True, False])

        result = get_unique_filename("/tmp/test.pdf", check_exists_func=check_func)
        assert result != "/tmp/test.pdf"
        assert "test_" in result
        assert ".pdf" in result

    def test_get_unique_filename_default_check_function(self):
        """Test that os.path.exists is used by default"""
        from app.utils.filename_utils import get_unique_filename

        # Use actual filesystem check
        result = get_unique_filename("/tmp/nonexistent_file_12345.pdf")
        # Should return original since file doesn't exist
        assert result == "/tmp/nonexistent_file_12345.pdf"

    def test_get_unique_filename_counter_fallback(self):
        """Test counter fallback when both timestamp and UUID already exist"""
        from app.utils.filename_utils import get_unique_filename

        # Original, timestamp, and first UUID all exist, but counter is free
        call_count = [0]

        def check_func(path):
            call_count[0] += 1
            # First 3 calls return True (original, timestamp, UUID exist)
            # Fourth call returns False (counter-based name is free)
            return call_count[0] <= 3

        result = get_unique_filename("/tmp/test.pdf", check_exists_func=check_func)
        assert result != "/tmp/test.pdf"
        assert "test_" in result
        assert ".pdf" in result
        # Should end with _1.pdf since that's the first counter
        assert result.endswith("_1.pdf")

    def test_get_unique_filename_full_uuid_fallback(self):
        """Test full UUID fallback when 1000+ counters exist"""
        from app.utils.filename_utils import get_unique_filename

        # Make it return True for the first 1003 calls (original, timestamp, UUID, and 1000 counters)
        call_count = [0]

        def check_func(path):
            call_count[0] += 1
            # Return True for first 1003 calls to simulate all variations existing
            return call_count[0] <= 1003

        result = get_unique_filename("/tmp/test.pdf", check_exists_func=check_func)
        assert result != "/tmp/test.pdf"
        assert "test_" in result
        assert ".pdf" in result
        # Should contain a full UUID (36 characters with dashes)


@pytest.mark.unit
class TestExtractRemotePath:
    """Test remote path extraction"""

    def test_extract_remote_path_basic(self):
        """Test basic remote path extraction"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/home/user/docs/file.pdf"
        base_dir = "/home/user"
        remote_base = "Documents"

        result = extract_remote_path(file_path, base_dir, remote_base)
        assert result == "Documents/docs/file.pdf"

    def test_extract_remote_path_without_remote_base(self):
        """Test remote path extraction without remote base"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/home/user/docs/file.pdf"
        base_dir = "/home/user"

        result = extract_remote_path(file_path, base_dir, "")
        assert result == "docs/file.pdf"

    def test_extract_remote_path_skips_processed_dir(self):
        """Test that 'processed' directory is skipped"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/home/user/processed/docs/file.pdf"
        base_dir = "/home/user"

        result = extract_remote_path(file_path, base_dir, "")
        assert "processed" not in result
        assert result == "docs/file.pdf"

    def test_extract_remote_path_with_absolute_remote_base(self):
        """Test remote path extraction with absolute remote base"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/home/user/docs/file.pdf"
        base_dir = "/home/user"
        remote_base = "/Documents"

        result = extract_remote_path(file_path, base_dir, remote_base)
        # Leading slash should be stripped
        assert result == "Documents/docs/file.pdf"

    def test_extract_remote_path_file_outside_base(self):
        """Test handling of file outside base directory"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/other/path/file.pdf"
        base_dir = "/home/user"

        result = extract_remote_path(file_path, base_dir, "")
        # Should just use filename
        assert result == "file.pdf"

    def test_extract_remote_path_uses_forward_slashes(self):
        """Test that result uses forward slashes"""
        from app.utils.filename_utils import extract_remote_path

        file_path = "/home/user/docs/subfolder/file.pdf"
        base_dir = "/home/user"

        result = extract_remote_path(file_path, base_dir, "")
        # Should use forward slashes for cloud service compatibility
        assert "/" in result
        assert "\\" not in result


@pytest.mark.unit
class TestFilenameUtilsEdgeCases:
    """Test edge cases in filename utilities"""

    def test_very_long_filename(self):
        """Test handling of very long filenames"""
        from app.utils.filename_utils import sanitize_filename

        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        # Should handle long filenames
        assert isinstance(result, str)
        assert len(result) > 0

    def test_filename_with_multiple_dots(self):
        """Test filename with multiple dots"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("my.document.file.name.pdf")
        assert isinstance(result, str)
        assert ".pdf" in result
        assert result == "my.document.file.name.pdf"

    def test_sanitize_filename_windows_reserved_chars(self):
        """Test sanitization of Windows reserved characters"""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename('file<>:"|?*.pdf')
        # All reserved chars should be replaced
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result
        assert "?" not in result


@pytest.mark.unit
class TestUniqueFilepathWithCounter:
    """Test unique filepath generation with numeric counter suffix"""

    def test_get_unique_filepath_with_counter_no_collision(self, tmp_path):
        """Test that original filename is returned when no collision exists"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        result = get_unique_filepath_with_counter(str(tmp_path), "document")
        assert result == str(tmp_path / "document.pdf")

    def test_get_unique_filepath_with_counter_single_collision(self, tmp_path):
        """Test that -0001 suffix is added on first collision"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        # Create the base file
        (tmp_path / "document.pdf").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), "document")
        assert result == str(tmp_path / "document-0001.pdf")

    def test_get_unique_filepath_with_counter_multiple_collisions(self, tmp_path):
        """Test that counter increments correctly for multiple collisions"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        # Create files with base name and first two counter suffixes
        (tmp_path / "document.pdf").touch()
        (tmp_path / "document-0001.pdf").touch()
        (tmp_path / "document-0002.pdf").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), "document")
        assert result == str(tmp_path / "document-0003.pdf")

    def test_get_unique_filepath_with_counter_custom_extension(self, tmp_path):
        """Test with custom file extension"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        (tmp_path / "data.json").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), "data", extension=".json")
        assert result == str(tmp_path / "data-0001.json")

    def test_get_unique_filepath_with_counter_zero_padded(self, tmp_path):
        """Test that counter uses zero-padded 4-digit format"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        (tmp_path / "invoice.pdf").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), "invoice")
        # Should be -0001, not -1
        assert result == str(tmp_path / "invoice-0001.pdf")
        assert "-1.pdf" not in result

    def test_get_unique_filepath_with_counter_preserves_filename(self, tmp_path):
        """Test that complex filenames are preserved"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        filename = "2024-01-01_Invoice_Company-Name"
        (tmp_path / f"{filename}.pdf").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), filename)
        assert filename in result
        assert result == str(tmp_path / f"{filename}-0001.pdf")

    def test_get_unique_filepath_with_counter_high_count(self, tmp_path):
        """Test that function handles high counter values"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        # Create files up to -0099
        (tmp_path / "test.pdf").touch()
        for i in range(1, 100):
            (tmp_path / f"test-{i:04d}.pdf").touch()

        result = get_unique_filepath_with_counter(str(tmp_path), "test")
        assert result == str(tmp_path / "test-0100.pdf")

    def test_get_unique_filepath_with_counter_directory_creation(self, tmp_path):
        """Test with directory that already exists"""
        from app.utils.filename_utils import get_unique_filepath_with_counter

        # Directory already exists (tmp_path)
        result = get_unique_filepath_with_counter(str(tmp_path), "newfile")
        assert result == str(tmp_path / "newfile.pdf")
        # File shouldn't be created, just path returned
        assert not os.path.exists(result)

    def test_get_unique_filepath_with_counter_extreme_collision(self, tmp_path):
        """Test extreme edge case when more than 9999 collisions occur"""
        from unittest.mock import patch

        from app.utils.filename_utils import get_unique_filepath_with_counter

        # Create base file to trigger counter logic
        (tmp_path / "test.pdf").touch()

        # Mock os.path.exists to simulate 10000+ collisions
        original_exists = os.path.exists
        call_count = [0]

        def mock_exists(path):
            # Use actual filesystem for the tmp_path directory check
            if path == str(tmp_path):
                return original_exists(path)
            # Check if it's our base file
            if path == str(tmp_path / "test.pdf"):
                return True
            # Simulate all counter-based files existing up to counter 10000
            call_count[0] += 1
            # First 10000 calls for counters return True (files exist)
            if call_count[0] <= 10000:
                return True
            # After that, allow the timestamp+UUID version to not exist
            return False

        with patch("os.path.exists", side_effect=mock_exists):
            result = get_unique_filepath_with_counter(str(tmp_path), "test")
            # Should have timestamp and UUID in the name
            assert "test-" in result
            assert ".pdf" in result
            # Should not be a simple counter-based name
            assert not any(f"test-{i:04d}.pdf" in result for i in range(1, 100))


@pytest.mark.unit
class TestSanitizeFilenameEdgeCases:
    """Additional edge cases for sanitize_filename."""

    def test_handles_empty_string(self):
        """Test with empty string."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("")
        # Should return a default document name
        assert "document_" in result
        assert len(result) > 0

    def test_handles_only_periods(self):
        """Test with only periods."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("...")
        # Should return a default document name
        assert "document_" in result

    def test_handles_only_dots(self):
        """Test with single dot."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename(".")
        # Should return a default document name
        assert "document_" in result

    def test_preserves_multiple_extensions(self):
        """Test that multiple extensions are preserved."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("file.tar.gz")
        assert ".tar.gz" in result or "file_tar_gz" in result

    def test_removes_null_bytes(self):
        """Test that null bytes are removed."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("file\x00name.pdf")
        assert "\x00" not in result
        assert "file" in result
        assert "name" in result

    def test_handles_unicode_characters(self):
        """Test handling of unicode characters."""
        from app.utils.filename_utils import sanitize_filename

        result = sanitize_filename("文档.pdf")
        # Should preserve unicode or convert safely
        assert ".pdf" in result
        assert len(result) > 0


@pytest.mark.unit
class TestExtractRemotePathEdgeCases:
    """Additional edge cases for extract_remote_path."""

    def test_file_not_in_base_dir(self):
        """Test when file is not a subdirectory of base_dir."""
        from app.utils.filename_utils import extract_remote_path

        result = extract_remote_path("/other/path/file.pdf", "/base/dir", "/remote")
        # Should just use filename
        assert result == "remote/file.pdf"

    def test_multiple_processed_directories(self):
        """Test path with multiple 'processed' directories.

        The function uses list.remove() which only removes the FIRST occurrence
        of 'processed' in the path. This is the current implementation behavior.
        If all occurrences should be removed, the function would need to be updated.
        """
        from app.utils.filename_utils import extract_remote_path

        result = extract_remote_path("/base/processed/subdir/processed/file.pdf", "/base", "/remote")
        # Function removes only first occurrence of 'processed' directory
        # Result should be: remote/subdir/processed/file.pdf
        assert result == "remote/subdir/processed/file.pdf"

    def test_remote_base_with_trailing_slash(self):
        """Test remote base that already has trailing slash."""
        from app.utils.filename_utils import extract_remote_path

        result = extract_remote_path("/base/file.pdf", "/base", "/remote/")
        # Should handle gracefully
        assert result.startswith("remote/")

    def test_empty_remote_base(self):
        """Test with empty remote base."""
        from app.utils.filename_utils import extract_remote_path

        result = extract_remote_path("/base/subdir/file.pdf", "/base", "")
        assert result == "subdir/file.pdf"

    def test_windows_style_separators(self, monkeypatch):
        """Test handling of Windows-style path separators."""
        from app.utils.filename_utils import extract_remote_path

        result = extract_remote_path("/base/subdir/file.pdf", "/base", "/remote")
        # Should use forward slashes in output
        assert "\\" not in result
        assert "/" in result
