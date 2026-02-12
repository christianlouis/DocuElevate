"""
Tests for file status and metrics calculation using FileProcessingStep model.

This test module verifies that:
1. Status calculation uses FileProcessingStep entries correctly
2. Metrics counting uses FileProcessingStep entries correctly
3. Files with completed steps show "completed" not "processing"
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FileProcessingStep, FileRecord
from app.utils.step_manager import get_file_overall_status, get_step_summary, initialize_file_steps, update_step_status


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
class TestFileStatusCalculation:
    """Test file status calculation using FileProcessingStep."""

    def test_status_completed_when_all_steps_success(self, db_session):
        """
        Test that status shows "completed" when all steps are success.
        """
        # Create file and initialize steps
        file_record = FileRecord(
            filehash="test1", original_filename="test.pdf", local_filename="/tmp/test.pdf", file_size=1024
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark all steps as success
        from app.utils.step_manager import MAIN_PROCESSING_STEPS

        for step_name in MAIN_PROCESSING_STEPS:
            update_step_status(db_session, file_record.id, step_name, "success")

        result = get_file_overall_status(db_session, file_record.id)

        assert result["status"] == "completed"
        assert result["has_errors"] is False

    def test_status_processing_when_steps_in_progress(self, db_session):
        """
        Test that status shows "processing" when there are in_progress steps.
        """
        file_record = FileRecord(
            filehash="test2", original_filename="test2.pdf", local_filename="/tmp/test2.pdf", file_size=2048
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark some steps as success, one as in_progress
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "in_progress")

        result = get_file_overall_status(db_session, file_record.id)

        assert result["status"] == "processing"
        assert result["has_errors"] is False

    def test_status_failed_when_steps_have_failure(self, db_session):
        """
        Test that status shows "failed" when any step has failure status.
        """
        file_record = FileRecord(
            filehash="test3", original_filename="test3.pdf", local_filename="/tmp/test3.pdf", file_size=3072
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark some steps as success, one as failure
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "success")
        update_step_status(db_session, file_record.id, "extract_text", "failure", error_message="OCR failed")

        result = get_file_overall_status(db_session, file_record.id)

        assert result["status"] == "failed"
        assert result["has_errors"] is True


@pytest.mark.unit
class TestMetricsCounting:
    """Test metrics counting using FileProcessingStep."""

    def test_main_steps_counted_correctly(self, db_session):
        """
        Test that main processing steps are counted correctly.
        """
        file_record = FileRecord(
            filehash="test4", original_filename="test4.pdf", local_filename="/tmp/test4.pdf", file_size=4096
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)

        # Mark some steps with different statuses
        update_step_status(db_session, file_record.id, "create_file_record", "success")
        update_step_status(db_session, file_record.id, "check_text", "success")
        update_step_status(db_session, file_record.id, "extract_text", "in_progress")

        summary = get_step_summary(db_session, file_record.id)

        # Should count each step once
        from app.utils.step_manager import MAIN_PROCESSING_STEPS

        assert summary["total_main_steps"] == len(MAIN_PROCESSING_STEPS)
        assert summary["main"]["success"] == 2
        assert summary["main"]["in_progress"] == 1

    def test_upload_tasks_counted_correctly(self, db_session):
        """
        Test that upload tasks are counted correctly.
        """
        file_record = FileRecord(
            filehash="test5", original_filename="test5.pdf", local_filename="/tmp/test5.pdf", file_size=5120
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)
        from app.utils.step_manager import add_upload_steps

        add_upload_steps(db_session, file_record.id, ["dropbox", "s3", "nextcloud"])

        # Mark upload steps with different statuses
        update_step_status(db_session, file_record.id, "upload_to_dropbox", "success")
        update_step_status(db_session, file_record.id, "upload_to_s3", "failure")
        update_step_status(db_session, file_record.id, "upload_to_nextcloud", "in_progress")

        summary = get_step_summary(db_session, file_record.id)

        # Should count only upload_to_* steps (not queue_* steps)
        assert summary["total_upload_tasks"] == 3
        assert summary["uploads"]["success"] == 1
        assert summary["uploads"]["failure"] == 1
        assert summary["uploads"]["in_progress"] == 1

    def test_accurate_metrics_for_completed_file(self, db_session):
        """
        Test metrics for a file with multiple successful uploads.
        """
        file_record = FileRecord(
            filehash="test6", original_filename="test6.pdf", local_filename="/tmp/test6.pdf", file_size=6144
        )
        db_session.add(file_record)
        db_session.commit()

        initialize_file_steps(db_session, file_record.id)
        from app.utils.step_manager import add_upload_steps

        services = ["dropbox", "s3", "nextcloud", "google_drive", "onedrive", "webdav"]
        add_upload_steps(db_session, file_record.id, services)

        # Mark all uploads as success
        for service in services:
            update_step_status(db_session, file_record.id, f"upload_to_{service}", "success")

        summary = get_step_summary(db_session, file_record.id)

        # Should have 6 upload_to_* tasks
        assert summary["total_upload_tasks"] == 6
        assert summary["uploads"]["success"] == 6
        assert summary["uploads"]["failure"] == 0
        assert summary["uploads"]["in_progress"] == 0
