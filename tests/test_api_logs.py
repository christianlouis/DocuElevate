"""Tests for app/api/logs.py module."""
import pytest
from datetime import datetime

from app.models import FileRecord, ProcessingLog


@pytest.mark.integration
class TestListProcessingLogs:
    """Tests for list_processing_logs endpoint."""

    def test_list_empty_logs(self, client):
        """Test listing logs when none exist."""
        response = client.get("/api/logs")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_logs_with_data(self, client, db_session):
        """Test listing logs with data in database."""
        # Create a log entry
        log = ProcessingLog(
            task_id="test-task-123",
            step_name="process_document",
            status="success",
            message="Test log",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["task_id"] == "test-task-123"
        assert data[0]["step_name"] == "process_document"
        assert data[0]["status"] == "success"

    def test_list_logs_filter_by_task_id(self, client, db_session):
        """Test filtering logs by task_id."""
        log1 = ProcessingLog(task_id="task-a", step_name="step1", status="success", message="Log A")
        log2 = ProcessingLog(task_id="task-b", step_name="step2", status="success", message="Log B")
        db_session.add_all([log1, log2])
        db_session.commit()

        response = client.get("/api/logs?task_id=task-a")
        assert response.status_code == 200
        data = response.json()
        assert all(log["task_id"] == "task-a" for log in data)

    def test_list_logs_with_limit(self, client, db_session):
        """Test limiting number of returned logs."""
        for i in range(5):
            log = ProcessingLog(task_id=f"task-{i}", step_name="step", status="success", message=f"Log {i}")
            db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


@pytest.mark.integration
class TestGetFileProcessingLogs:
    """Tests for get_file_processing_logs endpoint."""

    def test_get_logs_for_existing_file(self, client, db_session):
        """Test getting logs for a file that exists."""
        file_record = FileRecord(
            filehash="abc123def456",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        log = ProcessingLog(
            file_id=file_record.id,
            task_id="task-123",
            step_name="process_document",
            status="success",
            message="Processed",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get(f"/api/logs/file/{file_record.id}")
        assert response.status_code == 200
        data = response.json()
        assert "file" in data
        assert "logs" in data
        assert data["file"]["original_filename"] == "test.pdf"
        assert len(data["logs"]) == 1

    def test_get_logs_for_nonexistent_file(self, client):
        """Test getting logs for a file that doesn't exist."""
        response = client.get("/api/logs/file/99999")
        assert response.status_code == 404


@pytest.mark.integration
class TestGetTaskProcessingLogs:
    """Tests for get_task_processing_logs endpoint."""

    def test_get_logs_for_existing_task(self, client, db_session):
        """Test getting logs for an existing task."""
        log = ProcessingLog(
            task_id="test-task-abc",
            step_name="process_document",
            status="success",
            message="Done",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs/task/test-task-abc")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-abc"
        assert len(data["logs"]) == 1

    def test_get_logs_for_nonexistent_task(self, client):
        """Test getting logs for a task that doesn't exist."""
        response = client.get("/api/logs/task/nonexistent-task")
        assert response.status_code == 404
