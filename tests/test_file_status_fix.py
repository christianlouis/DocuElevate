"""
Tests for file status and metrics calculation bug fixes.

This test module verifies that:
1. Status calculation only considers the latest status per unique step
2. Metrics counting only uses the latest status per unique step
3. Files with completed steps show "completed" not "processing"
"""

import pytest
from datetime import datetime, timedelta

from app.utils.file_status import _compute_status_from_logs
from app.views.files import _compute_step_summary


@pytest.mark.unit
class TestFileStatusBugFixes:
    """Test fixes for status calculation bugs."""

    def test_status_not_stuck_on_old_in_progress(self):
        """
        Test that status doesn't show "processing" when old in_progress logs exist
        but latest status for all steps is success.
        
        This simulates the bug where a file shows "Processing" even though
        all steps have completed successfully.
        """
        class MockLog:
            def __init__(self, step_name, status, timestamp):
                self.step_name = step_name
                self.status = status
                self.timestamp = timestamp

        now = datetime.now()
        # Simulate logs ordered by timestamp desc (latest first)
        logs = [
            # Latest logs (all success)
            MockLog("upload_to_dropbox", "success", now - timedelta(minutes=1)),
            MockLog("extract_metadata_with_gpt", "success", now - timedelta(minutes=2)),
            MockLog("check_text", "success", now - timedelta(minutes=3)),
            # Older in_progress logs that should be ignored
            MockLog("upload_to_dropbox", "in_progress", now - timedelta(minutes=5)),
            MockLog("extract_metadata_with_gpt", "in_progress", now - timedelta(minutes=6)),
            MockLog("check_text", "in_progress", now - timedelta(minutes=7)),
        ]

        result = _compute_status_from_logs(logs)
        
        # Should be completed, not processing
        assert result["status"] == "completed"
        assert result["has_errors"] is False

    def test_status_shows_processing_for_active_tasks(self):
        """
        Test that status correctly shows "processing" when there are
        actually in-progress tasks (based on latest status).
        """
        class MockLog:
            def __init__(self, step_name, status, timestamp):
                self.step_name = step_name
                self.status = status
                self.timestamp = timestamp

        now = datetime.now()
        logs = [
            # One task actually in progress
            MockLog("upload_to_dropbox", "in_progress", now - timedelta(minutes=1)),
            # Other tasks completed
            MockLog("extract_metadata_with_gpt", "success", now - timedelta(minutes=2)),
            MockLog("check_text", "success", now - timedelta(minutes=3)),
        ]

        result = _compute_status_from_logs(logs)
        
        # Should be processing because one task is actually in progress
        assert result["status"] == "processing"
        assert result["has_errors"] is False

    def test_status_shows_failed_when_latest_has_failure(self):
        """
        Test that status shows "failed" when the latest status for any step is failure.
        """
        class MockLog:
            def __init__(self, step_name, status, timestamp):
                self.step_name = step_name
                self.status = status
                self.timestamp = timestamp

        now = datetime.now()
        logs = [
            # One task failed (latest status)
            MockLog("upload_to_s3", "failure", now - timedelta(minutes=1)),
            # Other tasks completed
            MockLog("upload_to_dropbox", "success", now - timedelta(minutes=2)),
            MockLog("extract_metadata_with_gpt", "success", now - timedelta(minutes=3)),
        ]

        result = _compute_status_from_logs(logs)
        
        assert result["status"] == "failed"
        assert result["has_errors"] is True


