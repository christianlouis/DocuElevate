"""
Tests for bulk file operations (delete and reprocess).
"""

import io
import zipfile
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


@pytest.mark.integration
@pytest.mark.requires_db
class TestBulkDownload:
    """Tests for POST /api/files/bulk-download endpoint."""

    def test_bulk_download_no_files_found(self, client: TestClient, db_session):
        """Test bulk download with non-existent IDs."""
        response = client.post("/api/files/bulk-download", json=[99999, 99998])
        assert response.status_code == 404

    def test_bulk_download_files_not_on_disk(self, client: TestClient, db_session):
        """Test bulk download when files are not found on disk."""
        file_record = FileRecord(
            filehash="hash_dl1",
            original_filename="nodisk.pdf",
            local_filename="/nonexistent/nodisk.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file_record.id])
        assert response.status_code == 404
        assert "None of the selected files" in response.json()["detail"]

    def test_bulk_download_success(self, client: TestClient, db_session, tmp_path):
        """Test successful bulk download returns a ZIP archive."""
        # Create a real file on disk
        pdf_file = tmp_path / "sample.pdf"
        pdf_file.write_bytes(b"PDF content")

        file_record = FileRecord(
            filehash="hash_dl2",
            original_filename="sample.pdf",
            local_filename=str(pdf_file),
            processed_file_path=str(pdf_file),
            file_size=len(b"PDF content"),
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file_record.id])
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert ".zip" in response.headers["content-disposition"]

    def test_bulk_download_multiple_files(self, client: TestClient, db_session, tmp_path):
        """Test bulk download with multiple files produces a valid ZIP."""
        ids = []
        for i in range(3):
            f = tmp_path / f"file{i}.pdf"
            f.write_bytes(f"content {i}".encode())
            rec = FileRecord(
                filehash=f"hash_multi_{i}",
                original_filename=f"file{i}.pdf",
                local_filename=str(f),
                processed_file_path=str(f),
                file_size=len(f"content {i}".encode()),
                mime_type="application/pdf",
            )
            db_session.add(rec)
            db_session.commit()
            ids.append(rec.id)

        response = client.post("/api/files/bulk-download", json=ids)
        assert response.status_code == 200

        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data) as zf:
            names = zf.namelist()
        assert len(names) == 3

    def test_bulk_download_duplicate_filenames(self, client: TestClient, db_session, tmp_path):
        """Test bulk download disambiguates duplicate filenames."""
        ids = []
        for i in range(2):
            f = tmp_path / f"dup_{i}.pdf"
            f.write_bytes(b"data")
            rec = FileRecord(
                filehash=f"hash_dup_{i}",
                original_filename="dup.pdf",  # same name
                local_filename=str(f),
                processed_file_path=str(f),
                file_size=4,
                mime_type="application/pdf",
            )
            db_session.add(rec)
            db_session.commit()
            ids.append(rec.id)

        response = client.post("/api/files/bulk-download", json=ids)
        assert response.status_code == 200
        zip_data = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_data) as zf:
            names = zf.namelist()
        # Names must be unique
        assert len(names) == len(set(names))


@pytest.mark.integration
@pytest.mark.requires_db
class TestBulkReprocessCloudOcr:
    """Tests for POST /api/files/bulk-reprocess-cloud-ocr endpoint."""

    @patch("app.api.files.process_document")
    def test_bulk_reprocess_cloud_ocr_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test bulk Cloud OCR reprocessing queues tasks."""
        mock_task = MagicMock()
        mock_task.id = "task-cloud-ocr-1"
        mock_delay.delay.return_value = mock_task

        pdf_file = tmp_path / "ocr_test.pdf"
        pdf_file.write_bytes(b"PDF data")

        file_record = FileRecord(
            filehash="hash_ocr1",
            original_filename="ocr_test.pdf",
            local_filename=str(pdf_file),
            file_size=8,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file_record.id])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["processed_files"]) == 1
        assert data["errors"] == []

        # Ensure force_cloud_ocr=True was passed
        call_kwargs = mock_delay.delay.call_args.kwargs
        assert call_kwargs.get("force_cloud_ocr") is True

    def test_bulk_reprocess_cloud_ocr_no_file_on_disk(self, client: TestClient, db_session):
        """Test Cloud OCR bulk reprocess skips files not on disk."""
        file_record = FileRecord(
            filehash="hash_ocr2",
            original_filename="missing.pdf",
            local_filename="/nonexistent/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file_record.id])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert len(data["errors"]) == 1

    def test_bulk_reprocess_cloud_ocr_no_files_found(self, client: TestClient, db_session):
        """Test Cloud OCR bulk reprocess with non-existent IDs."""
        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[99999])
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.requires_db
class TestOcrQualityFilter:
    """Tests for the ocr_quality filter on the /files view."""

    def test_ocr_quality_poor_filter(self, client: TestClient, db_session):
        """Files with a low ocr_quality_score appear when filtering poor."""
        rec_poor = FileRecord(
            filehash="hash_poor1",
            original_filename="poor_quality.pdf",
            local_filename="/tmp/poor_quality.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=40,
        )
        rec_good = FileRecord(
            filehash="hash_good1",
            original_filename="good_quality.pdf",
            local_filename="/tmp/good_quality.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=95,
        )
        db_session.add_all([rec_poor, rec_good])
        db_session.commit()

        response = client.get("/files?ocr_quality=poor")
        assert response.status_code == 200
        assert "poor_quality.pdf" in response.text
        assert "good_quality.pdf" not in response.text

    def test_ocr_quality_good_filter(self, client: TestClient, db_session):
        """Files with a high ocr_quality_score appear when filtering good."""
        rec_poor = FileRecord(
            filehash="hash_poor2",
            original_filename="poor_quality2.pdf",
            local_filename="/tmp/poor_quality2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=40,
        )
        rec_good = FileRecord(
            filehash="hash_good2",
            original_filename="good_quality2.pdf",
            local_filename="/tmp/good_quality2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=95,
        )
        db_session.add_all([rec_poor, rec_good])
        db_session.commit()

        response = client.get("/files?ocr_quality=good")
        assert response.status_code == 200
        assert "good_quality2.pdf" in response.text
        assert "poor_quality2.pdf" not in response.text

    def test_ocr_quality_unchecked_filter(self, client: TestClient, db_session):
        """Files with no score appear when filtering unchecked."""
        rec_unchecked = FileRecord(
            filehash="hash_unch1",
            original_filename="unchecked.pdf",
            local_filename="/tmp/unchecked.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=None,
        )
        rec_scored = FileRecord(
            filehash="hash_scored1",
            original_filename="scored.pdf",
            local_filename="/tmp/scored.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ocr_quality_score=90,
        )
        db_session.add_all([rec_unchecked, rec_scored])
        db_session.commit()

        response = client.get("/files?ocr_quality=unchecked")
        assert response.status_code == 200
        assert "unchecked.pdf" in response.text
        assert "scored.pdf" not in response.text

    def test_ocr_quality_no_filter(self, client: TestClient, db_session):
        """All files appear when no ocr_quality filter is applied."""
        rec = FileRecord(
            filehash="hash_all1",
            original_filename="all_files.pdf",
            local_filename="/tmp/all_files.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(rec)
        db_session.commit()

        response = client.get("/files")
        assert response.status_code == 200
        assert "all_files.pdf" in response.text
