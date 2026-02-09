"""Tests for app/tasks/upload_to_email.py module."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestUploadToEmail:
    """Tests for upload_to_email task."""

    def test_module_imports(self):
        """Test that the module can be imported."""
        from app.tasks.upload_to_email import upload_to_email
        assert callable(upload_to_email)