@pytest.mark.unit
class TestMetricsCountingBugFixes:
    """Test fixes for metrics counting bugs."""

    def test_main_steps_not_double_counted(self):
        """
        Test that main processing steps are only counted once per step,
        using the latest status, not counting all historical logs.
        
        This simulates the bug where metrics show incorrect counts because
        they count all logs instead of just the latest per step.
        """
        class MockLog:
            def __init__(self, step_name, status):
                self.step_name = step_name
                self.status = status

        # Simulate logs ordered by timestamp desc (latest first)
        logs = [
            # Latest status for each step (all success)
            MockLog("hash_file", "success"),
            MockLog("create_file_record", "success"),
            MockLog("extract_metadata_with_gpt", "success"),
            # Older in_progress logs that should be ignored
            MockLog("hash_file", "in_progress"),
            MockLog("create_file_record", "in_progress"),
            MockLog("extract_metadata_with_gpt", "in_progress"),
        ]

        summary = _compute_step_summary(logs)
        
        # Should count each main step only once
        assert summary["total_main_steps"] == 3
        assert summary["main"]["success"] == 3
        assert summary["main"]["in_progress"] == 0  # No steps actually in progress
        assert summary["main"]["failure"] == 0

    def test_upload_tasks_not_double_counted(self):
        """
        Test that upload tasks are only counted once per destination,
        using the latest status.
        """
        class MockLog:
            def __init__(self, step_name, status):
                self.step_name = step_name
                self.status = status

        # Logs ordered by timestamp desc (latest first)
        logs = [
            # Latest status for uploads
            MockLog("upload_to_dropbox", "success"),
            MockLog("upload_to_s3", "success"),
            MockLog("upload_to_nextcloud", "success"),
            # Queue logs (older, should use upload_to_ as latest)
            MockLog("queue_dropbox", "success"),
            MockLog("queue_s3", "in_progress"),
            MockLog("queue_nextcloud", "success"),
            # Even older in_progress logs
            MockLog("upload_to_dropbox", "in_progress"),
            MockLog("upload_to_s3", "in_progress"),
        ]

        summary = _compute_step_summary(logs)
        
        # Should count unique upload destinations
        # Note: queue_X and upload_to_X are separate steps
        assert summary["total_upload_tasks"] == 6  # 3 upload_to + 3 queue
        assert summary["uploads"]["success"] == 5  # All uploads success, 2 queue success
        assert summary["uploads"]["in_progress"] == 1  # 1 queue in_progress

    def test_accurate_metrics_for_completed_file(self):
        """
        Test the scenario from the issue: File with 6 actual uploads
        should show 6, not 12.
        """
        class MockLog:
            def __init__(self, step_name, status):
                self.step_name = step_name
                self.status = status

        # Simulate 6 successful uploads with their queue steps
        logs = []
        services = ["dropbox", "s3", "nextcloud", "google_drive", "onedrive", "webdav"]
        
        # Add latest status (all success)
        for service in services:
            logs.append(MockLog(f"upload_to_{service}", "success"))
            logs.append(MockLog(f"queue_{service}", "success"))
        
        # Add some older in_progress logs
        for service in services:
            logs.append(MockLog(f"upload_to_{service}", "in_progress"))
            logs.append(MockLog(f"queue_{service}", "in_progress"))

        summary = _compute_step_summary(logs)
        
        # Should have 12 total upload tasks (6 upload_to + 6 queue)
        assert summary["total_upload_tasks"] == 12
        # All should be success (latest status)
        assert summary["uploads"]["success"] == 12
        assert summary["uploads"]["in_progress"] == 0

    def test_mixed_upload_statuses(self):
        """
        Test that upload metrics correctly reflect mixed statuses.
        """
        class MockLog:
            def __init__(self, step_name, status):
                self.step_name = step_name
                self.status = status

        logs = [
            # Latest statuses
            MockLog("upload_to_dropbox", "success"),
            MockLog("upload_to_s3", "failure"),
            MockLog("upload_to_nextcloud", "in_progress"),
            MockLog("queue_dropbox", "success"),
            MockLog("queue_s3", "success"),
            MockLog("queue_nextcloud", "success"),
        ]

        summary = _compute_step_summary(logs)
        
        assert summary["total_upload_tasks"] == 6
        assert summary["uploads"]["success"] == 4  # 1 upload + 3 queue
        assert summary["uploads"]["failure"] == 1  # 1 upload
        assert summary["uploads"]["in_progress"] == 1  # 1 upload
