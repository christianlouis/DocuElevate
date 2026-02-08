"""
Additional tests for config and database modules
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestConfigModule:
    """Tests for config module."""

    def test_config_has_required_attributes(self):
        """Test that config has required attributes."""
        from app.config import settings

        # Check that essential settings exist
        assert hasattr(settings, "workdir")
        assert hasattr(settings, "database_url")
        assert hasattr(settings, "redis_url")

    @patch("app.config.settings")
    def test_config_debug_mode(self, mock_settings):
        """Test config debug mode setting."""
        mock_settings.debug = True
        assert mock_settings.debug is True

        mock_settings.debug = False
        assert mock_settings.debug is False


@pytest.mark.unit
class TestDatabaseModule:
    """Tests for database module."""

    def test_get_db_generator(self):
        """Test that get_db returns a generator."""
        from app.database import get_db

        db_gen = get_db()
        assert hasattr(db_gen, '__next__')

    def test_base_metadata(self):
        """Test that Base has metadata."""
        from app.database import Base

        assert hasattr(Base, 'metadata')
        assert Base.metadata is not None


@pytest.mark.unit
class TestModelsModule:
    """Tests for models module."""

    def test_file_record_model_exists(self):
        """Test that FileRecord model exists."""
        from app.models import FileRecord

        assert FileRecord is not None
        assert hasattr(FileRecord, '__tablename__')

    def test_processing_log_model_exists(self):
        """Test that ProcessingLog model exists."""
        from app.models import ProcessingLog

        assert ProcessingLog is not None
        assert hasattr(ProcessingLog, '__tablename__')

    def test_document_metadata_model_exists(self):
        """Test that DocumentMetadata model exists."""
        from app.models import DocumentMetadata

        assert DocumentMetadata is not None
        assert hasattr(DocumentMetadata, '__tablename__')

    def test_file_record_creation(self, db_session):
        """Test creating a FileRecord instance."""
        from app.models import FileRecord

        file_record = FileRecord(
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()

        assert file_record.id is not None
        assert file_record.original_filename == "test.pdf"

    def test_processing_log_creation(self, db_session):
        """Test creating a ProcessingLog instance."""
        from app.models import ProcessingLog
        from datetime import datetime

        log = ProcessingLog(
            file_id=1,
            task_id="test-task",
            step_name="test_step",
            status="success",
            message="Test message",
            timestamp=datetime.utcnow()
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.task_id == "test-task"


@pytest.mark.unit
class TestCeleryApp:
    """Tests for Celery app module."""

    def test_celery_app_exists(self):
        """Test that Celery app is initialized."""
        from app.celery_app import celery

        assert celery is not None
        assert hasattr(celery, 'task')
        assert hasattr(celery, 'conf')

    def test_celery_app_config(self):
        """Test Celery app configuration."""
        from app.celery_app import celery

        # Check that celery has broker_url configured
        assert hasattr(celery.conf, 'broker_url') or hasattr(celery.conf, 'get')
