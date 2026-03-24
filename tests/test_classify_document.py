"""Tests for the classify_document Celery task.

Covers the ``classify_document_task`` in ``app/tasks/classify_document.py``.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import ClassificationRuleModel, FileRecord
from app.tasks.classify_document import _load_custom_rules

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file_record(db_session, **overrides):
    """Insert a minimal FileRecord and return it."""
    defaults = {
        "owner_id": "test-user",
        "filehash": "abc123",
        "original_filename": "Invoice_2024.pdf",
        "local_filename": "/tmp/test.pdf",
        "file_size": 1024,
        "mime_type": "application/pdf",
        "ocr_text": "Invoice number: 12345. Amount due: $500.",
        "ai_metadata": None,
    }
    defaults.update(overrides)
    fr = FileRecord(**defaults)
    db_session.add(fr)
    db_session.commit()
    db_session.refresh(fr)
    return fr


def _make_rule(db_session, **overrides):
    """Insert a ClassificationRuleModel and return it."""
    defaults = {
        "owner_id": None,
        "name": "test_rule",
        "category": "test_category",
        "rule_type": "filename_pattern",
        "pattern": r"(?i)test",
        "priority": 0,
        "case_sensitive": False,
        "enabled": True,
    }
    defaults.update(overrides)
    rule = ClassificationRuleModel(**defaults)
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# _load_custom_rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadCustomRules:
    """Test the custom rule loading helper."""

    @patch("app.tasks.classify_document.SessionLocal")
    def test_loads_enabled_rules(self, mock_session_local):
        """Should load enabled rules from the database."""
        mock_rule = MagicMock()
        mock_rule.name = "rule1"
        mock_rule.category = "invoice"
        mock_rule.rule_type = "filename_pattern"
        mock_rule.pattern = r"(?i)invoice"
        mock_rule.priority = 10
        mock_rule.case_sensitive = False

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_rule]
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        rules = _load_custom_rules(owner_id="test-user")
        assert len(rules) == 1
        assert rules[0].name == "rule1"
        assert rules[0].category == "invoice"


# ---------------------------------------------------------------------------
# classify_document_task (integration-style with mocked DB and Celery)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassifyDocumentTask:
    """Test the Celery classify_document_task."""

    @patch("app.tasks.classify_document.log_task_progress")
    @patch("app.tasks.classify_document._load_custom_rules", return_value=[])
    @patch("app.tasks.classify_document.SessionLocal")
    def test_classify_invoice_file(self, mock_session_local, mock_load_rules, mock_log):
        """Should classify a file with invoice filename and text as 'invoice'."""
        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        mock_file.original_filename = "Invoice_2024.pdf"
        mock_file.ocr_text = "Invoice number: 12345. Amount due: $500."
        mock_file.ai_metadata = None
        mock_file.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.classify_document import classify_document_task

        # Call the underlying function directly via .run(), bypassing Celery
        result = classify_document_task.run(1, owner_id="test-user")

        assert result["status"] == "success"
        assert result["category"] == "invoice"
        assert result["confidence"] > 0

        # Verify ai_metadata was updated
        assert mock_file.ai_metadata is not None
        metadata = json.loads(mock_file.ai_metadata)
        assert "classification" in metadata
        assert metadata["classification"]["category"] == "invoice"

    @patch("app.tasks.classify_document.log_task_progress")
    @patch("app.tasks.classify_document.SessionLocal")
    def test_classify_file_not_found(self, mock_session_local, mock_log):
        """Should return error when file record is not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.classify_document import classify_document_task

        result = classify_document_task.run(99999)
        assert result["status"] == "error"

    @patch("app.tasks.classify_document.log_task_progress")
    @patch("app.tasks.classify_document._load_custom_rules", return_value=[])
    @patch("app.tasks.classify_document.SessionLocal")
    def test_classify_preserves_existing_metadata(self, mock_session_local, mock_load_rules, mock_log):
        """Should preserve existing ai_metadata fields and add classification."""
        existing_meta = json.dumps({"document_type": "Invoice", "tags": ["finance"]})

        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 2
        mock_file.original_filename = "doc.pdf"
        mock_file.ocr_text = ""
        mock_file.ai_metadata = existing_meta
        mock_file.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.classify_document import classify_document_task

        classify_document_task.run(2)

        # Check that existing fields are preserved
        metadata = json.loads(mock_file.ai_metadata)
        assert metadata["tags"] == ["finance"]
        assert metadata["document_type"] == "Invoice"
        assert "classification" in metadata

    @patch("app.tasks.classify_document.log_task_progress")
    @patch("app.tasks.classify_document._load_custom_rules", return_value=[])
    @patch("app.tasks.classify_document.SessionLocal")
    def test_classify_sets_document_type_when_missing(self, mock_session_local, mock_load_rules, mock_log):
        """Should set document_type from classification when not already present."""
        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 3
        mock_file.original_filename = "Invoice_2024.pdf"
        mock_file.ocr_text = "Invoice number: 12345"
        mock_file.ai_metadata = json.dumps({"tags": ["test"]})
        mock_file.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.classify_document import classify_document_task

        classify_document_task.run(3)

        metadata = json.loads(mock_file.ai_metadata)
        assert metadata["document_type"] == "Invoice"

    @patch("app.tasks.classify_document.log_task_progress")
    @patch("app.tasks.classify_document._load_custom_rules", return_value=[])
    @patch("app.tasks.classify_document.SessionLocal")
    def test_classify_unknown_document(self, mock_session_local, mock_load_rules, mock_log):
        """Should classify as 'unknown' when no rules match."""
        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 4
        mock_file.original_filename = "random_file.pdf"
        mock_file.ocr_text = "Lorem ipsum dolor sit amet."
        mock_file.ai_metadata = None
        mock_file.owner_id = "test-user"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_file
        mock_session_local.return_value.__enter__ = MagicMock(return_value=mock_db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=False)

        from app.tasks.classify_document import classify_document_task

        result = classify_document_task.run(4)

        assert result["category"] == "unknown"
        assert result["confidence"] == 0

    def test_classify_document_task_is_celery_task(self):
        """Task should be registered as a Celery task."""
        from app.tasks.classify_document import classify_document_task

        assert hasattr(classify_document_task, "apply_async")
        assert hasattr(classify_document_task, "delay")
        assert callable(classify_document_task)
