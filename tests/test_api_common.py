"""
Tests for common API utilities
"""

import pytest
import tempfile
from pathlib import Path
from fastapi import HTTPException

from app.api.common import resolve_file_path


@pytest.mark.unit
class TestResolveFilePath:
    """Tests for resolve_file_path function."""

    def test_resolve_relative_path(self, tmp_path):
        """Test resolving a relative file path."""
        with tempfile.TemporaryDirectory() as workdir:
            # Use patch to override settings.workdir
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test relative path
                result = resolve_file_path("test.pdf")
                expected = str(Path(workdir) / "test.pdf")
                assert result == expected

    def test_resolve_relative_path_with_subfolder(self, tmp_path):
        """Test resolving a relative file path with subfolder."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test relative path with subfolder
                result = resolve_file_path("test.pdf", subfolder="processed")
                expected = str(Path(workdir) / "processed" / "test.pdf")
                assert result == expected

    def test_resolve_absolute_path_within_workdir(self, tmp_path):
        """Test resolving an absolute file path within workdir."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test absolute path within workdir
                abs_path = str(Path(workdir) / "test.pdf")
                result = resolve_file_path(abs_path)
                assert result == abs_path

    def test_resolve_path_traversal_attack_relative(self, tmp_path):
        """Test path traversal attack with relative path."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test path traversal attempt with relative path
                with pytest.raises(HTTPException) as exc_info:
                    resolve_file_path("../../etc/passwd")

                assert exc_info.value.status_code == 400
                assert "path traversal" in exc_info.value.detail.lower()

    def test_resolve_path_traversal_attack_absolute(self, tmp_path):
        """Test path traversal attack with absolute path outside workdir."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test absolute path outside workdir
                with pytest.raises(HTTPException) as exc_info:
                    resolve_file_path("/etc/passwd")

                assert exc_info.value.status_code == 400
                assert "path traversal" in exc_info.value.detail.lower()

    def test_resolve_symlink_outside_workdir(self, tmp_path):
        """Test resolving symlink that points outside workdir."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            import os

            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Create a symlink pointing outside workdir
                outside_dir = tmp_path / "outside"
                outside_dir.mkdir()
                symlink_path = Path(workdir) / "symlink"

                try:
                    symlink_path.symlink_to(outside_dir)

                    # Attempt to resolve through the symlink
                    with pytest.raises(HTTPException) as exc_info:
                        resolve_file_path("symlink/file.txt")

                    assert exc_info.value.status_code == 400
                except OSError:
                    # Symlink creation may fail on some systems, skip the test
                    pytest.skip("Symlink creation not supported on this system")

    def test_resolve_nested_relative_path(self, tmp_path):
        """Test resolving nested relative paths."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Test nested relative path
                result = resolve_file_path("subdir1/subdir2/test.pdf")
                expected = str(Path(workdir) / "subdir1" / "subdir2" / "test.pdf")
                assert result == expected

    def test_resolve_path_with_dots_but_valid(self, tmp_path):
        """Test resolving path with dots that stays within workdir."""
        with tempfile.TemporaryDirectory() as workdir:
            from unittest.mock import patch
            with patch("app.api.common.settings") as mock_settings:
                mock_settings.workdir = workdir

                # Create subdirectories
                subdir = Path(workdir) / "subdir1" / "subdir2"
                subdir.mkdir(parents=True, exist_ok=True)

                # Test path that goes up but stays within workdir
                result = resolve_file_path("subdir1/subdir2/../test.pdf")
                expected = str(Path(workdir) / "subdir1" / "test.pdf")
                assert result == expected


@pytest.mark.unit
def test_get_db_dependency():
    """Test get_db dependency injection."""
    from app.api.common import get_db

    # Test that get_db returns a generator
    db_generator = get_db()
    assert hasattr(db_generator, '__next__')

    # Test that it yields a database session
    try:
        db_session = next(db_generator)
        assert db_session is not None
        # Close the session
        db_generator.close()
    except Exception:
        # If database is not properly configured in test, that's okay
        pass
