"""Additional tests for upload_to_ftp task."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestUploadToFtp:
    """Tests for upload_to_ftp task."""

    def test_module_imports(self):
        """Test that the module can be imported."""
        from app.tasks.upload_to_ftp import upload_to_ftp

        assert callable(upload_to_ftp)
