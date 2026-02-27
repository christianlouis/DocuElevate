"""
Tests for file status and metrics calculation using FileProcessingStep model.

This test module verifies that:
1. Status calculation uses FileProcessingStep entries correctly
2. Metrics counting uses FileProcessingStep entries correctly
3. Files with completed steps show "completed" not "processing"
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import FileRecord
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


@pytest.mark.unit
class TestGetFilesProcessingStatusEdgeCases:
    """Test edge cases for get_files_processing_status."""

    def test_handles_empty_file_list(self, db_session):
        """Test with empty file list."""
        from app.utils.file_status import get_files_processing_status

        result = get_files_processing_status(db_session, [])
        assert result == {}

    def test_handles_nonexistent_file_ids(self, db_session):
        """Test with file IDs that don't exist."""
        from app.utils.file_status import get_files_processing_status

        result = get_files_processing_status(db_session, [99999, 99998])
        # Should return status for these IDs even if they don't exist
        assert 99999 in result
        assert result[99999]["status"] == "pending"

    def test_handles_mixed_file_states(self, db_session):
        """Test with files in different states."""
        from app.models import FileRecord
        from app.utils.file_status import get_files_processing_status
        from app.utils.step_manager import initialize_file_steps, update_step_status

        # Create multiple files with different states
        file1 = FileRecord(
            filehash="hash1",
            local_filename="/tmp/file1.pdf",
            original_filename="file1.pdf",
            file_size=1000,
            is_duplicate=False,
        )
        file2 = FileRecord(
            filehash="hash2",
            local_filename="/tmp/file2.pdf",
            original_filename="file2.pdf",
            file_size=2000,
            is_duplicate=True,
        )
        file3 = FileRecord(
            filehash="hash3",
            local_filename="/tmp/file3.pdf",
            original_filename="file3.pdf",
            file_size=3000,
            is_duplicate=False,
        )

        db_session.add_all([file1, file2, file3])
        db_session.commit()

        # Initialize steps for file1 and file3
        initialize_file_steps(db_session, file1.id)
        initialize_file_steps(db_session, file3.id)

        # Mark file1 as failed
        update_step_status(db_session, file1.id, "extract_text", "failure")

        # Mark file3 as in progress
        update_step_status(db_session, file3.id, "extract_text", "in_progress")

        result = get_files_processing_status(db_session, [file1.id, file2.id, file3.id])

        assert result[file1.id]["status"] == "failed"
        assert result[file2.id]["status"] == "duplicate"
        assert result[file3.id]["status"] == "processing"


@pytest.mark.unit
class TestComputeStatusFromLogsDeprecated:
    """Test the deprecated _compute_status_from_logs function."""

    def test_empty_logs_list(self):
        """Test with empty logs list."""
        from app.utils.file_status import _compute_status_from_logs

        result = _compute_status_from_logs([])
        assert result["status"] == "pending"
        assert result["last_step"] is None
        assert result["has_errors"] is False

    def test_logs_with_multiple_steps(self, db_session):
        """Test logs from multiple steps."""
        from app.models import ProcessingLog
        from app.utils.file_status import _compute_status_from_logs

        logs = [
            ProcessingLog(
                file_id=1, task_id="task1", step_name="step1", status="success", message="Done", timestamp=None
            ),
            ProcessingLog(
                file_id=1, task_id="task2", step_name="step2", status="in_progress", message="Running", timestamp=None
            ),
        ]

        result = _compute_status_from_logs(logs)
        assert result["status"] == "processing"
        assert result["last_step"] == "step1"  # First log in list


