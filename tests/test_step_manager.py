"""
Tests for the FileProcessingStep model and step_manager utilities.

This test module verifies the new explicit status tracking approach.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import FileProcessingStep, FileRecord
from app.utils.step_manager import (
    MAIN_PROCESSING_STEPS,
    add_upload_steps,
    get_file_overall_status,
    get_file_step_status,
    get_step_summary,
    initialize_file_steps,
    update_step_status,
)


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


@pytest.mark.unit
class TestFileProcessingStepModel:
    """Test the FileProcessingStep model."""

    def test_create_step(self, db_session: Session):
        """Test creating a processing step."""
        # Create a file record first
        file_record = FileRecord(
            filehash="test123", original_filename="test.pdf", local_filename="/tmp/test.pdf", file_size=1024
        )
        db_session.add(file_record)
        db_session.commit()

        # Create a processing step
        step = FileProcessingStep(file_id=file_record.id, step_name="hash_file", status="success")
        db_session.add(step)
        db_session.commit()

        assert step.id is not None
        assert step.file_id == file_record.id
        assert step.step_name == "hash_file"
        assert step.status == "success"

    def test_unique_constraint(self, db_session: Session):
        """Test that the unique constraint on (file_id, step_name) works."""
        # Create a file record
        file_record = FileRecord(
            filehash="test456", original_filename="test2.pdf", local_filename="/tmp/test2.pdf", file_size=2048
        )
        db_session.add(file_record)
        db_session.commit()

        # Create first step
        step1 = FileProcessingStep(file_id=file_record.id, step_name="hash_file", status="in_progress")
        db_session.add(step1)
        db_session.commit()

        # Try to create duplicate step - should fail
        step2 = FileProcessingStep(file_id=file_record.id, step_name="hash_file", status="success")
        db_session.add(step2)

        with pytest.raises(Exception):  # SQLAlchemy will raise an integrity error
            db_session.commit()


@pytest.mark.unit
class TestStepManager:
    """Test step_manager utility functions."""

    def test_initialize_file_steps(self, db_session: Session):
        """Test initializing processing steps for a file."""
        # Create a file record
        file_record = FileRecord(
            filehash="test789", original_filename="test3.pdf", local_filename="/tmp/test3.pdf", file_size=4096
        )
        db_session.add(file_record)
        db_session.commit()

        # Initialize steps
        initialize_file_steps(db_session, file_record.id)

        # Verify steps were created
        steps = db_session.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_record.id).all()

        assert len(steps) == len(MAIN_PROCESSING_STEPS)
        for step in steps:
            assert step.status == "pending"
            assert step.step_name in MAIN_PROCESSING_STEPS

    def test_add_upload_steps(self, db_session: Session):
        """Test adding upload destination steps."""
        # Create a file record
        file_record = FileRecord(
            filehash="test101112", original_filename="test4.pdf", local_filename="/tmp/test4.pdf", file_size=8192
        )
        db_session.add(file_record)
        db_session.commit()

        # Add upload steps
        destinations = ["dropbox", "s3", "nextcloud"]
        add_upload_steps(db_session, file_record.id, destinations)

        # Verify upload steps were created
        steps = db_session.query(FileProcessingStep).filter(FileProcessingStep.file_id == file_record.id).all()

        # Should have 2 steps per destination (queue_ and upload_to_)
        assert len(steps) == len(destinations) * 2

        expected_steps = []
        for dest in destinations:
            expected_steps.append(f"queue_{dest}")
            expected_steps.append(f"upload_to_{dest}")

        for step in steps:
            assert step.step_name in expected_steps
            assert step.status == "pending"

    def test_update_step_status_new_step(self, db_session: Session):
        """Test updating status creates step if it doesn't exist."""
        # Create a file record
        file_record = FileRecord(
            filehash="test131415", original_filename="test5.pdf", local_filename="/tmp/test5.pdf", file_size=16384
        )
        db_session.add(file_record)
        db_session.commit()

        # Update a step that doesn't exist yet
        now = datetime.now()
        update_step_status(db_session, file_record.id, "hash_file", "in_progress", started_at=now)

        # Verify step was created
        step = (
            db_session.query(FileProcessingStep)
            .filter(FileProcessingStep.file_id == file_record.id, FileProcessingStep.step_name == "hash_file")
            .first()
        )

        assert step is not None
        assert step.status == "in_progress"
        assert step.started_at == now

    def test_update_step_status_existing_step(self, db_session: Session):
        """Test updating status of existing step."""
        # Create a file record and initialize steps
        file_record = FileRecord(
            filehash="test161718", original_filename="test6.pdf", local_filename="/tmp/test6.pdf", file_size=32768
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Update an existing step
        now = datetime.now()
        update_step_status(
            db_session, file_record.id, "hash_file", "success", started_at=now - timedelta(seconds=5), completed_at=now
        )

        # Verify step was updated
        step = (
            db_session.query(FileProcessingStep)
            .filter(FileProcessingStep.file_id == file_record.id, FileProcessingStep.step_name == "hash_file")
            .first()
        )

        assert step.status == "success"
        assert step.started_at == now - timedelta(seconds=5)
        assert step.completed_at == now

    def test_get_file_step_status(self, db_session: Session):
        """Test retrieving all step statuses for a file."""
        # Create a file record and initialize steps
        file_record = FileRecord(
            filehash="test192021", original_filename="test7.pdf", local_filename="/tmp/test7.pdf", file_size=65536
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Update some steps
        now = datetime.now()
        update_step_status(db_session, file_record.id, "hash_file", "success", completed_at=now)
        update_step_status(db_session, file_record.id, "create_file_record", "in_progress", started_at=now)
        update_step_status(db_session, file_record.id, "check_text", "failure", error_message="Failed to check text")

        # Get all step statuses
        status_map = get_file_step_status(db_session, file_record.id)

        assert len(status_map) == len(MAIN_PROCESSING_STEPS)
        assert status_map["hash_file"]["status"] == "success"
        assert status_map["hash_file"]["completed_at"] == now
        assert status_map["create_file_record"]["status"] == "in_progress"
        assert status_map["check_text"]["status"] == "failure"
        assert status_map["check_text"]["error_message"] == "Failed to check text"

    def test_get_file_overall_status_pending(self, db_session: Session):
        """Test overall status for a file with pending steps."""
        file_record = FileRecord(
            filehash="test222324", original_filename="test8.pdf", local_filename="/tmp/test8.pdf", file_size=131072
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        status = get_file_overall_status(db_session, file_record.id)

        assert status["status"] == "pending"
        assert status["has_errors"] is False
        assert status["total_steps"] == len(MAIN_PROCESSING_STEPS)
        assert status["completed_steps"] == 0
        assert status["in_progress_steps"] == 0

    def test_get_file_overall_status_processing(self, db_session: Session):
        """Test overall status for a file with in-progress steps."""
        file_record = FileRecord(
            filehash="test252627", original_filename="test9.pdf", local_filename="/tmp/test9.pdf", file_size=262144
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark some steps as complete and one as in progress
        update_step_status(db_session, file_record.id, "hash_file", "success")
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "in_progress")

        status = get_file_overall_status(db_session, file_record.id)

        assert status["status"] == "processing"
        assert status["has_errors"] is False
        assert status["completed_steps"] == 2
        assert status["in_progress_steps"] == 1

    def test_get_file_overall_status_completed(self, db_session: Session):
        """Test overall status for a completed file."""
        file_record = FileRecord(
            filehash="test282930", original_filename="test10.pdf", local_filename="/tmp/test10.pdf", file_size=524288
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark all steps as success
        for step_name in MAIN_PROCESSING_STEPS:
            update_step_status(db_session, file_record.id, step_name, "success")

        status = get_file_overall_status(db_session, file_record.id)

        assert status["status"] == "completed"
        assert status["has_errors"] is False
        assert status["completed_steps"] == len(MAIN_PROCESSING_STEPS)
        assert status["in_progress_steps"] == 0

    def test_get_file_overall_status_failed(self, db_session: Session):
        """Test overall status for a file with failed steps."""
        file_record = FileRecord(
            filehash="test313233", original_filename="test11.pdf", local_filename="/tmp/test11.pdf", file_size=1048576
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark some steps as success and one as failure
        update_step_status(db_session, file_record.id, "hash_file", "success")
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "failure", error_message="OCR failed")

        status = get_file_overall_status(db_session, file_record.id)

        assert status["status"] == "failed"
        assert status["has_errors"] is True
        assert status["failed_steps"] == 1

    def test_get_step_summary(self, db_session: Session):
        """Test getting step summary with counts."""
        file_record = FileRecord(
            filehash="test343536", original_filename="test12.pdf", local_filename="/tmp/test12.pdf", file_size=2097152
        )
        db_session.add(file_record)
        db_session.commit()

        # Initialize main steps and add upload steps
        initialize_file_steps(db_session, file_record.id)
        add_upload_steps(db_session, file_record.id, ["dropbox", "s3", "nextcloud"])

        # Update statuses
        update_step_status(db_session, file_record.id, "hash_file", "success")
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "in_progress")
        update_step_status(db_session, file_record.id, "upload_to_dropbox", "success")
        update_step_status(db_session, file_record.id, "upload_to_s3", "failure")
        update_step_status(db_session, file_record.id, "queue_nextcloud", "in_progress")

        summary = get_step_summary(db_session, file_record.id)

        # Check main step counts
        assert summary["main"]["success"] == 2
        assert summary["main"]["in_progress"] == 1
        assert summary["main"]["queued"] >= 5  # Remaining pending steps

        # Check upload counts
        assert summary["uploads"]["success"] == 1
        assert summary["uploads"]["failure"] == 1
        assert summary["uploads"]["in_progress"] == 1

        assert summary["total_main_steps"] == len(MAIN_PROCESSING_STEPS)
        assert summary["total_upload_tasks"] == 6  # 3 destinations x 2 steps each
