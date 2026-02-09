"""Tests for app/tasks/finalize_document_storage.py module."""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestFinalizeDocumentStorageHelpers:
    """Tests for helper functions used in finalize_document_storage."""

    def test_get_configured_services_from_validator(self):
        """Test that get_configured_services_from_validator returns a dict."""
        from app.tasks.send_to_all import get_configured_services_from_validator

        result = get_configured_services_from_validator()
        assert isinstance(result, dict)

    def test_module_imports(self):
        """Test that the module can be imported without errors."""
        from app.tasks.finalize_document_storage import finalize_document_storage
        assert callable(finalize_document_storage)