@pytest.mark.unit
class TestFileStatusMissingCoverage:
    """Tests for uncovered lines in file_status.py."""

    @pytest.fixture
    def db_session(self):
        """Create an in-memory SQLite database for testing."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()
        Base.metadata.drop_all(engine)

    def test_get_file_processing_status_duplicate(self, db_session):
        """Covers line 28: returns duplicate status for duplicate files."""
        from app.utils.file_status import get_file_processing_status

        file_record = FileRecord(
            filehash="dup1",
            original_filename="dup.pdf",
            local_filename="/tmp/dup.pdf",
            file_size=100,
            is_duplicate=True,
        )
        db_session.add(file_record)
        db_session.commit()

        result = get_file_processing_status(db_session, file_record.id)
        assert result["status"] == "duplicate"
        assert result["last_step"] == "check_for_duplicates"
        assert result["has_errors"] is False

    def test_get_files_processing_status_deduplication_enabled(self, db_session):
        """Covers line 105->109: check_for_duplicates step added when deduplication enabled."""
        from unittest.mock import patch

        from app.utils.file_status import get_files_processing_status

        file_record = FileRecord(
            filehash="dedup1",
            original_filename="dedup.pdf",
            local_filename="/tmp/dedup.pdf",
            file_size=100,
        )
        db_session.add(file_record)
        db_session.commit()

        with patch("app.config.settings") as ms:
            ms.enable_deduplication = True
            result = get_files_processing_status(db_session, [file_record.id])

        # File has no steps, so should be pending
        assert result[file_record.id]["status"] == "pending"

    def test_get_files_processing_status_pending_steps(self, db_session):
        """Covers line 154: some steps exist but not all are completed (pending status)."""
        from datetime import datetime

        from app.models import FileProcessingStep
        from app.utils.file_status import get_files_processing_status

        file_record = FileRecord(
            filehash="pend1",
            original_filename="pending.pdf",
            local_filename="/tmp/pending.pdf",
            file_size=100,
        )
        db_session.add(file_record)
        db_session.commit()

        # Add a step that is neither success nor failure nor in_progress
        step = FileProcessingStep(
            file_id=file_record.id,
            step_name="create_file_record",
            status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(step)
        db_session.commit()

        from unittest.mock import patch

        with patch("app.config.settings") as ms:
            ms.enable_deduplication = False
            result = get_files_processing_status(db_session, [file_record.id])

        assert result[file_record.id]["status"] == "pending"

    def test_compute_status_from_logs_failed(self):
        """Covers lines 203: status is 'failed' when there's a failure log."""
        from app.models import ProcessingLog
        from app.utils.file_status import _compute_status_from_logs

        logs = [
            ProcessingLog(
                file_id=1,
                task_id="t1",
                step_name="extract",
                status="failure",
                message="Error",
                timestamp=None,
            ),
        ]
        result = _compute_status_from_logs(logs)
        assert result["status"] == "failed"
        assert result["has_errors"] is True

    def test_compute_status_from_logs_completed(self):
        """Covers lines 206-207: status is 'completed' when latest log is success."""
        from app.models import ProcessingLog
        from app.utils.file_status import _compute_status_from_logs

        logs = [
            ProcessingLog(
                file_id=1,
                task_id="t1",
                step_name="finalize",
                status="success",
                message="Done",
                timestamp=None,
            ),
        ]
        result = _compute_status_from_logs(logs)
        assert result["status"] == "completed"
        assert result["has_errors"] is False

    def test_compute_status_from_logs_pending_non_success(self):
        """Covers lines 208-209: status is 'pending' when latest log is not success/failure/in_progress."""
        from app.models import ProcessingLog
        from app.utils.file_status import _compute_status_from_logs

        logs = [
            ProcessingLog(
                file_id=1,
                task_id="t1",
                step_name="upload",
                status="queued",
                message="Waiting",
                timestamp=None,
            ),
        ]
        result = _compute_status_from_logs(logs)
        assert result["status"] == "pending"
        assert result["has_errors"] is False

    def test_get_files_processing_status_with_completed_steps(self, db_session):
        """Covers completed + skipped == total_steps with terminal step → completed status."""
        from datetime import datetime
        from unittest.mock import patch

        from app.models import FileProcessingStep
        from app.utils.file_status import get_files_processing_status

        file_record = FileRecord(
            filehash="comp1",
            original_filename="comp.pdf",
            local_filename="/tmp/comp.pdf",
            file_size=100,
        )
        db_session.add(file_record)
        db_session.commit()

        now = datetime.utcnow()
        for step_name, step_status in [
            ("create_file_record", "success"),
            ("finalize_document_storage", "skipped"),
            ("send_to_all_destinations", "success"),
        ]:
            step = FileProcessingStep(
                file_id=file_record.id,
                step_name=step_name,
                status=step_status,
                created_at=now,
                updated_at=now,
            )
            db_session.add(step)
        db_session.commit()

        with patch("app.config.settings") as ms:
            ms.enable_deduplication = False
            result = get_files_processing_status(db_session, [file_record.id])

        assert result[file_record.id]["status"] == "completed"

    def test_get_files_processing_status_completed_with_pending_intermediate(self, db_session):
        """Test that terminal step success marks file completed even with pending intermediate steps.

        This tests the dynamic pipeline scenario where check_for_duplicates or
        extract_text might remain pending because the pipeline skipped them.
        """
        from datetime import datetime
        from unittest.mock import patch

        from app.models import FileProcessingStep
        from app.utils.file_status import get_files_processing_status

        file_record = FileRecord(
            filehash="terminal_fallback",
            original_filename="fallback.pdf",
            local_filename="/tmp/fallback.pdf",
            file_size=100,
        )
        db_session.add(file_record)
        db_session.commit()

        now = datetime.now()
        # Simulate: check_for_duplicates pending, rest succeeded, OCR skipped
        for step_name, step_status in [
            ("check_for_duplicates", "pending"),
            ("create_file_record", "success"),
            ("check_text", "success"),
            ("extract_text", "success"),
            ("process_with_ocr", "skipped"),
            ("extract_metadata_with_gpt", "success"),
            ("embed_metadata_into_pdf", "success"),
            ("finalize_document_storage", "success"),
            ("send_to_all_destinations", "success"),
        ]:
            step = FileProcessingStep(
                file_id=file_record.id,
                step_name=step_name,
                status=step_status,
                created_at=now,
                updated_at=now,
            )
            db_session.add(step)
        db_session.commit()

        with patch("app.config.settings") as ms:
            ms.enable_deduplication = True
            result = get_files_processing_status(db_session, [file_record.id])

        # Terminal step succeeded → file should be completed despite pending dedup step
        assert result[file_record.id]["status"] == "completed"
