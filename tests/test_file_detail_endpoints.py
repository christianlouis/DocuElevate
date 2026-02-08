"""
Tests for file detail view improvements including reprocessing and preview endpoints.
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.models import FileRecord, ProcessingLog


@pytest.mark.integration
class TestFileReprocessing:
    """Tests for single file reprocessing endpoint."""
    
    @patch("app.api.files.process_document")
    def test_reprocess_existing_file(self, mock_process_document, client: TestClient, db_session, sample_pdf_path):
        """Test reprocessing an existing file."""
        # Setup mock
        mock_task = MagicMock()
        mock_task.id = "test-task-123"
        mock_process_document.delay.return_value = mock_task
        
        # Create a file record
        file_record = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Add a failed processing log
        log = ProcessingLog(
            file_id=file_record.id,
            task_id="test-task-123",
            step_name="extract_metadata_with_gpt",
            status="failure",
            message="API error"
        )
        db_session.add(log)
        db_session.commit()
        
        # Test reprocessing
        response = client.post(f"/api/files/{file_record.id}/reprocess")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "task_id" in data
        assert data["file_id"] == file_record.id
        assert data["filename"] == "test.pdf"
    
    def test_reprocess_nonexistent_file(self, client: TestClient):
        """Test reprocessing a file that doesn't exist."""
        response = client.post("/api/files/99999/reprocess")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_reprocess_file_missing_on_disk(self, client: TestClient, db_session):
        """Test reprocessing when local file is missing."""
        # Create a file record with non-existent local path
        file_record = FileRecord(
            filehash="xyz789",
            original_filename="missing.pdf",
            local_filename="/nonexistent/path/missing.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test reprocessing
        response = client.post(f"/api/files/{file_record.id}/reprocess")
        assert response.status_code == 400
        assert "not found on disk" in response.json()["detail"].lower()


@pytest.mark.integration
class TestSubtaskRetry:
    """Tests for per-subtask retry endpoint."""
    
    def test_retry_subtask_invalid_file(self, client: TestClient):
        """Test retrying a subtask for nonexistent file."""
        response = client.post("/api/files/99999/retry-subtask?subtask_name=upload_to_dropbox")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_retry_subtask_invalid_task_name(self, client: TestClient, db_session, sample_pdf_path):
        """Test retrying with invalid subtask name."""
        # Create a file record
        file_record = FileRecord(
            filehash="retry123",
            original_filename="retry.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test with invalid subtask name
        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=invalid_task")
        assert response.status_code == 400
        assert "invalid subtask name" in response.json()["detail"].lower()
    
    def test_retry_subtask_missing_processed_file(self, client: TestClient, db_session, sample_pdf_path):
        """Test retrying when processed file is missing."""
        # Create a file record
        file_record = FileRecord(
            filehash="retry456",
            original_filename="retry2.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test retry (processed file won't exist)
        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=upload_to_dropbox")
        assert response.status_code == 400
        assert "processed file not found" in response.json()["detail"].lower()


@pytest.mark.integration
class TestFilePreview:
    """Tests for file preview endpoint."""
    
    def test_preview_original_file(self, client: TestClient, db_session, sample_pdf_path):
        """Test getting original file preview."""
        # Create a file record
        file_record = FileRecord(
            filehash="def456",
            original_filename="preview.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test preview
        response = client.get(f"/api/files/{file_record.id}/preview?version=original")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
    
    def test_preview_processed_file_not_found(self, client: TestClient, db_session, sample_pdf_path):
        """Test getting processed file preview when it doesn't exist."""
        # Create a file record
        file_record = FileRecord(
            filehash="ghi789",
            original_filename="processed.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test preview (processed version should not exist)
        response = client.get(f"/api/files/{file_record.id}/preview?version=processed")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_preview_nonexistent_file(self, client: TestClient):
        """Test preview for a file that doesn't exist."""
        response = client.get("/api/files/99999/preview?version=original")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_preview_invalid_version(self, client: TestClient, db_session, sample_pdf_path):
        """Test preview with invalid version parameter."""
        # Create a file record
        file_record = FileRecord(
            filehash="jkl012",
            original_filename="test.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Test with invalid version
        response = client.get(f"/api/files/{file_record.id}/preview?version=invalid")
        assert response.status_code == 400
        assert "invalid version" in response.json()["detail"].lower()


@pytest.mark.integration
class TestFileDetailView:
    """Tests for enhanced file detail view."""
    
    def test_file_detail_view_with_logs(self, client: TestClient, db_session, sample_pdf_path):
        """Test file detail view returns enhanced data."""
        # Create a file record
        file_record = FileRecord(
            filehash="mno345",
            original_filename="detail.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Add processing logs
        logs = [
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-1",
                step_name="hash_file",
                status="success",
                message="File hashed successfully"
            ),
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-1",
                step_name="create_file_record",
                status="success",
                message="File record created"
            ),
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-1",
                step_name="extract_metadata_with_gpt",
                status="failure",
                message="API rate limit exceeded"
            )
        ]
        for log in logs:
            db_session.add(log)
        db_session.commit()
        
        # Test detail view
        response = client.get(f"/files/{file_record.id}/detail")
        assert response.status_code == 200
        # Check that response contains HTML with file information
        assert b"File Information" in response.content
        assert b"detail.pdf" in response.content
        assert b"Processing History" in response.content
    
    def test_file_detail_view_with_upload_branches(self, client: TestClient, db_session, sample_pdf_path):
        """Test file detail view with upload subtask branches."""
        # Create a file record
        file_record = FileRecord(
            filehash="branch123",
            original_filename="branches.pdf",
            local_filename=sample_pdf_path,
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)
        
        # Add processing logs including upload branches
        logs = [
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-1",
                step_name="send_to_all_destinations",
                status="success",
                message="Queued uploads"
            ),
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-2",
                step_name="upload_to_dropbox",
                status="success",
                message="Uploaded to Dropbox"
            ),
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-3",
                step_name="upload_to_s3",
                status="failure",
                message="S3 connection error"
            ),
            ProcessingLog(
                file_id=file_record.id,
                task_id="task-4",
                step_name="upload_to_nextcloud",
                status="success",
                message="Uploaded to Nextcloud"
            )
        ]
        for log in logs:
            db_session.add(log)
        db_session.commit()
        
        # Test detail view
        response = client.get(f"/files/{file_record.id}/detail")
        assert response.status_code == 200
        # Check that response contains branching visualization elements
        assert b"Process Flow Visualization" in response.content
        assert b"Processing Status Summary" in response.content
        # Should have upload branches
        assert b"Dropbox" in response.content or b"dropbox" in response.content
    
    def test_file_detail_view_nonexistent(self, client: TestClient):
        """Test file detail view for nonexistent file."""
        response = client.get("/files/99999/detail")
        assert response.status_code == 200  # Returns page with error message
        assert b"not found" in response.content.lower()


@pytest.mark.unit
class TestProcessingFlowComputation:
    """Tests for the _compute_processing_flow function."""
    
    def test_flow_with_upload_branches(self, db_session):
        """Test that upload tasks are properly grouped as branches."""
        from app.views.files import _compute_processing_flow
        
        # Create mock logs
        class MockLog:
            def __init__(self, step_name, status, message, timestamp, task_id):
                self.step_name = step_name
                self.status = status
                self.message = message
                self.timestamp = timestamp
                self.task_id = task_id
        
        logs = [
            MockLog("hash_file", "success", "Hashed", None, "task-1"),
            MockLog("send_to_all_destinations", "success", "Queued", None, "task-2"),
            MockLog("upload_to_dropbox", "success", "Uploaded", None, "task-3"),
            MockLog("upload_to_s3", "failure", "Failed", None, "task-4"),
        ]
        
        flow = _compute_processing_flow(logs)
        
        # Find the upload stage
        upload_stage = None
        for stage in flow:
            if stage.get("is_branch_parent"):
                upload_stage = stage
                break
        
        assert upload_stage is not None
        assert "branches" in upload_stage
        assert len(upload_stage["branches"]) == 2
        
        # Check branch details
        branches = {b["key"]: b for b in upload_stage["branches"]}
        assert "upload_to_dropbox" in branches
        assert branches["upload_to_dropbox"]["status"] == "success"
        assert "upload_to_s3" in branches
        assert branches["upload_to_s3"]["status"] == "failure"
        assert branches["upload_to_s3"]["can_retry"] is True


@pytest.mark.unit
class TestStepSummary:
    """Tests for the _compute_step_summary function."""
    
    def test_summary_with_mixed_statuses(self):
        """Test step summary with various statuses."""
        from app.views.files import _compute_step_summary
        
        # Create mock logs
        class MockLog:
            def __init__(self, step_name, status):
                self.step_name = step_name
                self.status = status
        
        logs = [
            MockLog("hash_file", "success"),
            MockLog("create_file_record", "success"),
            MockLog("extract_metadata_with_gpt", "failure"),
            MockLog("upload_to_dropbox", "success"),
            MockLog("upload_to_s3", "failure"),
            MockLog("upload_to_nextcloud", "in_progress"),
        ]
        
        summary = _compute_step_summary(logs)
        
        assert "main" in summary
        assert "uploads" in summary
        assert summary["total_main_steps"] == 3
        assert summary["total_upload_tasks"] == 3
        assert summary["uploads"]["success"] == 1
        assert summary["uploads"]["failure"] == 1
        assert summary["uploads"]["in_progress"] == 1
