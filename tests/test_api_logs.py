"""
Tests for logs API endpoints
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestLogsEndpoints:
    """Tests for processing logs API endpoints."""

    def test_list_logs_empty(self, client: TestClient, db_session):
        """Test listing logs when database is empty."""
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_logs_with_data(self, client: TestClient, db_session):
        """Test listing logs with data."""
        from app.models import ProcessingLog

        # Add test log
        log = ProcessingLog(
            file_id=1,
            task_id="test-task-123",
            step_name="test_step",
            status="success",
            message="Test message",
            timestamp=datetime.utcnow()
        )
        db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert data[0]["task_id"] == "test-task-123"

    def test_list_logs_filter_by_file_id(self, client: TestClient, db_session):
        """Test filtering logs by file_id."""
        from app.models import ProcessingLog

        # Add test logs with different file_ids
        log1 = ProcessingLog(file_id=1, task_id="task-1", step_name="step1", status="success", timestamp=datetime.utcnow())
        log2 = ProcessingLog(file_id=2, task_id="task-2", step_name="step2", status="success", timestamp=datetime.utcnow())
        db_session.add_all([log1, log2])
        db_session.commit()

        response = client.get("/api/logs?file_id=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["file_id"] == 1

    def test_list_logs_filter_by_task_id(self, client: TestClient, db_session):
        """Test filtering logs by task_id."""
        from app.models import ProcessingLog

        log1 = ProcessingLog(file_id=1, task_id="task-abc", step_name="step1", status="success", timestamp=datetime.utcnow())
        log2 = ProcessingLog(file_id=1, task_id="task-xyz", step_name="step2", status="success", timestamp=datetime.utcnow())
        db_session.add_all([log1, log2])
        db_session.commit()

        response = client.get("/api/logs?task_id=task-abc")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["task_id"] == "task-abc"

    def test_list_logs_with_limit(self, client: TestClient, db_session):
        """Test limiting number of logs returned."""
        from app.models import ProcessingLog

        # Add multiple logs
        for i in range(10):
            log = ProcessingLog(file_id=1, task_id=f"task-{i}", step_name="step", status="success", timestamp=datetime.utcnow())
            db_session.add(log)
        db_session.commit()

        response = client.get("/api/logs?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_get_file_logs_success(self, client: TestClient, db_session):
        """Test getting logs for a specific file."""
        from app.models import FileRecord, ProcessingLog

        # Create file record
        file_record = FileRecord(
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        file_id = file_record.id

        # Add log for this file
        log = ProcessingLog(file_id=file_id, task_id="task-1", step_name="process", status="success", timestamp=datetime.utcnow())
        db_session.add(log)
        db_session.commit()

        response = client.get(f"/api/logs/file/{file_id}")
        assert response.status_code == 200
        data = response.json()
        assert "file" in data
        assert "logs" in data
        assert data["file"]["id"] == file_id
        assert len(data["logs"]) == 1

    def test_get_file_logs_not_found(self, client: TestClient, db_session):
        """Test getting logs for non-existent file."""
        response = client.get("/api/logs/file/99999")
        assert response.status_code == 404

    def test_get_task_logs_success(self, client: TestClient, db_session):
        """Test getting logs for a specific task."""
        from app.models import ProcessingLog

        task_id = "test-task-456"
        log1 = ProcessingLog(file_id=1, task_id=task_id, step_name="step1", status="in_progress", timestamp=datetime.utcnow())
        log2 = ProcessingLog(file_id=1, task_id=task_id, step_name="step2", status="success", timestamp=datetime.utcnow())
        db_session.add_all([log1, log2])
        db_session.commit()

        response = client.get(f"/api/logs/task/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert len(data["logs"]) == 2
        assert data["total_logs"] == 2

    def test_get_task_logs_not_found(self, client: TestClient, db_session):
        """Test getting logs for non-existent task."""
        response = client.get("/api/logs/task/nonexistent-task")
        assert response.status_code == 404
