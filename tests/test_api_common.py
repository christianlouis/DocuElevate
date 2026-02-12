"""Tests for app/api/common.py module."""

import os
from unittest.mock import patch

import pytest

from app.api.common import resolve_file_path


@pytest.mark.unit
class TestResolveFilePath:
    """Tests for resolve_file_path function."""

    def test_relative_path_resolved_to_workdir(self):
        """Test that relative paths are resolved within workdir."""
        result = resolve_file_path("test.pdf")
        assert result.endswith("test.pdf")
        assert os.path.isabs(result)

    def test_relative_path_with_subfolder(self):
        """Test relative path with subfolder parameter."""
        result = resolve_file_path("test.pdf", subfolder="processed")
        assert "processed" in result
        assert result.endswith("test.pdf")

    def test_absolute_path_within_workdir(self, tmp_path):
        """Test absolute path within workdir is accepted."""
        with patch("app.api.common.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            test_file = str(tmp_path / "test.pdf")
            result = resolve_file_path(test_file)
            assert result == test_file

    def test_path_traversal_blocked(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        from fastapi import HTTPException

        with patch("app.api.common.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            with pytest.raises(HTTPException) as exc_info:
                resolve_file_path("../../etc/passwd")
            assert exc_info.value.status_code == 400

    def test_path_traversal_absolute_blocked(self, tmp_path):
        """Test that absolute paths outside workdir are blocked."""
        from fastapi import HTTPException

        with patch("app.api.common.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            with pytest.raises(HTTPException) as exc_info:
                resolve_file_path("/etc/passwd")
            assert exc_info.value.status_code == 400
