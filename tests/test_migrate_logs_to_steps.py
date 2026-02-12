"""
Tests for app/utils/migrate_logs_to_steps.py module.

Covers migrate_logs_to_steps, _parse_logs_to_step_states, migrate_all_files,
and verify_migration with comprehensive unit tests.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import FileProcessingStep, ProcessingLog
from app.utils.migrate_logs_to_steps import (
    _parse_logs_to_step_states,
    migrate_all_files,
    migrate_logs_to_steps,
    verify_migration,
)


def _make_log(file_id, step_name, status, message=None, timestamp=None):
    """Helper to create a mock ProcessingLog."""
    log = MagicMock(spec=ProcessingLog)
    log.file_id = file_id
    log.step_name = step_name
    log.status = status
    log.message = message
    log.timestamp = timestamp or datetime.now(timezone.utc)
    return log


def _make_step(file_id, step_name, status, started_at=None, completed_at=None, error_message=None):
    """Helper to create a mock FileProcessingStep."""
    step = MagicMock(spec=FileProcessingStep)
    step.file_id = file_id
    step.step_name = step_name
    step.status = status
    step.started_at = started_at
    step.completed_at = completed_at
    step.error_message = error_message
    return step


@pytest.mark.unit
class TestParseLogsToStepStates:
    """Tests for _parse_logs_to_step_states function."""

    def test_empty_logs(self):
        """Test parsing empty log list returns empty dict."""
        result = _parse_logs_to_step_states([])
        assert result == {}

    def test_single_in_progress_log(self):
        """Test parsing a single in_progress log entry."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        logs = [_make_log(1, "hash_file", "in_progress", timestamp=ts)]

        result = _parse_logs_to_step_states(logs)

        assert "hash_file" in result
        assert result["hash_file"]["status"] == "in_progress"
        assert result["hash_file"]["started_at"] == ts
        assert result["hash_file"]["completed_at"] is None

    def test_in_progress_then_success(self):
        """Test step that starts and completes successfully."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        logs = [
            _make_log(1, "hash_file", "in_progress", timestamp=ts1),
            _make_log(1, "hash_file", "success", timestamp=ts2),
        ]

        result = _parse_logs_to_step_states(logs)

        assert result["hash_file"]["status"] == "success"
        assert result["hash_file"]["started_at"] == ts1
        assert result["hash_file"]["completed_at"] == ts2
        assert result["hash_file"]["error_message"] is None

    def test_in_progress_then_failure(self):
        """Test step that starts and fails."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        logs = [
            _make_log(1, "ocr", "in_progress", timestamp=ts1),
            _make_log(1, "ocr", "failure", message="OCR failed", timestamp=ts2),
        ]

        result = _parse_logs_to_step_states(logs)

        assert result["ocr"]["status"] == "failure"
        assert result["ocr"]["started_at"] == ts1
        assert result["ocr"]["completed_at"] == ts2
        assert result["ocr"]["error_message"] == "OCR failed"

    def test_success_without_in_progress(self):
        """Test step that goes directly to success without in_progress."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        logs = [_make_log(1, "hash_file", "success", timestamp=ts)]

        result = _parse_logs_to_step_states(logs)

        assert result["hash_file"]["status"] == "success"
        assert result["hash_file"]["started_at"] == ts
        assert result["hash_file"]["completed_at"] == ts

    def test_failure_without_in_progress(self):
        """Test step that goes directly to failure without in_progress."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        logs = [_make_log(1, "upload", "failure", message="Connection error", timestamp=ts)]

        result = _parse_logs_to_step_states(logs)

        assert result["upload"]["status"] == "failure"
        assert result["upload"]["started_at"] == ts
        assert result["upload"]["error_message"] == "Connection error"

    def test_pending_status(self):
        """Test step with pending status."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        logs = [_make_log(1, "upload", "pending", timestamp=ts)]

        result = _parse_logs_to_step_states(logs)

        assert result["upload"]["status"] == "pending"
        assert result["upload"]["started_at"] is None

    def test_queued_status(self):
        """Test step with queued status."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        logs = [_make_log(1, "upload", "queued", timestamp=ts)]

        result = _parse_logs_to_step_states(logs)

        assert result["upload"]["status"] == "pending"

    def test_multiple_steps(self):
        """Test parsing logs for multiple steps."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
        ts4 = datetime(2024, 1, 1, 12, 0, 15, tzinfo=timezone.utc)
        logs = [
            _make_log(1, "hash_file", "in_progress", timestamp=ts1),
            _make_log(1, "hash_file", "success", timestamp=ts2),
            _make_log(1, "ocr", "in_progress", timestamp=ts3),
            _make_log(1, "ocr", "success", timestamp=ts4),
        ]

        result = _parse_logs_to_step_states(logs)

        assert len(result) == 2
        assert result["hash_file"]["status"] == "success"
        assert result["ocr"]["status"] == "success"

    def test_retry_overwrites_previous_state(self):
        """Test that later success after failure wins (retry scenario)."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        ts3 = datetime(2024, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
        ts4 = datetime(2024, 1, 1, 12, 0, 15, tzinfo=timezone.utc)
        logs = [
            _make_log(1, "upload", "in_progress", timestamp=ts1),
            _make_log(1, "upload", "failure", message="timeout", timestamp=ts2),
            _make_log(1, "upload", "in_progress", timestamp=ts3),
            _make_log(1, "upload", "success", timestamp=ts4),
        ]

        result = _parse_logs_to_step_states(logs)

        assert result["upload"]["status"] == "success"
        assert result["upload"]["error_message"] is None
        assert result["upload"]["completed_at"] == ts4

    def test_pending_does_not_override_in_progress(self):
        """Test that pending does not override in_progress status."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
        logs = [
            _make_log(1, "upload", "in_progress", timestamp=ts1),
            _make_log(1, "upload", "pending", timestamp=ts2),
        ]

        result = _parse_logs_to_step_states(logs)

        assert result["upload"]["status"] == "in_progress"


@pytest.mark.unit
class TestMigrateLogsToSteps:
    """Tests for migrate_logs_to_steps function."""

    def test_no_logs_found(self, db_session):
        """Test migration when no logs exist for the file."""
        result = migrate_logs_to_steps(db_session, file_id=999)

        assert result["file_id"] == 999
        assert result["steps_created"] == 0
        assert result["steps_updated"] == 0
        assert result["steps_skipped"] == 0
        assert result["errors"] == []

    def test_creates_new_steps(self, db_session):
        """Test migration creates FileProcessingStep entries from logs."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        # Add processing logs
        log1 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="in_progress", timestamp=ts1)
        log2 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts2)
        db_session.add_all([log1, log2])
        db_session.commit()

        result = migrate_logs_to_steps(db_session, file_id=1)

        assert result["steps_created"] == 1
        assert result["steps_updated"] == 0
        assert result["errors"] == []

        # Verify step was actually created
        steps = db_session.query(FileProcessingStep).filter(FileProcessingStep.file_id == 1).all()
        assert len(steps) == 1
        assert steps[0].step_name == "hash_file"
        assert steps[0].status == "success"

    def test_updates_existing_step(self, db_session):
        """Test migration updates existing step when status differs."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        # Add a log with success
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts2)
        db_session.add(log)

        # Add existing step with different status
        existing = FileProcessingStep(file_id=1, step_name="hash_file", status="in_progress", started_at=ts1)
        db_session.add(existing)
        db_session.commit()

        result = migrate_logs_to_steps(db_session, file_id=1)

        assert result["steps_updated"] == 1
        assert result["steps_created"] == 0

    def test_skips_unchanged_step(self, db_session):
        """Test migration skips step that is already up to date."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        # Add logs
        log1 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="in_progress", timestamp=ts1)
        log2 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts2)
        db_session.add_all([log1, log2])

        # Add existing step with the same values
        existing = FileProcessingStep(
            file_id=1, step_name="hash_file", status="success", started_at=ts1, completed_at=ts2
        )
        db_session.add(existing)
        db_session.commit()

        result = migrate_logs_to_steps(db_session, file_id=1)

        assert result["steps_skipped"] == 1
        assert result["steps_created"] == 0
        assert result["steps_updated"] == 0

    def test_dry_run_does_not_commit(self, db_session):
        """Test that dry_run mode does not persist changes."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)
        db_session.commit()

        result = migrate_logs_to_steps(db_session, file_id=1, dry_run=True)

        assert result["steps_created"] == 1

        # After dry run + rollback, no steps should be persisted
        steps = db_session.query(FileProcessingStep).filter(FileProcessingStep.file_id == 1).all()
        assert len(steps) == 0

    def test_handles_exception_gracefully(self, db_session):
        """Test that exceptions are caught and reported."""
        with patch.object(db_session, "query", side_effect=Exception("DB error")):
            result = migrate_logs_to_steps(db_session, file_id=1)

        assert "DB error" in result["errors"][0]
        assert result["steps_created"] == 0


@pytest.mark.unit
class TestMigrateAllFiles:
    """Tests for migrate_all_files function."""

    def test_no_files_to_migrate(self, db_session):
        """Test with no files needing migration."""
        result = migrate_all_files(db_session)

        assert result["total_files"] == 0
        assert result["files_migrated"] == 0
        assert result["files_failed"] == 0

    def test_migrates_files_with_logs_but_no_steps(self, db_session):
        """Test migrating files that have logs but no steps."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        # Add logs for file 1
        log1 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="in_progress", timestamp=ts1)
        log2 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts2)
        db_session.add_all([log1, log2])
        db_session.commit()

        result = migrate_all_files(db_session)

        assert result["total_files"] == 1
        assert result["files_migrated"] == 1
        assert result["total_steps_created"] == 1

    def test_skips_files_already_with_steps(self, db_session):
        """Test that files with existing steps are skipped."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Add log and step for file 1
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        step = FileProcessingStep(file_id=1, step_name="hash_file", status="success")
        db_session.add_all([log, step])
        db_session.commit()

        result = migrate_all_files(db_session)

        assert result["total_files"] == 0

    def test_handles_file_with_none_file_id(self, db_session):
        """Test that logs with None file_id are excluded."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        log = ProcessingLog(file_id=None, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)
        db_session.commit()

        result = migrate_all_files(db_session)

        assert result["total_files"] == 0

    def test_batch_processing(self, db_session):
        """Test batch processing with small batch size."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        for i in range(3):
            log = ProcessingLog(file_id=i + 10, task_id=f"t{i}", step_name="hash_file", status="success", timestamp=ts)
            db_session.add(log)
        db_session.commit()

        result = migrate_all_files(db_session, batch_size=2)

        assert result["total_files"] == 3
        assert result["files_migrated"] == 3

    def test_tracks_failed_files(self, db_session):
        """Test that migration errors for individual files are tracked."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)
        db_session.commit()

        with patch(
            "app.utils.migrate_logs_to_steps.migrate_logs_to_steps",
            return_value={"errors": ["forced error"], "steps_created": 0, "steps_updated": 0, "steps_skipped": 0},
        ):
            result = migrate_all_files(db_session)

        assert result["files_failed"] == 1
        assert "forced error" in result["errors"]

    def test_dry_run(self, db_session):
        """Test that dry_run is propagated."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)
        db_session.commit()

        result = migrate_all_files(db_session, dry_run=True)

        # File still processed, but changes not committed
        assert result["total_files"] == 1


@pytest.mark.unit
class TestVerifyMigration:
    """Tests for verify_migration function."""

    def test_no_logs_found(self, db_session):
        """Test verification when no logs exist."""
        result = verify_migration(db_session, file_id=999)

        assert result["is_valid"] is False
        assert "No logs found" in result["discrepancies"][0]

    def test_valid_migration(self, db_session):
        """Test verification passes when migration is correct."""
        ts1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        # Add logs
        log1 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="in_progress", timestamp=ts1)
        log2 = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts2)
        db_session.add_all([log1, log2])

        # Add matching step
        step = FileProcessingStep(file_id=1, step_name="hash_file", status="success", started_at=ts1, completed_at=ts2)
        db_session.add(step)
        db_session.commit()

        result = verify_migration(db_session, file_id=1)

        assert result["is_valid"] is True
        assert result["discrepancies"] == []
        assert "hash_file" in result["log_steps"]
        assert "hash_file" in result["table_steps"]

    def test_missing_step_in_table(self, db_session):
        """Test verification detects missing steps."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)
        db_session.commit()

        result = verify_migration(db_session, file_id=1)

        assert result["is_valid"] is False
        assert any("missing from table" in d for d in result["discrepancies"])

    def test_status_mismatch(self, db_session):
        """Test verification detects status mismatches."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)

        step = FileProcessingStep(file_id=1, step_name="hash_file", status="failure")
        db_session.add(step)
        db_session.commit()

        result = verify_migration(db_session, file_id=1)

        assert result["is_valid"] is False
        assert any("status mismatch" in d for d in result["discrepancies"])

    def test_extra_step_in_table(self, db_session):
        """Test that extra steps in table are noted but don't invalidate."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        log = ProcessingLog(file_id=1, task_id="t1", step_name="hash_file", status="success", timestamp=ts)
        db_session.add(log)

        # Add matching step + an extra one
        step1 = FileProcessingStep(file_id=1, step_name="hash_file", status="success")
        step2 = FileProcessingStep(file_id=1, step_name="extra_step", status="success")
        db_session.add_all([step1, step2])
        db_session.commit()

        result = verify_migration(db_session, file_id=1)

        assert any("Extra step" in d for d in result["discrepancies"])
        # Extra steps don't mark as invalid
        assert result["is_valid"] is True
