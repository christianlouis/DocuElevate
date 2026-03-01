"""
Tests for database performance indexes and schema migrations.
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.database import Base, _ensure_indexes


@pytest.fixture
def engine_with_tables():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import models to register them with Base
    from app.models import (  # noqa: F401
        ApplicationSettings,
        FileProcessingStep,
        FileRecord,
        ProcessingLog,
    )

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.mark.unit
def test_ensure_indexes_creates_expected_indexes(engine_with_tables):
    """_ensure_indexes should create all performance indexes."""
    engine = engine_with_tables
    inspector = inspect(engine)

    # Run the migration
    _ensure_indexes(engine, inspector)

    # Refresh inspector after DDL
    inspector = inspect(engine)

    expected = {
        "files": {"ix_files_created_at", "ix_files_mime_type"},
        "processing_logs": {"ix_processing_logs_file_id", "ix_processing_logs_timestamp"},
        "file_processing_steps": {"ix_file_processing_steps_status"},
    }

    for table, idx_names in expected.items():
        actual_indexes = {idx["name"] for idx in inspector.get_indexes(table)}
        for name in idx_names:
            assert name in actual_indexes, f"Index {name} missing from {table}; found {actual_indexes}"


@pytest.mark.unit
def test_ensure_indexes_idempotent(engine_with_tables):
    """_ensure_indexes should be safe to run multiple times."""
    engine = engine_with_tables
    inspector = inspect(engine)

    _ensure_indexes(engine, inspector)
    # Running again should not raise
    inspector2 = inspect(engine)
    _ensure_indexes(engine, inspector2)


@pytest.mark.unit
def test_model_indexes_declared():
    """Verify key indexes are declared in SQLAlchemy model metadata."""
    from app.models import FileProcessingStep, FileRecord, ProcessingLog

    # FileRecord.created_at should be indexed
    assert FileRecord.__table__.c.created_at.index is True
    # FileRecord.mime_type should be indexed
    assert FileRecord.__table__.c.mime_type.index is True
    # ProcessingLog.file_id should be indexed
    assert ProcessingLog.__table__.c.file_id.index is True
    # ProcessingLog.timestamp should be indexed
    assert ProcessingLog.__table__.c.timestamp.index is True
    # FileProcessingStep.status should be indexed
    assert FileProcessingStep.__table__.c.status.index is True
