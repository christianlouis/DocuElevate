"""
Tests for file detail view improvements including reprocessing and preview endpoints.
"""
import os
import pytest
from fastapi.testclient import TestClient
from app.models import FileRecord, ProcessingLog


@pytest.mark.integration
class TestFileReprocessing:
    """Tests for single file reprocessing endpoint."""
    
    def test_reprocess_existing_file(self, client: TestClient, db_session, sample_pdf_path):
        """Test reprocessing an existing file."""
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
    
    def test_file_detail_view_nonexistent(self, client: TestClient):
        """Test file detail view for nonexistent file."""
        response = client.get("/files/99999/detail")
        assert response.status_code == 200  # Returns page with error message
        assert b"not found" in response.content.lower()
