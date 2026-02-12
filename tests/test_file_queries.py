"""
Tests for file query utilities.

This module tests the shared file status filtering logic in app/utils/file_queries.py.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FileProcessingStep, FileRecord
from app.utils.file_queries import apply_status_filter


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def sample_files(db_session):
    """Create sample files with different processing statuses."""
    # File 1: pending (no steps)
    file1 = FileRecord(
        filehash="hash1",
        original_filename="pending.pdf",
        local_filename="/tmp/pending.pdf",
        file_size=1024,
        mime_type="application/pdf",
    )
    db_session.add(file1)
    db_session.flush()

    # File 2: processing (has in_progress step)
    file2 = FileRecord(
        filehash="hash2",
        original_filename="processing.pdf",
        local_filename="/tmp/processing.pdf",
        file_size=2048,
        mime_type="application/pdf",
    )
    db_session.add(file2)
    db_session.flush()

    step2 = FileProcessingStep(
        file_id=file2.id,
        step_name="extract_text",
        status="in_progress",
    )
    db_session.add(step2)

    # File 3: failed (has failure step)
    file3 = FileRecord(
        filehash="hash3",
        original_filename="failed.pdf",
        local_filename="/tmp/failed.pdf",
        file_size=3072,
        mime_type="application/pdf",
    )
    db_session.add(file3)
    db_session.flush()

    step3 = FileProcessingStep(
        file_id=file3.id,
        step_name="extract_text",
        status="failure",
        error_message="Error occurred",
    )
    db_session.add(step3)

    # File 4: completed (has success step, no failures)
    file4 = FileRecord(
        filehash="hash4",
        original_filename="completed.pdf",
        local_filename="/tmp/completed.pdf",
        file_size=4096,
        mime_type="application/pdf",
    )
    db_session.add(file4)
    db_session.flush()

    step4 = FileProcessingStep(file_id=file4.id, step_name="extract_text", status="success")
    db_session.add(step4)

    # File 5: completed with multiple success steps
    file5 = FileRecord(
        filehash="hash5",
        original_filename="completed2.pdf",
        local_filename="/tmp/completed2.pdf",
        file_size=5120,
        mime_type="application/pdf",
    )
    db_session.add(file5)
    db_session.flush()

    step5a = FileProcessingStep(
        file_id=file5.id,
        step_name="extract_text",
        status="success",
    )
    step5b = FileProcessingStep(
        file_id=file5.id,
        step_name="extract_metadata_with_gpt",
        status="success",
    )
    db_session.add_all([step5a, step5b])

    # File 6: has success but also failure (should be filtered out from completed)
    file6 = FileRecord(
        filehash="hash6",
        original_filename="mixed.pdf",
        local_filename="/tmp/mixed.pdf",
        file_size=6144,
        mime_type="application/pdf",
    )
    db_session.add(file6)
    db_session.flush()

    step6a = FileProcessingStep(
        file_id=file6.id,
        step_name="extract_text",
        status="success",
    )
    step6b = FileProcessingStep(
        file_id=file6.id,
        step_name="upload_to_s3",
        status="failure",
        error_message="Upload failed",
    )
    db_session.add_all([step6a, step6b])

    db_session.commit()

    return {
        "pending": file1,
        "processing": file2,
        "failed": file3,
        "completed": file4,
        "completed2": file5,
        "mixed": file6,
    }


@pytest.mark.unit
def test_apply_status_filter_none(db_session, sample_files):
    """Test that no filter is applied when status is None."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, None)
    results = filtered_query.all()

    # Should return all files
    assert len(results) == 6


@pytest.mark.unit
def test_apply_status_filter_pending(db_session, sample_files):
    """Test filtering for pending files (no steps)."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "pending")
    results = filtered_query.all()

    # Should return only file1 (no steps)
    assert len(results) == 1
    assert results[0].filehash == "hash1"
    assert results[0].original_filename == "pending.pdf"


@pytest.mark.unit
def test_apply_status_filter_processing(db_session, sample_files):
    """Test filtering for files in processing state."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "processing")
    results = filtered_query.all()

    # Should return only file2 (has in_progress step)
    assert len(results) == 1
    assert results[0].filehash == "hash2"
    assert results[0].original_filename == "processing.pdf"


@pytest.mark.unit
def test_apply_status_filter_failed(db_session, sample_files):
    """Test filtering for failed files."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "failed")
    results = filtered_query.all()

    # Should return file3 and file6 (both have failure steps)
    assert len(results) == 2
    filehashes = {r.filehash for r in results}
    assert "hash3" in filehashes
    assert "hash6" in filehashes


@pytest.mark.unit
def test_apply_status_filter_completed(db_session, sample_files):
    """Test filtering for completed files (success with no failures)."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "completed")
    results = filtered_query.all()

    # Should return file4 and file5 (success steps, no failures)
    # file6 should NOT be included (has both success and failure)
    assert len(results) == 2
    filehashes = {r.filehash for r in results}
    assert "hash4" in filehashes
    assert "hash5" in filehashes
    assert "hash6" not in filehashes  # mixed status should be excluded


@pytest.mark.unit
def test_apply_status_filter_empty_string(db_session, sample_files):
    """Test that empty string status is treated like None (no filter)."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "")
    results = filtered_query.all()

    # Should return all files
    assert len(results) == 6


@pytest.mark.unit
def test_apply_status_filter_invalid_status(db_session, sample_files):
    """Test that invalid status values don't crash, just return unfiltered."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "invalid_status")
    results = filtered_query.all()

    # Should return all files (no filter applied for unknown status)
    assert len(results) == 6


@pytest.mark.unit
def test_apply_status_filter_with_other_filters(db_session, sample_files):
    """Test that status filter can be combined with other query filters."""
    # Filter for completed PDFs
    query = db_session.query(FileRecord).filter(FileRecord.mime_type == "application/pdf")
    filtered_query = apply_status_filter(query, db_session, "completed")
    results = filtered_query.all()

    # Should return file4 and file5 (both are completed PDFs)
    assert len(results) == 2
    filehashes = {r.filehash for r in results}
    assert "hash4" in filehashes
    assert "hash5" in filehashes


@pytest.mark.unit
def test_apply_status_filter_empty_database(db_session):
    """Test filtering on empty database doesn't crash."""
    query = db_session.query(FileRecord)
    filtered_query = apply_status_filter(query, db_session, "completed")
    results = filtered_query.all()

    # Should return empty list
    assert len(results) == 0


@pytest.mark.unit
def test_apply_status_filter_preserves_query_order(db_session, sample_files):
    """Test that status filter preserves existing query ordering."""
    from sqlalchemy import desc

    # Query with ordering
    query = db_session.query(FileRecord).order_by(desc(FileRecord.file_size))
    filtered_query = apply_status_filter(query, db_session, "completed")
    results = filtered_query.all()

    # Should return file5 before file4 (larger file size)
    assert len(results) == 2
    assert results[0].file_size > results[1].file_size
    assert results[0].filehash == "hash5"
    assert results[1].filehash == "hash4"
