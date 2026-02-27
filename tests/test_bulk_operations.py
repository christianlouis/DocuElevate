"""
Tests for bulk file operations (delete and reprocess).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileProcessingStep, FileRecord


@pytest.mark.integration
@pytest.mark.requires_db
class TestSingleFileOperations:
    """Tests for single file operations."""

    def test_single_file_delete_success(self, client: TestClient, db_session):
        """Test deletion of a single file."""
        # Create a sample file
        file_record = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        file_id = file_record.id

        # Delete the file
        response = client.delete(f"/api/files/{file_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert f"File record {file_id} deleted successfully" in data["message"]

        # Verify file is deleted
        file_record = db_session.query(FileRecord).filter(FileRecord.id == file_id).first()
        assert file_record is None

    def test_single_file_delete_nonexistent(self, client: TestClient, db_session):
        """Test deletion of a non-existent file."""
        response = client.delete("/api/files/9999")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


@pytest.mark.integration
@pytest.mark.requires_db
class TestBulkOperations:
    """Tests for bulk file operations."""

    def test_bulk_delete_success(self, client: TestClient, db_session):
        """Test bulk deletion of files."""
        # Create sample files
        file_ids = []
        for i in range(3):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file_record)
            db_session.flush()
            file_ids.append(file_record.id)
        db_session.commit()

        # Bulk delete
        response = client.post("/api/files/bulk-delete", json=file_ids)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["deleted_ids"]) == 3

        # Verify files are deleted
        for file_id in file_ids:
            file_record = db_session.query(FileRecord).filter(FileRecord.id == file_id).first()
            assert file_record is None

    def test_bulk_delete_empty_list(self, client: TestClient, db_session):
        """Test bulk deletion with empty list."""
        response = client.post("/api/files/bulk-delete", json=[])
        assert response.status_code == 404
        data = response.json()
        assert "No files found" in data["detail"]

    def test_bulk_delete_nonexistent_files(self, client: TestClient, db_session):
        """Test bulk deletion of non-existent files."""
        response = client.post("/api/files/bulk-delete", json=[9999, 9998])
        assert response.status_code == 404

    @patch("app.api.files.process_document")
    def test_bulk_reprocess_success(self, mock_process_document, client: TestClient, db_session):
        """Test bulk reprocessing of files passes file_id to skip duplicate check."""
        # Setup mock
        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Create sample files with local files that "exist"
        file_ids = []
        for i in range(2):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file_record)
            db_session.flush()
            file_ids.append(file_record.id)
        db_session.commit()

        # Mock os.path.exists to return True
        with patch("os.path.exists", return_value=True):
            response = client.post("/api/files/bulk-reprocess", json=file_ids)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["processed_files"]) == 2
        assert len(data["task_ids"]) == 2

        # Verify that file_id was passed to skip duplicate check
        for call_args in mock_process_document.delay.call_args_list:
            assert "file_id" in call_args.kwargs or len(call_args.args) > 1

    @patch("app.api.files.process_document")
    def test_bulk_reprocess_missing_files(self, mock_process_document, client: TestClient, db_session):
        """Test bulk reprocessing when some local files are missing."""
        # Setup mock
        mock_task = MagicMock()
        mock_task.id = "test-task-id"
        mock_process_document.delay.return_value = mock_task

        # Create sample files
        file_ids = []
        for i in range(2):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",  # Both files have local_filename
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file_record)
            db_session.flush()
            file_ids.append(file_record.id)
        db_session.commit()

        # Mock os.path.exists to return False for missing file
        with patch("os.path.exists", return_value=False):
            response = client.post("/api/files/bulk-reprocess", json=file_ids)

        assert response.status_code == 200
        data = response.json()
        # All files should have errors since we mocked exists to return False
        assert data["errors"] is not None
        assert len(data["errors"]) == 2

    def test_bulk_reprocess_nonexistent_files(self, client: TestClient, db_session):
        """Test bulk reprocessing of non-existent files."""
        response = client.post("/api/files/bulk-reprocess", json=[9999, 9998])
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.requires_db
class TestStatusFilter:
    """Tests for status filtering in files view."""

    def test_status_filter_pending(self, client: TestClient, db_session):
        """Test filtering files by pending status."""
        # Create files with different statuses
        # File 1: Pending (no processing steps)
        file1 = FileRecord(
            filehash="hash1",
            original_filename="pending.pdf",
            local_filename="/tmp/pending.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file1)

        # File 2: Processing (has in_progress step)
        file2 = FileRecord(
            filehash="hash2",
            original_filename="processing.pdf",
            local_filename="/tmp/processing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file2)
        db_session.flush()

        step2 = FileProcessingStep(
            file_id=file2.id,
            step_name="extract_text",
            status="in_progress",
        )
        db_session.add(step2)
        db_session.commit()

        # Test pending filter
        response = client.get("/files?status=pending")
        assert response.status_code == 200
        # Check that pending file is shown (HTML response)
        assert "pending.pdf" in response.text
        assert "processing.pdf" not in response.text

    def test_status_filter_processing(self, client: TestClient, db_session):
        """Test filtering files by processing status."""
        # Create file with in_progress status
        file_record = FileRecord(
            filehash="hash1",
            original_filename="processing.pdf",
            local_filename="/tmp/processing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.flush()

        step = FileProcessingStep(
            file_id=file_record.id,
            step_name="extract_text",
            status="in_progress",
        )
        db_session.add(step)
        db_session.commit()

        # Test processing filter
        response = client.get("/files?status=processing")
        assert response.status_code == 200
        assert "processing.pdf" in response.text

    def test_status_filter_completed(self, client: TestClient, db_session):
        """Test filtering files by completed status."""
        # Create file with success status
        file_record = FileRecord(
            filehash="hash1",
            original_filename="completed.pdf",
            local_filename="/tmp/completed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.flush()

        for step_name in ("extract_text", "send_to_all_destinations"):
            step = FileProcessingStep(
                file_id=file_record.id,
                step_name=step_name,
                status="success",
            )
            db_session.add(step)
        db_session.commit()

        # Test completed filter
        response = client.get("/files?status=completed")
        assert response.status_code == 200
        assert "completed.pdf" in response.text

    def test_status_filter_failed(self, client: TestClient, db_session):
        """Test filtering files by failed status."""
        # Create file with failure status
        file_record = FileRecord(
            filehash="hash1",
            original_filename="failed.pdf",
            local_filename="/tmp/failed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.flush()

        step = FileProcessingStep(
            file_id=file_record.id,
            step_name="extract_text",
            status="failure",
            error_message="Failed",
        )
        db_session.add(step)
        db_session.commit()

        # Test failed filter
        response = client.get("/files?status=failed")
        assert response.status_code == 200
        assert "failed.pdf" in response.text
