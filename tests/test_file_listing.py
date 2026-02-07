"""
Tests for file listing, pagination, filtering, and detail endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.models import FileRecord, ProcessingLog
from datetime import datetime


@pytest.mark.integration
@pytest.mark.requires_db
class TestFileListingPagination:
    """Tests for file listing with pagination, sorting, and filtering."""
    
    def test_list_files_empty_with_pagination(self, client: TestClient):
        """Test listing files when database is empty returns pagination structure."""
        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "pagination" in data
        assert isinstance(data["files"], list)
        assert len(data["files"]) == 0
        assert data["pagination"]["total_items"] == 0
    
    def test_list_files_with_data(self, client: TestClient, db_session):
        """Test listing files with sample data."""
        # Create sample files
        for i in range(5):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024 * (i + 1),
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 5
        assert data["pagination"]["total_items"] == 5
        assert data["pagination"]["page"] == 1
    
    def test_pagination_works(self, client: TestClient, db_session):
        """Test that pagination correctly limits results."""
        # Create 10 sample files
        for i in range(10):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Get first page with 5 items per page
        response = client.get("/api/files?page=1&per_page=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 5
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["total_pages"] == 2
        
        # Get second page
        response = client.get("/api/files?page=2&per_page=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 5
        assert data["pagination"]["page"] == 2
    
    def test_sorting_by_filename(self, client: TestClient, db_session):
        """Test sorting files by filename."""
        # Create files with different names
        for name in ["zebra.pdf", "apple.pdf", "middle.pdf"]:
            file_record = FileRecord(
                filehash=name,
                original_filename=name,
                local_filename=f"/tmp/{name}",
                file_size=1024,
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Sort ascending
        response = client.get("/api/files?sort_by=original_filename&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        filenames = [f["original_filename"] for f in data["files"]]
        assert filenames == ["apple.pdf", "middle.pdf", "zebra.pdf"]
        
        # Sort descending
        response = client.get("/api/files?sort_by=original_filename&sort_order=desc")
        assert response.status_code == 200
        data = response.json()
        filenames = [f["original_filename"] for f in data["files"]]
        assert filenames == ["zebra.pdf", "middle.pdf", "apple.pdf"]
    
    def test_sorting_by_file_size(self, client: TestClient, db_session):
        """Test sorting files by size."""
        # Create files with different sizes
        for i, size in enumerate([5000, 1000, 3000]):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"file{i}.pdf",
                local_filename=f"/tmp/file{i}.pdf",
                file_size=size,
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Sort by size ascending
        response = client.get("/api/files?sort_by=file_size&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        sizes = [f["file_size"] for f in data["files"]]
        assert sizes == [1000, 3000, 5000]
    
    def test_search_filter(self, client: TestClient, db_session):
        """Test searching files by filename."""
        # Create files with different names
        for name in ["invoice_2024.pdf", "receipt_2024.pdf", "report.pdf"]:
            file_record = FileRecord(
                filehash=name,
                original_filename=name,
                local_filename=f"/tmp/{name}",
                file_size=1024,
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Search for "2024"
        response = client.get("/api/files?search=2024")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        filenames = [f["original_filename"] for f in data["files"]]
        assert "invoice_2024.pdf" in filenames
        assert "receipt_2024.pdf" in filenames
        assert "report.pdf" not in filenames
    
    def test_mime_type_filter(self, client: TestClient, db_session):
        """Test filtering files by MIME type."""
        # Create files with different MIME types
        files_data = [
            ("file1.pdf", "application/pdf"),
            ("file2.txt", "text/plain"),
            ("file3.pdf", "application/pdf"),
        ]
        for filename, mime_type in files_data:
            file_record = FileRecord(
                filehash=filename,
                original_filename=filename,
                local_filename=f"/tmp/{filename}",
                file_size=1024,
                mime_type=mime_type
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Filter by PDF mime type
        response = client.get("/api/files?mime_type=application/pdf")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        for file in data["files"]:
            assert file["mime_type"] == "application/pdf"
    
    def test_processing_status_included(self, client: TestClient, db_session):
        """Test that processing status is included in file listing."""
        # Create a file
        file_record = FileRecord(
            filehash="test_hash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        
        # Add a processing log
        log = ProcessingLog(
            file_id=file_record.id,
            task_id="test_task",
            step_name="test_step",
            status="success",
            message="Test message"
        )
        db_session.add(log)
        db_session.commit()
        
        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert "processing_status" in data["files"][0]
        assert data["files"][0]["processing_status"]["status"] == "completed"


@pytest.mark.integration
@pytest.mark.requires_db
class TestFileDetailEndpoint:
    """Tests for file detail endpoint."""
    
    def test_get_file_detail_success(self, client: TestClient, db_session):
        """Test getting details for an existing file."""
        # Create a file
        file_record = FileRecord(
            filehash="test_hash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        
        # Add processing logs
        for i, status in enumerate(["success", "in_progress", "success"]):
            log = ProcessingLog(
                file_id=file_record.id,
                task_id=f"task_{i}",
                step_name=f"step_{i}",
                status=status,
                message=f"Message {i}"
            )
            db_session.add(log)
        db_session.commit()
        
        response = client.get(f"/api/files/{file_record.id}")
        assert response.status_code == 200
        data = response.json()
        
        # Check file details
        assert "file" in data
        assert data["file"]["id"] == file_record.id
        assert data["file"]["original_filename"] == "test.pdf"
        
        # Check processing status
        assert "processing_status" in data
        assert data["processing_status"]["status"] in ["completed", "processing"]
        
        # Check logs
        assert "logs" in data
        assert len(data["logs"]) == 3
    
    def test_get_nonexistent_file_detail(self, client: TestClient):
        """Test getting details for a non-existent file returns 404."""
        response = client.get("/api/files/99999")
        assert response.status_code == 404
    
    def test_file_detail_status_determination(self, client: TestClient, db_session):
        """Test that processing status is correctly determined."""
        # Create a file
        file_record = FileRecord(
            filehash="test_hash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file_record)
        db_session.commit()
        
        # Test 1: No logs = pending
        response = client.get(f"/api/files/{file_record.id}")
        assert response.status_code == 200
        assert response.json()["processing_status"]["status"] == "pending"
        
        # Test 2: Success log = completed
        log = ProcessingLog(
            file_id=file_record.id,
            task_id="task_1",
            step_name="step_1",
            status="success"
        )
        db_session.add(log)
        db_session.commit()
        
        response = client.get(f"/api/files/{file_record.id}")
        assert response.status_code == 200
        assert response.json()["processing_status"]["status"] == "completed"
        
        # Test 3: Failure log = failed
        log2 = ProcessingLog(
            file_id=file_record.id,
            task_id="task_2",
            step_name="step_2",
            status="failure"
        )
        db_session.add(log2)
        db_session.commit()
        
        response = client.get(f"/api/files/{file_record.id}")
        assert response.status_code == 200
        assert response.json()["processing_status"]["status"] == "failed"
