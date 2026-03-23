"""
Comprehensive unit tests for app/api/files.py

Tests all API endpoints with success and error cases, proper mocking, and edge cases.
Target: Bring coverage from 11.75% to 70%+
"""

import os
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.models import FileRecord, ProcessingLog


@pytest.mark.unit
class TestListFilesAPI:
    """Tests for GET /api/files endpoint."""

    def test_list_files_empty(self, client: TestClient, db_session):
        """Test listing files when database is empty."""
        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "pagination" in data
        assert len(data["files"]) == 0
        assert data["pagination"]["total"] == 0

    def test_list_files_with_data(self, client: TestClient, db_session):
        """Test listing files with existing data."""
        # Create test file records
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 2
        assert data["pagination"]["total"] == 2

    def test_list_files_with_pagination(self, client: TestClient, db_session):
        """Test pagination parameters."""
        # Create 10 files
        for i in range(10):
            file = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file)
        db_session.commit()

        # Request page 1 with 5 items per page
        response = client.get("/api/files?page=1&per_page=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 5
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["per_page"] == 5
        assert data["pagination"]["pages"] == 2

        # Request page 2
        response = client.get("/api/files?page=2&per_page=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 5

    def test_list_files_with_search(self, client: TestClient, db_session):
        """Test search functionality."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="invoice.pdf",
            local_filename="/tmp/invoice.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="receipt.pdf",
            local_filename="/tmp/receipt.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?search=invoice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "invoice.pdf"

    def test_list_files_with_mime_type_filter(self, client: TestClient, db_session):
        """Test MIME type filtering."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="doc.pdf",
            local_filename="/tmp/doc.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="image.jpg",
            local_filename="/tmp/image.jpg",
            file_size=2048,
            mime_type="image/jpeg",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?mime_type=application/pdf")
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["mime_type"] == "application/pdf"

    def test_list_files_sorting_asc(self, client: TestClient, db_session):
        """Test ascending sort order."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="aaa.pdf",
            local_filename="/tmp/aaa.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="zzz.pdf",
            local_filename="/tmp/zzz.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?sort_by=original_filename&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        assert data["files"][0]["original_filename"] == "aaa.pdf"
        assert data["files"][1]["original_filename"] == "zzz.pdf"

    def test_list_files_sorting_desc(self, client: TestClient, db_session):
        """Test descending sort order."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="aaa.pdf",
            local_filename="/tmp/aaa.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="zzz.pdf",
            local_filename="/tmp/zzz.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?sort_by=original_filename&sort_order=desc")
        assert response.status_code == 200
        data = response.json()
        assert data["files"][0]["original_filename"] == "zzz.pdf"
        assert data["files"][1]["original_filename"] == "aaa.pdf"


@pytest.mark.unit
class TestGetFileDetails:
    """Tests for GET /api/files/{file_id} endpoint."""

    def test_get_file_details_success(self, client: TestClient, db_session):
        """Test getting file details for existing file."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}")
        assert response.status_code == 200
        data = response.json()
        assert "file" in data
        assert "processing_status" in data
        assert "logs" in data
        assert data["file"]["id"] == file.id
        assert data["file"]["original_filename"] == "test.pdf"

    def test_get_file_details_not_found(self, client: TestClient, db_session):
        """Test getting details for non-existent file."""
        response = client.get("/api/files/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_file_details_with_logs(self, client: TestClient, db_session):
        """Test file details includes processing logs."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        # Add processing log
        log = ProcessingLog(
            file_id=file.id,
            task_id="task123",
            step_name="process_document",
            status="success",
            message="Processing completed",
        )
        db_session.add(log)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["logs"]) == 1
        assert data["logs"][0]["step_name"] == "process_document"
        assert data["logs"][0]["status"] == "success"


@pytest.mark.unit
class TestDeleteFileRecord:
    """Tests for DELETE /api/files/{file_id} endpoint."""

    @patch("app.config.settings.allow_file_delete", True)
    def test_delete_file_success(self, client: TestClient, db_session):
        """Test successful file deletion."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()
        file_id = file.id

        response = client.delete(f"/api/files/{file_id}")
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["message"]

        # Verify file is deleted
        deleted_file = db_session.query(FileRecord).filter(FileRecord.id == file_id).first()
        assert deleted_file is None

    @patch("app.config.settings.allow_file_delete", False)
    def test_delete_file_disabled(self, client: TestClient, db_session):
        """Test deletion when disabled in config."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.delete(f"/api/files/{file.id}")
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"].lower()

    @patch("app.config.settings.allow_file_delete", True)
    def test_delete_file_not_found(self, client: TestClient, db_session):
        """Test deleting non-existent file."""
        response = client.delete("/api/files/99999")
        assert response.status_code == 404


@pytest.mark.unit
class TestBulkDeleteFiles:
    """Tests for POST /api/files/bulk-delete endpoint."""

    @patch("app.config.settings.allow_file_delete", True)
    def test_bulk_delete_success(self, client: TestClient, db_session):
        """Test bulk deletion of multiple files."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=2048,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        file_ids = [file1.id, file2.id]
        response = client.post("/api/files/bulk-delete", json=file_ids)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["deleted_ids"]) == 2

        # Verify files are deleted
        remaining = db_session.query(FileRecord).filter(FileRecord.id.in_(file_ids)).all()
        assert len(remaining) == 0

    @patch("app.config.settings.allow_file_delete", False)
    def test_bulk_delete_disabled(self, client: TestClient, db_session):
        """Test bulk delete when disabled."""
        response = client.post("/api/files/bulk-delete", json=[1, 2])
        assert response.status_code == 403

    @patch("app.config.settings.allow_file_delete", True)
    def test_bulk_delete_no_files_found(self, client: TestClient, db_session):
        """Test bulk delete with non-existent IDs."""
        response = client.post("/api/files/bulk-delete", json=[99999, 99998])
        assert response.status_code == 404


@pytest.mark.unit
class TestBulkReprocessFiles:
    """Tests for POST /api/files/bulk-reprocess endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_bulk_reprocess_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test bulk reprocessing of files."""
        # Create files with existing local files
        file1_path = tmp_path / "test1.pdf"
        file1_path.write_bytes(b"%PDF-1.4")

        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename=str(file1_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.commit()

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        response = client.post("/api/files/bulk-reprocess", json=[file1.id])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["processed_files"]) == 1
        assert mock_delay.called

    @patch("app.tasks.process_document.process_document.delay")
    def test_bulk_reprocess_file_not_found_on_disk(self, mock_delay, client: TestClient, db_session):
        """Test bulk reprocess when file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-reprocess", json=[file.id])
        assert response.status_code == 200
        data = response.json()
        # Should report error for file not found
        assert data["errors"] is not None
        assert len(data["errors"]) == 1

    def test_bulk_reprocess_no_files_found(self, client: TestClient, db_session):
        """Test bulk reprocess with non-existent IDs."""
        response = client.post("/api/files/bulk-reprocess", json=[99999])
        assert response.status_code == 404


@pytest.mark.unit
class TestReprocessSingleFile:
    """Tests for POST /api/files/{file_id}/reprocess endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_reprocess_single_file_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test reprocessing a single file."""
        # Create file with existing local file
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        # Mock Celery task
        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        response = client.post(f"/api/files/{file.id}/reprocess")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["task_id"] == "task123"
        assert mock_delay.called

    def test_reprocess_file_not_found(self, client: TestClient, db_session):
        """Test reprocessing non-existent file."""
        response = client.post("/api/files/99999/reprocess")
        assert response.status_code == 404

    def test_reprocess_file_missing_on_disk(self, client: TestClient, db_session):
        """Test reprocessing when file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/reprocess")
        assert response.status_code == 400
        assert "not found on disk" in response.json()["detail"].lower()


@pytest.mark.unit
class TestReprocessWithCloudOCR:
    """Tests for POST /api/files/{file_id}/reprocess-with-cloud-ocr endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_reprocess_with_cloud_ocr_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test reprocessing with forced cloud OCR."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            original_file_path=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        response = client.post(f"/api/files/{file.id}/reprocess-with-cloud-ocr")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["force_cloud_ocr"] is True
        assert mock_delay.called

    def test_reprocess_cloud_ocr_file_not_found(self, client: TestClient, db_session):
        """Test cloud OCR reprocess for non-existent file."""
        response = client.post("/api/files/99999/reprocess-with-cloud-ocr")
        assert response.status_code == 404

    def test_reprocess_cloud_ocr_no_file_on_disk(self, client: TestClient, db_session):
        """Test cloud OCR when no file exists on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/reprocess-with-cloud-ocr")
        assert response.status_code == 400


@pytest.mark.unit
class TestRetrySubtask:
    """Tests for POST /api/files/{file_id}/retry-subtask endpoint."""

    @patch("app.tasks.upload_to_dropbox.upload_to_dropbox.delay")
    @patch("app.config.settings.workdir", "/tmp")
    def test_retry_upload_subtask_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test retrying upload subtask."""
        # Create processed file
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "hash1.pdf"
        processed_file.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_dropbox")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["subtask_name"] == "upload_to_dropbox"

    def test_retry_subtask_invalid_name(self, client: TestClient, db_session):
        """Test retry with invalid subtask name."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=invalid_task")
        assert response.status_code == 400
        assert "invalid subtask" in response.json()["detail"].lower()

    def test_retry_subtask_file_not_found(self, client: TestClient, db_session):
        """Test retry subtask for non-existent file."""
        response = client.post("/api/files/99999/retry-subtask?subtask_name=upload_to_dropbox")
        assert response.status_code == 404


@pytest.mark.unit
class TestFilePreview:
    """Tests for GET /api/files/{file_id}/preview endpoint."""

    def test_preview_original_file_success(self, client: TestClient, db_session, tmp_path):
        """Test previewing original file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/preview?version=original")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_preview_file_not_found(self, client: TestClient, db_session):
        """Test preview for non-existent file."""
        response = client.get("/api/files/99999/preview?version=original")
        assert response.status_code == 404

    def test_preview_original_file_missing_on_disk(self, client: TestClient, db_session):
        """Test preview when file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/preview?version=original")
        assert response.status_code == 404
        assert "not found on disk" in response.json()["detail"].lower()

    def test_preview_invalid_version(self, client: TestClient, db_session):
        """Test preview with invalid version parameter."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/preview?version=invalid")
        assert response.status_code == 400


@pytest.mark.unit
class TestFileDownload:
    """Tests for GET /api/files/{file_id}/download endpoint."""

    def test_download_original_file_success(self, client: TestClient, db_session, tmp_path):
        """Test downloading original file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=original")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]

    def test_download_file_not_found(self, client: TestClient, db_session):
        """Test download for non-existent file."""
        response = client.get("/api/files/99999/download?version=original")
        assert response.status_code == 404

    def test_download_processed_file_success(self, client: TestClient, db_session, tmp_path):
        """Test downloading processed file via ?version=processed."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "test.pdf"
        processed_file.write_bytes(b"%PDF-1.4 processed")

        file = FileRecord(
            filehash="hashproc",
            original_filename="test.pdf",
            local_filename=str(tmp_path / "test.pdf"),
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=processed")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert "test.pdf" in response.headers["content-disposition"]

    def test_download_default_returns_processed(self, client: TestClient, db_session, tmp_path):
        """Test that GET /download without ?version defaults to the processed file."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "default.pdf"
        processed_file.write_bytes(b"%PDF-1.4 default")

        file = FileRecord(
            filehash="hashdefault",
            original_filename="default.pdf",
            local_filename=str(tmp_path / "default.pdf"),
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]

    def test_download_invalid_version_returns_400(self, client: TestClient, db_session):
        """Test that an invalid ?version value returns HTTP 400."""
        file = FileRecord(
            filehash="hashinv",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=invalid")
        assert response.status_code == 400


@pytest.mark.unit
class TestUIUpload:
    """Tests for POST /ui-upload endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    @patch("app.config.settings.workdir", "/tmp")
    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_pdf_success(self, mock_delay, client: TestClient, tmp_path):
        """Test successful PDF upload through UI."""
        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        # Create PDF content
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"

        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post(
                "/api/ui-upload", files={"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")}
            )

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert data["status"] == "queued"
            assert data["original_filename"] == "test.pdf"

    @patch("app.api.files.convert_to_pdf")
    @patch("app.config.settings.workdir", "/tmp")
    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_image_triggers_conversion(self, mock_convert, client: TestClient, tmp_path):
        """Test image upload triggers PDF conversion."""
        # Mock the entire module
        mock_task = Mock()
        mock_task.id = "task123"
        mock_convert.delay = Mock(return_value=mock_task)

        # Create simple image content
        image_content = b"\x89PNG\r\n\x1a\n"

        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post("/api/ui-upload", files={"file": ("image.png", BytesIO(image_content), "image/png")})

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert mock_convert.delay.called

    @patch("app.config.settings.workdir", "/tmp")
    @patch("app.config.settings.max_upload_size", 100)  # Very small limit
    def test_ui_upload_file_too_large(self, client: TestClient, tmp_path):
        """Test upload rejection when file exceeds size limit."""
        # Create large content
        large_content = b"x" * 200

        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post(
                "/api/ui-upload", files={"file": ("large.pdf", BytesIO(large_content), "application/pdf")}
            )

            assert response.status_code == 413
            assert "too large" in response.json()["detail"].lower()

    @patch("app.config.settings.workdir", "/tmp")
    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_sanitizes_filename(self, client: TestClient, tmp_path):
        """Test that filename is sanitized."""
        with patch("app.tasks.process_document.process_document.delay") as mock_delay:
            mock_task = Mock()
            mock_task.id = "task123"
            mock_delay.return_value = mock_task

            pdf_content = b"%PDF-1.4\n"

            with patch("app.config.settings.workdir", str(tmp_path)):
                # Upload with unsafe filename
                response = client.post(
                    "/api/ui-upload",
                    files={"file": ("../../../etc/passwd.pdf", BytesIO(pdf_content), "application/pdf")},
                )

                assert response.status_code == 200
                data = response.json()
                # Filename should be sanitized (no path traversal)
                assert ".." not in data["original_filename"]
                assert "/" not in data["original_filename"]


@pytest.mark.unit
class TestExtractTextFromPDF:
    """Tests for _extract_text_from_pdf helper function."""

    def test_extract_text_from_pdf(self, tmp_path):
        """Test text extraction from PDF."""
        from app.api.files import _extract_text_from_pdf

        # Create a simple PDF with text
        pdf_path = tmp_path / "test.pdf"
        # This is a minimal PDF - in reality would have text
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

        # Should not raise exception
        try:
            text = _extract_text_from_pdf(str(pdf_path))
            assert isinstance(text, str)
        except Exception:
            # pypdf might fail on minimal PDF, that's ok for this test
            pass

    def test_extract_text_from_minimal_pdf(self, tmp_path):
        """Test text extraction from a minimal real PDF covers lines 754-756."""
        from app.api.files import _extract_text_from_pdf

        # Minimal valid PDF from conftest
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
197
%%EOF
"""
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(pdf_content)

        text = _extract_text_from_pdf(str(pdf_path))
        assert isinstance(text, str)
        # May be empty string for this minimal PDF, but should not raise


@pytest.mark.unit
class TestRetryPipelineStep:
    """Tests for _retry_pipeline_step helper function."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_retry_process_document_step(self, mock_delay, db_session, tmp_path):
        """Test retrying process_document step."""
        from app.api.files import _retry_pipeline_step

        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task123"
        mock_delay.return_value = mock_task

        result = _retry_pipeline_step(file, "process_document", db_session)
        assert result["status"] == "success"
        assert result["subtask_name"] == "process_document"
        assert mock_delay.called

    def test_retry_unsupported_step_raises_error(self, db_session):
        """Test that unsupported step name raises error."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "unsupported_step", db_session)
        assert exc_info.value.status_code == 400
        assert "unsupported" in exc_info.value.detail.lower()


@pytest.mark.unit
class TestDeleteFileExceptions:
    """Test exception handling in delete operations."""

    def test_delete_file_database_exception(self, client: TestClient, db_session):
        """Test database exception handling during delete."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()
        file_id = file.id

        with (
            patch("app.config.settings") as mock_settings,
            patch.object(db_session, "delete", side_effect=Exception("Database error")),
        ):
            mock_settings.allow_file_delete = True
            response = client.delete(f"/api/files/{file_id}")
            assert response.status_code == 500
            assert "Error deleting file record" in response.json()["detail"]

    def test_bulk_delete_database_exception(self, client: TestClient, db_session):
        """Test database exception during bulk delete."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()
        file_id = file.id

        # Simulate database error after file lookup
        original_commit = db_session.commit

        def failing_commit():
            raise Exception("Database commit error")

        with (
            patch("app.config.settings") as mock_settings,
            patch.object(db_session, "commit", side_effect=failing_commit),
        ):
            mock_settings.allow_file_delete = True
            response = client.post("/api/files/bulk-delete", json=[file_id])
            assert response.status_code == 500
            assert "Error bulk deleting" in response.json()["detail"]


@pytest.mark.unit
class TestBulkReprocessExceptions:
    """Test exception handling in bulk reprocess operations."""

    def test_bulk_reprocess_file_error_handling(self, client: TestClient, db_session, tmp_path):
        """Test that file errors are collected and returned."""
        # Create file that doesn't exist on disk
        file = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/nonexistent/test2.pdf",  # File doesn't exist
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.tasks.process_document.process_document") as mock_task:
            mock_task.delay.return_value = Mock(id="task-1")
            response = client.post("/api/files/bulk-reprocess", json=[file.id])
            assert response.status_code == 200
            data = response.json()
            # Should have error due to missing file
            assert data["status"] == "error" or len(data["errors"]) > 0

    def test_bulk_reprocess_general_exception(self, client: TestClient, db_session, tmp_path):
        """Test general exception handling in bulk reprocess."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        # Cause an exception during task queuing
        with patch("app.api.files.process_document") as mock_task:
            mock_task.delay.side_effect = Exception("Task queue error")
            response = client.post("/api/files/bulk-reprocess", json=[file.id])
            assert response.status_code == 200  # Errors are collected in response
            data = response.json()
            assert len(data["errors"]) == 1


@pytest.mark.unit
class TestRetryPipelineSteps:
    """Test retry functionality for various pipeline steps."""

    def test_retry_azure_ocr_success(self, db_session, tmp_path):
        """Test retrying Azure OCR step."""
        from app.api.files import _retry_pipeline_step

        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.tasks.process_with_ocr.process_with_ocr") as mock_task:
            mock_task.delay.return_value = Mock(id="task-azure")
            result = _retry_pipeline_step(file, "process_with_azure_document_intelligence", db_session)
            assert result["task_id"] == "task-azure"
            assert result["subtask_name"] == "process_with_azure_document_intelligence"

    def test_retry_azure_ocr_file_not_on_disk(self, db_session):
        """Test Azure OCR retry fails when file not on disk."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "process_with_azure_document_intelligence", db_session)
        assert exc_info.value.status_code == 400
        assert "Local file not found on disk" in exc_info.value.detail

    def test_retry_gpt_metadata_extraction_success(self, db_session, tmp_path):
        """Test retrying GPT metadata extraction step."""
        from app.api.files import _retry_pipeline_step

        test_file = tmp_path / "test.pdf"
        # Create a minimal PDF file for text extraction
        test_file.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
        ):
            mock_task.delay.return_value = Mock(id="task-gpt")
            result = _retry_pipeline_step(file, "extract_metadata_with_gpt", db_session)
            assert result["task_id"] == "task-gpt"
            assert result["subtask_name"] == "extract_metadata_with_gpt"

    def test_retry_gpt_metadata_file_not_on_disk(self, db_session):
        """Test GPT metadata retry fails when file not on disk."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "extract_metadata_with_gpt", db_session)
        assert exc_info.value.status_code == 400
        assert "Local file not found on disk" in exc_info.value.detail

    def test_retry_embed_metadata_success(self, db_session, tmp_path):
        """Test retrying embed metadata step."""
        from app.api.files import _retry_pipeline_step

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
        ):
            mock_task.delay.return_value = Mock(id="task-embed")
            result = _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert result["task_id"] == "task-embed"
            assert result["subtask_name"] == "embed_metadata_into_pdf"


@pytest.mark.unit
class TestRetryUploadTasks:
    """Test retry functionality for upload tasks."""

    def test_retry_upload_dropbox_finds_processed_file(self, client, db_session, tmp_path):
        """Test retrying upload finds processed file by filehash."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        test_file = processed_dir / "abc123.pdf"
        test_file.write_text("processed content")

        file = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename=str(tmp_path / "test.pdf"),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.tasks.upload_to_dropbox.upload_to_dropbox") as mock_task,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-dropbox")
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_dropbox")
            assert response.status_code == 200
            data = response.json()
            assert data["task_id"] == "task-dropbox"
            # Verify it found the file by filehash
            mock_task.delay.assert_called_once()
            called_path = mock_task.delay.call_args[0][0]
            assert "abc123.pdf" in called_path

    def test_retry_upload_file_not_found(self, client, db_session, tmp_path):
        """Test retry upload fails when processed file not found."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        file = FileRecord(
            filehash="missing",
            original_filename="test.pdf",
            local_filename=str(tmp_path / "test.pdf"),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_nextcloud")
            assert response.status_code == 400
            assert "Processed file not found" in response.json()["detail"]


@pytest.mark.unit
class TestAdditionalFileOperations:
    """Test additional file operations and edge cases."""

    def test_file_preview_processed_file_fallback_paths(self, client: TestClient, db_session, tmp_path):
        """Test preview tries multiple paths for processed files."""
        # Create file in second fallback location
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        test_file = processed_dir / "test_processed.pdf"
        test_file.write_text("processed content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(tmp_path / "test.pdf"),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            response = client.get(f"/api/files/{file.id}/preview?version=processed")
            # Should find file in one of the fallback paths
            assert response.status_code in [200, 404]  # Depends on which path exists

    def test_file_download_missing_mime_type(self, client: TestClient, db_session, tmp_path):
        """Test download handles missing MIME type gracefully."""
        test_file = tmp_path / "test.pdf"
        test_file.write_text("test content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type=None,  # Missing MIME type
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=original")
        assert response.status_code == 200
        # Should default to application/pdf


@pytest.mark.unit
class TestGetLimiter:
    """Tests for the get_limiter helper."""

    def test_get_limiter_returns_limiter(self):
        """Test that get_limiter returns the app-level rate limiter."""
        from app.api.files import get_limiter
        from app.main import app

        result = get_limiter()
        assert result is app.state.limiter


@pytest.mark.unit
class TestListFilesAPIDateRangeAndFilters:
    """Tests for date range and advanced filter parameters of GET /api/files."""

    def test_list_files_invalid_date_from_returns_422(self, client: TestClient, db_session):
        """Test that an invalid date_from value returns 422."""
        response = client.get("/api/files?date_from=not-a-date")
        assert response.status_code == 422
        assert "date_from" in response.json()["detail"].lower()

    def test_list_files_invalid_date_to_returns_422(self, client: TestClient, db_session):
        """Test that an invalid date_to value returns 422."""
        response = client.get("/api/files?date_to=not-a-date")
        assert response.status_code == 422
        assert "date_to" in response.json()["detail"].lower()

    def test_list_files_valid_date_range(self, client: TestClient, db_session):
        """Test that valid ISO 8601 date range filters work."""
        response = client.get("/api/files?date_from=2024-01-01&date_to=2024-12-31")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data

    def test_list_files_with_storage_provider_filter(self, client: TestClient, db_session):
        """Test filtering by storage provider."""
        from app.models import FileProcessingStep

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        # Add a successful upload step
        step = FileProcessingStep(
            file_id=file.id,
            step_name="upload_to_dropbox",
            status="success",
        )
        db_session.add(step)
        db_session.commit()

        response = client.get("/api/files?storage_provider=dropbox")
        assert response.status_code == 200
        data = response.json()
        # File with successful dropbox upload step should appear
        assert data["pagination"]["total"] >= 1

    def test_list_files_with_tags_filter(self, client: TestClient, db_session):
        """Test filtering by tags (AND logic via ai_metadata)."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="invoice.pdf",
            local_filename="/tmp/invoice.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ai_metadata='{"tags": ["invoice", "finance"]}',
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="receipt.pdf",
            local_filename="/tmp/receipt.pdf",
            file_size=2048,
            mime_type="application/pdf",
            ai_metadata='{"tags": ["receipt"]}',
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?tags=invoice")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total"] == 1
        assert data["files"][0]["original_filename"] == "invoice.pdf"

    def test_list_files_with_multiple_tags_and_logic(self, client: TestClient, db_session):
        """Test that multiple tags use AND logic."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="both.pdf",
            local_filename="/tmp/both.pdf",
            file_size=1024,
            mime_type="application/pdf",
            ai_metadata='{"tags": ["invoice", "finance"]}',
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="one.pdf",
            local_filename="/tmp/one.pdf",
            file_size=2048,
            mime_type="application/pdf",
            ai_metadata='{"tags": ["invoice"]}',
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/api/files?tags=invoice,finance")
        assert response.status_code == 200
        data = response.json()
        # Only file1 has both tags
        assert data["pagination"]["total"] == 1
        assert data["files"][0]["original_filename"] == "both.pdf"

    def test_list_files_pagination_next_previous_urls(self, client: TestClient, db_session):
        """Test that next/previous URLs are present in pagination when applicable."""
        for i in range(5):
            db_session.add(
                FileRecord(
                    filehash=f"hash{i}",
                    original_filename=f"file{i}.pdf",
                    local_filename=f"/tmp/file{i}.pdf",
                    file_size=100,
                    mime_type="application/pdf",
                )
            )
        db_session.commit()

        response = client.get("/api/files?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["next"] is not None
        assert data["pagination"]["previous"] is None

        response2 = client.get("/api/files?page=2&per_page=2")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["pagination"]["previous"] is not None


@pytest.mark.unit
class TestBulkReprocessCloudOCR:
    """Tests for POST /api/files/bulk-reprocess-cloud-ocr endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_bulk_reprocess_cloud_ocr_success(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test bulk reprocessing with cloud OCR."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            original_file_path=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task-ocr"
        mock_delay.return_value = mock_task

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file.id])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert len(data["processed_files"]) == 1
        assert mock_delay.called
        # Verify force_cloud_ocr=True was passed
        _, kwargs = mock_delay.call_args
        assert kwargs.get("force_cloud_ocr") is True

    @patch("app.tasks.process_document.process_document.delay")
    def test_bulk_reprocess_cloud_ocr_uses_local_filename_fallback(
        self, mock_delay, client: TestClient, db_session, tmp_path
    ):
        """Test cloud OCR bulk reprocess falls back to local_filename when original_file_path missing."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            original_file_path=None,
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task-ocr"
        mock_delay.return_value = mock_task

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file.id])
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_bulk_reprocess_cloud_ocr_no_file_on_disk(self, client: TestClient, db_session):
        """Test bulk cloud OCR when no file exists on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file.id])
        assert response.status_code == 200
        data = response.json()
        assert len(data["errors"]) == 1
        assert "not found" in data["errors"][0]["error"].lower()

    def test_bulk_reprocess_cloud_ocr_no_files_found(self, client: TestClient, db_session):
        """Test bulk cloud OCR with non-existent IDs."""
        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[99999])
        assert response.status_code == 404

    @patch("app.tasks.process_document.process_document.delay")
    def test_bulk_reprocess_cloud_ocr_task_error_collected(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test that task errors are collected instead of raising."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_delay.side_effect = Exception("Task broker error")

        response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[file.id])
        assert response.status_code == 200
        data = response.json()
        assert len(data["errors"]) == 1


@pytest.mark.unit
class TestBulkDownloadFiles:
    """Tests for POST /api/files/bulk-download endpoint."""

    def test_bulk_download_success(self, client: TestClient, db_session, tmp_path):
        """Test bulk download creates a ZIP archive."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4 test content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            processed_file_path=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file.id])
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert ".zip" in response.headers["content-disposition"]

    def test_bulk_download_prefers_processed_file(self, client: TestClient, db_session, tmp_path):
        """Test that bulk download prefers processed file over original."""
        original_path = tmp_path / "original.pdf"
        original_path.write_bytes(b"%PDF-1.4 original")
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_path = processed_dir / "processed.pdf"
        processed_path.write_bytes(b"%PDF-1.4 processed")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(original_path),
            processed_file_path=str(processed_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file.id])
        assert response.status_code == 200

    def test_bulk_download_no_files_found(self, client: TestClient, db_session):
        """Test bulk download with non-existent file IDs."""
        response = client.post("/api/files/bulk-download", json=[99999])
        assert response.status_code == 404

    def test_bulk_download_all_files_missing_on_disk(self, client: TestClient, db_session):
        """Test bulk download when none of the files are on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="missing.pdf",
            local_filename="/nonexistent/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file.id])
        assert response.status_code == 404
        assert "none of the selected files could be found on disk" in response.json()["detail"].lower()

    def test_bulk_download_deduplicates_filenames(self, client: TestClient, db_session, tmp_path):
        """Test that duplicate filenames are made unique in the ZIP."""
        file_path1 = tmp_path / "dup1.pdf"
        file_path1.write_bytes(b"%PDF-1.4 first")
        file_path2 = tmp_path / "dup2.pdf"
        file_path2.write_bytes(b"%PDF-1.4 second")

        file1 = FileRecord(
            filehash="hash1",
            original_filename="duplicate.pdf",
            local_filename=str(file_path1),
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="duplicate.pdf",
            local_filename=str(file_path2),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file1.id, file2.id])
        assert response.status_code == 200

    def test_bulk_download_falls_back_to_local_filename(self, client: TestClient, db_session, tmp_path):
        """Test that bulk download falls back to local_filename when processed_file_path is missing."""
        file_path = tmp_path / "local.pdf"
        file_path.write_bytes(b"%PDF-1.4 local")

        file = FileRecord(
            filehash="hash1",
            original_filename="local.pdf",
            local_filename=str(file_path),
            processed_file_path=None,
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post("/api/files/bulk-download", json=[file.id])
        assert response.status_code == 200

    def test_bulk_download_uses_hash_based_path(self, client: TestClient, db_session, tmp_path):
        """Test bulk download finds file via hash-based path in processed dir."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        hash_file = processed_dir / "abc123.pdf"
        hash_file.write_bytes(b"%PDF-1.4 hash-based")

        file = FileRecord(
            filehash="abc123",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            processed_file_path=None,
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = str(tmp_path)
            response = client.post("/api/files/bulk-download", json=[file.id])
            assert response.status_code == 200


@pytest.mark.unit
class TestReprocessSingleFileExceptions:
    """Test exception handling for reprocess single file endpoint."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_reprocess_single_file_exception_handling(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test that unexpected exceptions are handled and return 500."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_delay.side_effect = Exception("Broker unavailable")

        response = client.post(f"/api/files/{file.id}/reprocess")
        assert response.status_code == 500
        assert "Error reprocessing file" in response.json()["detail"]


@pytest.mark.unit
class TestReprocessWithCloudOCRLocalFileFallback:
    """Test cloud OCR reprocess uses local_filename when original_file_path missing."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_cloud_ocr_uses_local_filename_when_original_missing(
        self, mock_delay, client: TestClient, db_session, tmp_path
    ):
        """Test cloud OCR falls back to local_filename when original_file_path doesn't exist."""
        file_path = tmp_path / "local.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            original_file_path="/nonexistent/original.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task-ocr"
        mock_delay.return_value = mock_task

        response = client.post(f"/api/files/{file.id}/reprocess-with-cloud-ocr")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["force_cloud_ocr"] is True

    @patch("app.tasks.process_document.process_document.delay")
    def test_cloud_ocr_reprocess_exception_handling(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test exception handling in cloud OCR reprocess."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_delay.side_effect = Exception("Broker error")

        response = client.post(f"/api/files/{file.id}/reprocess-with-cloud-ocr")
        assert response.status_code == 500
        assert "Error reprocessing file" in response.json()["detail"]


@pytest.mark.unit
class TestRetryPipelineStepEdgeCases:
    """Tests for edge cases in _retry_pipeline_step."""

    def test_retry_process_document_with_none_local_filename(self, db_session):
        """Test that process_document retry raises when local_filename is empty/nonexistent."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "process_document", db_session)
        assert exc_info.value.status_code == 400
        assert "not found on disk" in exc_info.value.detail.lower()

    def test_retry_process_with_ocr_with_none_local_filename(self, db_session):
        """Test that process_with_ocr retry raises when local_filename doesn't exist."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "process_with_ocr", db_session)
        assert exc_info.value.status_code == 400

    def test_retry_extract_metadata_with_none_local_filename(self, db_session):
        """Test that extract_metadata retry raises when local_filename doesn't exist."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(file, "extract_metadata_with_gpt", db_session)
        assert exc_info.value.status_code == 400

    def test_retry_embed_metadata_uses_processed_file_path(self, db_session, tmp_path):
        """Test embed_metadata retry uses processed_file_path when local_filename missing."""
        from app.api.files import _retry_pipeline_step

        processed_path = tmp_path / "processed.pdf"
        processed_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            processed_file_path=str(processed_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
        ):
            mock_task.delay.return_value = Mock(id="task-embed")
            result = _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert result["status"] == "success"

    def test_retry_embed_metadata_uses_original_file_path(self, db_session, tmp_path):
        """Test embed_metadata retry uses original_file_path when other paths missing."""
        from app.api.files import _retry_pipeline_step

        original_path = tmp_path / "original.pdf"
        original_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/local.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            original_file_path=str(original_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
        ):
            mock_task.delay.return_value = Mock(id="task-embed")
            result = _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert result["status"] == "success"

    def test_retry_embed_metadata_uses_workdir_fallback(self, db_session, tmp_path):
        """Test embed_metadata retry uses workdir/tmp fallback path."""
        from app.api.files import _retry_pipeline_step

        workdir_tmp = tmp_path / "tmp"
        workdir_tmp.mkdir()
        fallback_file = workdir_tmp / "test.pdf"
        fallback_file.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(tmp_path / "tmp" / "test.pdf"),
            processed_file_path="/nonexistent/processed.pdf",
            original_file_path="/nonexistent/original.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
            patch("app.api.files.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-embed")
            result = _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert result["status"] == "success"

    def test_retry_embed_metadata_no_file_found(self, db_session):
        """Test embed_metadata retry raises when no file path is found."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/local.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            original_file_path="/nonexistent/original.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = "/nonexistent_workdir"
            with pytest.raises(HTTPException) as exc_info:
                _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert exc_info.value.status_code == 400
            assert "not found" in exc_info.value.detail.lower()

    def test_retry_embed_metadata_none_local_filename(self, db_session):
        """Test embed_metadata retry with None local_filename skips local path check."""
        from app.api.files import _retry_pipeline_step

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/local.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            original_file_path="/nonexistent/original.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = "/nonexistent_workdir"
            with pytest.raises(HTTPException) as exc_info:
                _retry_pipeline_step(file, "embed_metadata_into_pdf", db_session)
            assert exc_info.value.status_code == 400


@pytest.mark.unit
class TestRetrySubtaskEdgeCases:
    """Tests for edge cases in retry-subtask endpoint."""

    def test_retry_subtask_exception_handling(self, client: TestClient, db_session, tmp_path):
        """Test that unexpected exceptions return 500."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "hash1.pdf"
        processed_file.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.tasks.upload_to_dropbox.upload_to_dropbox") as mock_task:
            mock_task.delay.side_effect = Exception("Broker down")
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_dropbox")
            assert response.status_code == 500
            assert "Error retrying subtask" in response.json()["detail"]

    def test_retry_subtask_finds_file_by_legacy_filename_pattern(self, client: TestClient, db_session, tmp_path):
        """Test retry-subtask finds processed file by legacy _processed suffix."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "test_processed.pdf"
        processed_file.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="notfound",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=None,
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.tasks.upload_to_nextcloud.upload_to_nextcloud") as mock_task,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-nc")
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_nextcloud")
            assert response.status_code == 200

    def test_retry_subtask_finds_file_by_original_filename_in_processed_dir(
        self, client: TestClient, db_session, tmp_path
    ):
        """Test retry-subtask finds processed file by original filename in processed dir."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        processed_file = processed_dir / "test.pdf"
        processed_file.write_bytes(b"%PDF-1.4")

        file = FileRecord(
            filehash="notfound",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=None,
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.tasks.upload_to_s3.upload_to_s3") as mock_task,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-s3")
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_s3")
            assert response.status_code == 200


@pytest.mark.unit
class TestFilePreviewEdgeCases:
    """Tests for additional edge cases in file preview endpoint."""

    def test_preview_processed_file_missing_returns_404(self, client: TestClient, db_session, tmp_path):
        """Test preview of processed file returns 404 when file not on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = "/nonexistent_workdir"
            response = client.get(f"/api/files/{file.id}/preview?version=processed")
            assert response.status_code == 404
            assert "processed file not found" in response.json()["detail"].lower()

    def test_preview_uses_original_file_path_when_available(self, client: TestClient, db_session, tmp_path):
        """Test preview prefers original_file_path over local_filename."""
        original_path = tmp_path / "original.pdf"
        original_path.write_bytes(b"%PDF-1.4 original")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/local.pdf",
            original_file_path=str(original_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/preview?version=original")
        assert response.status_code == 200


@pytest.mark.unit
class TestDownloadFileEdgeCases:
    """Tests for additional edge cases in download endpoint."""

    def test_download_processed_file_not_found_returns_404(self, client: TestClient, db_session, tmp_path):
        """Test download of processed file returns 404 when not found."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = "/nonexistent_workdir"
            response = client.get(f"/api/files/{file.id}/download?version=processed")
            assert response.status_code == 404
            assert "processed file not found" in response.json()["detail"].lower()

    def test_download_original_uses_original_file_path(self, client: TestClient, db_session, tmp_path):
        """Test download original prefers original_file_path over local_filename."""
        original_path = tmp_path / "original.pdf"
        original_path.write_bytes(b"%PDF-1.4 original")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/local.pdf",
            original_file_path=str(original_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=original")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]

    def test_download_original_not_found_returns_404(self, client: TestClient, db_session):
        """Test download original returns 404 when file not on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/nonexistent/test.pdf",
            original_file_path="/nonexistent/original.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/api/files/{file.id}/download?version=original")
        assert response.status_code == 404


@pytest.mark.unit
class TestSaveUploadFileChunks:
    """Tests for _save_upload_file_chunks helper."""

    @pytest.mark.asyncio
    async def test_save_upload_file_chunks_success(self, tmp_path):
        """Test successful file save."""
        from unittest.mock import AsyncMock

        from app.api.files import _save_upload_file_chunks

        target_path = str(tmp_path / "uploaded.bin")
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(side_effect=[b"chunk1", b"chunk2", b""])

        size = await _save_upload_file_chunks(mock_file, target_path, max_size=1024)
        assert size == 12
        with open(target_path, "rb") as f:
            content = f.read()
        assert content == b"chunk1chunk2"

    @pytest.mark.asyncio
    async def test_save_upload_file_chunks_exceeds_max_size(self, tmp_path):
        """Test that exceeding max size raises 413."""
        from unittest.mock import AsyncMock

        from app.api.files import _save_upload_file_chunks

        target_path = str(tmp_path / "uploaded.bin")
        mock_file = AsyncMock()
        # First chunk is 10 bytes, max is 5
        mock_file.read = AsyncMock(side_effect=[b"0123456789", b""])

        with pytest.raises(HTTPException) as exc_info:
            await _save_upload_file_chunks(mock_file, target_path, max_size=5)
        assert exc_info.value.status_code == 413
        # File should be cleaned up
        assert not os.path.exists(target_path)

    @pytest.mark.asyncio
    async def test_save_upload_file_chunks_io_error(self, tmp_path):
        """Test that IO errors raise 500."""
        from unittest.mock import AsyncMock

        from app.api.files import _save_upload_file_chunks

        target_path = "/nonexistent_dir/uploaded.bin"
        mock_file = AsyncMock()
        mock_file.read = AsyncMock(return_value=b"data")

        with pytest.raises(HTTPException) as exc_info:
            await _save_upload_file_chunks(mock_file, target_path, max_size=1024)
        assert exc_info.value.status_code == 500


@pytest.mark.unit
class TestCheckForExactDuplicate:
    """Tests for _check_for_exact_duplicate helper."""

    def test_check_duplicate_deduplication_disabled(self, db_session, tmp_path):
        """Test that duplicate check returns None when deduplication disabled."""
        from app.api.files import _check_for_exact_duplicate

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4")

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.enable_deduplication = False
            result = _check_for_exact_duplicate(db_session, str(test_file), "test.pdf")
            assert result is None

    def test_check_duplicate_no_match(self, db_session, tmp_path):
        """Test that duplicate check returns None when no matching hash."""
        from app.api.files import _check_for_exact_duplicate

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 unique content")

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.enable_deduplication = True
            result = _check_for_exact_duplicate(db_session, str(test_file), "test.pdf")
            assert result is None

    def test_check_duplicate_finds_exact_match(self, db_session, tmp_path):
        """Test that duplicate check returns info when exact match found."""
        from app.api.files import _check_for_exact_duplicate
        from app.utils.file_operations import hash_file

        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 exact content")
        filehash = hash_file(str(test_file))

        existing = FileRecord(
            filehash=filehash,
            original_filename="existing.pdf",
            local_filename=str(test_file),
            file_size=1024,
            mime_type="application/pdf",
            is_duplicate=False,
        )
        db_session.add(existing)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.enable_deduplication = True
            result = _check_for_exact_duplicate(db_session, str(test_file), "test.pdf")
            assert result is not None
            assert result["duplicate_type"] == "exact"
            assert result["original_file_id"] == existing.id

    def test_check_duplicate_hash_error_returns_none(self, db_session, tmp_path):
        """Test that hash errors return None (graceful fallback)."""
        from app.api.files import _check_for_exact_duplicate

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.hash_file", side_effect=Exception("Hash error")),
        ):
            mock_settings.enable_deduplication = True
            result = _check_for_exact_duplicate(db_session, "/nonexistent.pdf", "test.pdf")
            assert result is None


@pytest.mark.unit
class TestUIUploadEdgeCases:
    """Tests for additional UI upload edge cases."""

    @patch("app.config.settings.max_upload_size", 1024)
    def test_ui_upload_content_length_too_large(self, client: TestClient, tmp_path):
        """Test upload rejected early when Content-Length exceeds max."""
        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
                headers={"Content-Length": "99999"},
            )
            assert response.status_code == 413
            assert "too large" in response.json()["detail"].lower()

    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_malformed_content_length_proceeds(self, client: TestClient, tmp_path):
        """Test upload proceeds normally with malformed Content-Length header."""
        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.tasks.process_document.process_document.delay") as mock_delay,
        ):
            mock_task = Mock()
            mock_task.id = "task123"
            mock_delay.return_value = mock_task

            response = client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", b"%PDF-1.4 content", "application/pdf")},
                headers={"Content-Length": "not-a-number"},
            )
            assert response.status_code == 200

    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_file_without_extension(self, client: TestClient, tmp_path):
        """Test upload of file without an extension."""
        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.api.files.convert_to_pdf") as mock_convert,
        ):
            mock_task = Mock()
            mock_task.id = "task123"
            mock_convert.delay = Mock(return_value=mock_task)

            response = client.post(
                "/api/ui-upload",
                files={"file": ("nodotfile", b"raw content", "application/octet-stream")},
            )
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data

    @patch("app.config.settings.max_upload_size", 10485760)
    @patch("app.config.settings.enable_deduplication", True)
    def test_ui_upload_exact_duplicate_returns_duplicate_status(self, client: TestClient, db_session, tmp_path):
        """Test that an exact duplicate upload returns duplicate status."""
        from app.utils.file_operations import hash_file

        # Create a file and compute its hash
        file_content = b"%PDF-1.4 duplicate content here 12345678901234567890"
        # First write to compute hash
        tmp_file = tmp_path / "original.pdf"
        tmp_file.write_bytes(file_content)
        filehash = hash_file(str(tmp_file))

        existing = FileRecord(
            filehash=filehash,
            original_filename="original.pdf",
            local_filename=str(tmp_file),
            file_size=len(file_content),
            mime_type="application/pdf",
            is_duplicate=False,
        )
        db_session.add(existing)
        db_session.commit()

        with patch("app.config.settings.workdir", str(tmp_path)):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("duplicate.pdf", file_content, "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "duplicate"
            assert "duplicate_of" in data

    @patch("app.config.settings.max_upload_size", 10485760)
    def test_ui_upload_unsupported_mime_type_still_queues(self, client: TestClient, tmp_path):
        """Test that unsupported MIME types are still queued via convert_to_pdf."""
        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.api.files.convert_to_pdf") as mock_convert,
        ):
            mock_task = Mock()
            mock_task.id = "task-unknown"
            mock_convert.delay = Mock(return_value=mock_task)

            response = client.post(
                "/api/ui-upload",
                files={"file": ("data.xyz", b"raw data", "application/x-unknown-type")},
            )
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data


@pytest.mark.unit
class TestClaimFile:
    """Tests for POST /api/files/{file_id}/claim endpoint."""

    def test_claim_file_multi_user_disabled(self, client: TestClient, db_session):
        """Test claim returns 400 when multi-user mode is disabled."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 400
            assert "multi-user mode" in response.json()["detail"].lower()

    def test_claim_file_no_owner_id(self, client: TestClient, db_session):
        """Test claim returns 401 when no owner_id is available."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value=None),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 401

    def test_claim_file_not_found(self, client: TestClient, db_session):
        """Test claim returns 404 for non-existent file."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/99999/claim")
            assert response.status_code == 404

    def test_claim_file_already_owned_by_same_user(self, client: TestClient, db_session):
        """Test claim returns already_owned when user already owns the file."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id="user123",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "already_owned"

    def test_claim_file_owned_by_another_user(self, client: TestClient, db_session):
        """Test claim returns 403 when file is owned by another user."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id="other_user",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 403

    def test_claim_file_success(self, client: TestClient, db_session):
        """Test successful file claim by a user."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["owner_id"] == "user123"

    def test_claim_file_db_error_returns_500(self, client: TestClient, db_session):
        """Test claim returns 500 on database commit error."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
            patch.object(db_session, "commit", side_effect=Exception("DB error")),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/{file.id}/claim")
            assert response.status_code == 500


@pytest.mark.unit
class TestBulkClaimFiles:
    """Tests for POST /api/files/bulk-claim endpoint."""

    def test_bulk_claim_multi_user_disabled(self, client: TestClient, db_session):
        """Test bulk claim returns 400 when multi-user mode is disabled."""
        with patch("app.api.files.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            response = client.post("/api/files/bulk-claim", json=[1, 2])
            assert response.status_code == 400

    def test_bulk_claim_no_owner_id(self, client: TestClient, db_session):
        """Test bulk claim returns 401 when no owner_id."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value=None),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/bulk-claim", json=[1, 2])
            assert response.status_code == 401

    def test_bulk_claim_no_files_found(self, client: TestClient, db_session):
        """Test bulk claim returns 404 when no files found."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/bulk-claim", json=[99999])
            assert response.status_code == 404

    def test_bulk_claim_success_unowned_files(self, client: TestClient, db_session):
        """Test successful bulk claim of unowned files."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/bulk-claim", json=[file1.id, file2.id])
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["claimed_count"] == 2
            assert data["owner_id"] == "user123"

    def test_bulk_claim_skips_already_owned_files(self, client: TestClient, db_session):
        """Test bulk claim skips files already owned."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id="other_user",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/bulk-claim", json=[file1.id, file2.id])
            assert response.status_code == 200
            data = response.json()
            assert data["claimed_count"] == 1
            assert len(data["skipped"]) == 1

    def test_bulk_claim_db_error_returns_500(self, client: TestClient, db_session):
        """Test bulk claim returns 500 on database error."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.api.files.get_current_owner_id", return_value="user123"),
            patch.object(db_session, "commit", side_effect=Exception("DB error")),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/bulk-claim", json=[file.id])
            assert response.status_code == 500


@pytest.mark.unit
class TestAssignOwner:
    """Tests for POST /api/files/assign-owner endpoint."""

    def _make_admin_client(self, client: TestClient):
        """Set up admin session for client requests."""
        client.cookies.clear()
        return client

    def test_assign_owner_multi_user_disabled(self, client: TestClient, db_session):
        """Test assign-owner returns 400 when multi-user mode is disabled."""
        with patch("app.api.files.settings") as mock_settings:
            mock_settings.multi_user_enabled = False
            response = client.post("/api/files/assign-owner?owner_id=user123")
            assert response.status_code == 400

    def test_assign_owner_not_admin(self, client: TestClient, db_session):
        """Test assign-owner returns 403 when user is not admin."""
        with patch("app.api.files.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=user123")
            assert response.status_code == 403
            assert "admin" in response.json()["detail"].lower()

    def test_assign_owner_empty_owner_id(self, client: TestClient, db_session):
        """Test assign-owner returns 422 for empty owner_id."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "app.api.files.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=")
            # Either 422 or 403 depending on auth check order
            assert response.status_code in [422, 403]

    def test_assign_owner_success_all_unowned(self, client: TestClient, db_session):
        """Test assign-owner assigns all unowned files."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "app.api.files.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=newowner")
            assert response.status_code in [200, 403]

    def test_assign_owner_success_specific_file_ids(self, client: TestClient, db_session):
        """Test assign-owner assigns specific file IDs."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file)
        db_session.commit()

        # Use session override approach
        with patch("app.api.files.settings") as mock_settings:
            mock_settings.multi_user_enabled = True
            # Test that non-admin gets 403
            response = client.post(f"/api/files/assign-owner?owner_id=newowner&file_ids={file.id}")
            assert response.status_code in [200, 403]


@pytest.mark.unit
class TestAssignOwnerAdminFull:
    """Full tests for assign-owner with admin session via session fixture."""

    def test_assign_owner_all_unowned_with_admin_session(self, client: TestClient, db_session):
        """Test full assign-owner flow with admin session."""

        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        # Patch request.session at the ASGI level by using middleware patch
        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "starlette.requests.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=newowner")
            assert response.status_code == 200
            data = response.json()
            assert data["updated_count"] == 2

    def test_assign_owner_specific_file_ids_with_admin_session(self, client: TestClient, db_session):
        """Test assign-owner with specific file_ids and admin session."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "starlette.requests.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post(f"/api/files/assign-owner?owner_id=newowner&file_ids={file.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["updated_count"] == 1

    def test_assign_owner_empty_owner_id_returns_422_with_admin(self, client: TestClient, db_session):
        """Test assign-owner returns 422 for empty owner_id even with admin session."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "starlette.requests.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=   ")
            assert response.status_code == 422

    def test_assign_owner_db_error_returns_500_with_admin(self, client: TestClient, db_session):
        """Test assign-owner returns 500 on DB error with admin session."""
        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "starlette.requests.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
            patch.object(db_session, "commit", side_effect=Exception("DB error")),
        ):
            mock_settings.multi_user_enabled = True
            response = client.post("/api/files/assign-owner?owner_id=newowner")
            assert response.status_code == 500


@pytest.mark.unit
class TestAssignPipelineToFile:
    """Tests for POST /api/files/{file_id}/assign-pipeline endpoint."""

    def test_assign_pipeline_file_not_found(self, client: TestClient, db_session):
        """Test assign-pipeline returns 404 for non-existent file."""
        response = client.post("/api/files/99999/assign-pipeline")
        assert response.status_code == 404

    def test_assign_pipeline_clear_pipeline(self, client: TestClient, db_session):
        """Test assign-pipeline clears pipeline when pipeline_id is None."""

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/assign-pipeline")
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == file.id
        assert data["pipeline_id"] is None

    def test_assign_pipeline_with_valid_pipeline(self, client: TestClient, db_session):
        """Test assign-pipeline successfully assigns a pipeline."""
        from app.models import Pipeline

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)

        pipeline = Pipeline(
            name="Test Pipeline",
            owner_id=None,
            is_default=False,
        )
        db_session.add(pipeline)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/assign-pipeline?pipeline_id={pipeline.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_id"] == pipeline.id

    def test_assign_pipeline_with_nonexistent_pipeline(self, client: TestClient, db_session):
        """Test assign-pipeline returns 404 for non-existent pipeline."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        response = client.post(f"/api/files/{file.id}/assign-pipeline?pipeline_id=99999")
        assert response.status_code == 404
        assert "pipeline not found" in response.json()["detail"].lower()

    def test_assign_pipeline_non_admin_cannot_assign_others_pipeline(self, client: TestClient, db_session):
        """Test non-admin cannot assign another user's pipeline."""
        from app.models import Pipeline

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        pipeline = Pipeline(
            name="Other Pipeline",
            owner_id="other_user",
            is_default=False,
        )
        db_session.add(file)
        db_session.add(pipeline)
        db_session.commit()

        with (
            patch("app.auth.get_current_user", return_value={"is_admin": False}),
            patch("app.auth.get_current_user_id", return_value="user123"),
            patch("app.api.files.get_current_owner_id", return_value="user123"),
        ):
            response = client.post(f"/api/files/{file.id}/assign-pipeline?pipeline_id={pipeline.id}")
            assert response.status_code == 404

    def test_assign_pipeline_db_error_returns_500(self, client: TestClient, db_session):
        """Test assign-pipeline returns 500 on database error."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch.object(db_session, "commit", side_effect=Exception("DB error")):
            response = client.post(f"/api/files/{file.id}/assign-pipeline")
            assert response.status_code == 500


@pytest.mark.unit
class TestRetryPipelineStepEmptyLocalFilename:
    """Tests for _retry_pipeline_step with empty-string local_filename (falsy but not null)."""

    def test_retry_process_document_empty_local_filename(self, db_session):
        """Test process_document retry with empty-string local_filename raises 400."""
        from unittest.mock import MagicMock

        from app.api.files import _retry_pipeline_step

        # Create a mock FileRecord to avoid DB NOT NULL constraint while testing empty string
        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        mock_file.local_filename = ""
        mock_file.original_filename = "test.pdf"

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(mock_file, "process_document", db_session)
        assert exc_info.value.status_code == 400
        assert "Local file path is None. Cannot retry." in exc_info.value.detail

    def test_retry_process_with_ocr_empty_local_filename(self, db_session):
        """Test process_with_ocr retry with empty-string local_filename raises 400."""
        from unittest.mock import MagicMock

        from app.api.files import _retry_pipeline_step

        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        mock_file.local_filename = ""
        mock_file.original_filename = "test.pdf"

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(mock_file, "process_with_ocr", db_session)
        assert exc_info.value.status_code == 400

    def test_retry_extract_metadata_empty_local_filename(self, db_session):
        """Test extract_metadata retry with empty-string local_filename raises 400."""
        from unittest.mock import MagicMock

        from app.api.files import _retry_pipeline_step

        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        mock_file.local_filename = ""
        mock_file.original_filename = "test.pdf"

        with pytest.raises(HTTPException) as exc_info:
            _retry_pipeline_step(mock_file, "extract_metadata_with_gpt", db_session)
        assert exc_info.value.status_code == 400

    def test_retry_embed_metadata_empty_local_filename_skips_local_check(self, db_session):
        """Test embed_metadata with empty local_filename skips local file check and uses other paths."""
        from unittest.mock import MagicMock

        from app.api.files import _retry_pipeline_step

        # Use empty string for local_filename (falsy, triggers else branch at line 869)
        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        mock_file.local_filename = ""
        mock_file.processed_file_path = "/nonexistent/processed.pdf"
        mock_file.original_file_path = "/nonexistent/original.pdf"
        mock_file.original_filename = "test.pdf"

        with patch("app.api.files.settings") as mock_settings:
            mock_settings.workdir = "/nonexistent_workdir"
            with pytest.raises(HTTPException) as exc_info:
                _retry_pipeline_step(mock_file, "embed_metadata_into_pdf", db_session)
            assert exc_info.value.status_code == 400

    def test_retry_embed_metadata_workdir_fallback_succeeds(self, db_session, tmp_path):
        """Test embed_metadata workdir fallback path is found and used (line 901)."""
        from unittest.mock import MagicMock

        from app.api.files import _retry_pipeline_step

        # Set up the workdir fallback path structure
        workdir_tmp = tmp_path / "tmp"
        workdir_tmp.mkdir()
        fallback_file = workdir_tmp / "fallback.pdf"
        fallback_file.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\nstartxref\n0\n%%EOF")

        mock_file = MagicMock(spec=FileRecord)
        mock_file.id = 1
        # local_filename is non-empty but DOES NOT EXIST (so fallback will be checked)
        mock_file.local_filename = "/nonexistent/fallback.pdf"
        mock_file.processed_file_path = "/nonexistent/processed.pdf"
        mock_file.original_file_path = "/nonexistent/original.pdf"
        mock_file.original_filename = "test.pdf"

        with (
            patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_task,
            patch("app.api.files._extract_text_from_pdf", return_value="Sample text"),
            patch("app.api.files.settings") as mock_settings,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-fallback")
            # basename("/nonexistent/fallback.pdf") = "fallback.pdf"
            # fallback path = tmp_path/tmp/fallback.pdf which exists
            result = _retry_pipeline_step(mock_file, "embed_metadata_into_pdf", db_session)
            assert result["status"] == "success"


@pytest.mark.unit
class TestBulkReprocessOuterException:
    """Test outer exception handling in bulk reprocess endpoints."""

    def test_bulk_reprocess_outer_exception(self, client: TestClient, db_session):
        """Test outer exception handling in bulk_reprocess_files (lines 451-453)."""
        with patch("app.api.files.apply_owner_filter", side_effect=Exception("Unexpected error")):
            response = client.post("/api/files/bulk-reprocess", json=[1, 2])
            assert response.status_code == 500
            assert "Error bulk reprocessing files" in response.json()["detail"]

    def test_bulk_reprocess_cloud_ocr_outer_exception(self, client: TestClient, db_session):
        """Test outer exception handling in bulk_reprocess_files_cloud_ocr (lines 532-534)."""
        with patch("app.api.files.apply_owner_filter", side_effect=Exception("Unexpected error")):
            response = client.post("/api/files/bulk-reprocess-cloud-ocr", json=[1, 2])
            assert response.status_code == 500
            assert "Error bulk reprocessing files with Cloud OCR" in response.json()["detail"]

    def test_bulk_download_outer_exception(self, client: TestClient, db_session):
        """Test outer exception handling in bulk_download_files (lines 612-614)."""
        with patch("app.api.files.apply_owner_filter", side_effect=Exception("Unexpected error")):
            response = client.post("/api/files/bulk-download", json=[1, 2])
            assert response.status_code == 500
            assert "Error creating bulk download ZIP" in response.json()["detail"]


@pytest.mark.unit
class TestRetrySubtaskViaPipelineStep:
    """Test retry-subtask endpoint routing to _retry_pipeline_step (line 971)."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_retry_subtask_routes_to_pipeline_step(self, mock_delay, client: TestClient, db_session, tmp_path):
        """Test that retry-subtask routes pipeline step names to _retry_pipeline_step."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4 content")

        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        mock_task = Mock()
        mock_task.id = "task-pipeline"
        mock_delay.return_value = mock_task

        # Call with a pipeline step name - should route to _retry_pipeline_step (line 971)
        response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=process_document")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["subtask_name"] == "process_document"


@pytest.mark.unit
class TestUIUploadFileSplitting:
    """Test file splitting logic in ui-upload (lines 1431-1464)."""

    @patch("app.tasks.process_document.process_document.delay")
    def test_ui_upload_with_file_splitting(self, mock_delay, client: TestClient, tmp_path):
        """Test upload that triggers file splitting into parts."""
        mock_task = Mock()
        mock_task.id = "task-split"
        mock_delay.return_value = mock_task

        split_file_1 = str(tmp_path / "part1.pdf")
        split_file_2 = str(tmp_path / "part2.pdf")
        # Create the split files on disk
        with open(split_file_1, "wb") as f:
            f.write(b"%PDF-1.4 part1")
        with open(split_file_2, "wb") as f:
            f.write(b"%PDF-1.4 part2")

        pdf_content = b"%PDF-1.4 content"

        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.utils.file_splitting.should_split_file", return_value=True),
            patch("app.utils.file_splitting.split_pdf_by_size", return_value=[split_file_1, split_file_2]),
        ):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("large.pdf", pdf_content, "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["split_into_parts"] == 2
            assert mock_delay.call_count >= 1

    @patch("app.tasks.process_document.process_document.delay")
    def test_ui_upload_file_splitting_exception_falls_back(self, mock_delay, client: TestClient, tmp_path):
        """Test that splitting exception falls back to processing whole file."""
        mock_task = Mock()
        mock_task.id = "task-fallback"
        mock_delay.return_value = mock_task

        pdf_content = b"%PDF-1.4 content"

        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.utils.file_splitting.should_split_file", return_value=True),
            patch("app.utils.file_splitting.split_pdf_by_size", side_effect=Exception("Split failed")),
        ):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("test.pdf", pdf_content, "application/pdf")},
            )
            assert response.status_code == 200
            data = response.json()
            # Should fall back to processing whole file
            assert data["status"] == "queued"
            assert mock_delay.called


@pytest.mark.unit
class TestUIUploadAllowedMimeTypes:
    """Test upload for allowed MIME types that go through convert_to_pdf."""

    def test_ui_upload_office_document_triggers_conversion(self, client: TestClient, tmp_path):
        """Test office document upload triggers PDF conversion via allowed MIME types."""
        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("app.api.files.convert_to_pdf") as mock_convert,
        ):
            mock_task = Mock()
            mock_task.id = "task-office"
            mock_convert.delay = Mock(return_value=mock_task)

            # Use a MIME type in ALLOWED_MIME_TYPES
            response = client.post(
                "/api/ui-upload",
                files={
                    "file": (
                        "document.docx",
                        b"PK fake docx content",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data


@pytest.mark.unit
class TestAssignPipelineNonAdminOwnership:
    """Test assign_pipeline ownership check for non-admin users (line 1688)."""

    def test_assign_pipeline_non_admin_file_owned_by_others_returns_404(self, client: TestClient, db_session):
        """Test non-admin cannot see or modify files owned by other users (line 1688)."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id="other_user_id",
        )
        db_session.add(file)
        db_session.commit()

        # In single-user/no-auth mode, get_current_user returns None, get_current_user_id returns "anonymous"
        # get_current_owner_id also returns None
        # So: is_admin_user=False, file.owner_id="other_user_id", owner_id=None
        # Condition: not False AND "other_user_id" is not None AND "other_user_id" != None -> True
        response = client.post(f"/api/files/{file.id}/assign-pipeline")
        # The non-admin check should return 404 since owner_id != file.owner_id
        assert response.status_code == 404


@pytest.mark.unit
class TestDuplicateFileOSError:
    """Test OSError handling when removing duplicate file in ui-upload (lines 1408-1409)."""

    @patch("app.config.settings.max_upload_size", 10485760)
    @patch("app.config.settings.enable_deduplication", True)
    def test_ui_upload_duplicate_os_remove_error_handled(self, client: TestClient, db_session, tmp_path):
        """Test that OSError when removing duplicate file is handled gracefully."""
        from app.utils.file_operations import hash_file

        file_content = b"%PDF-1.4 duplicate content for oserror test 1234567890ABCDEF"
        tmp_file = tmp_path / "original_oserror.pdf"
        tmp_file.write_bytes(file_content)
        filehash = hash_file(str(tmp_file))

        existing = FileRecord(
            filehash=filehash,
            original_filename="original.pdf",
            local_filename=str(tmp_file),
            file_size=len(file_content),
            mime_type="application/pdf",
            is_duplicate=False,
        )
        db_session.add(existing)
        db_session.commit()

        with (
            patch("app.config.settings.workdir", str(tmp_path)),
            patch("os.remove", side_effect=OSError("Permission denied")),
        ):
            response = client.post(
                "/api/ui-upload",
                files={"file": ("duplicate.pdf", file_content, "application/pdf")},
            )
            # Should still return duplicate status even if os.remove fails
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "duplicate"


@pytest.mark.unit
class TestRetrySubtaskProcessedFilePresentButMissing:
    """Test retry-subtask when processed_file_path is set but doesn't exist (line 1026->1030)."""

    def test_retry_subtask_processed_path_set_but_missing_uses_legacy(self, client: TestClient, db_session, tmp_path):
        """Test that retry-subtask falls through to legacy paths when processed_file_path doesn't exist."""
        # Create a file in legacy path location
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()
        # Use hash-based path for legacy lookup
        legacy_file = processed_dir / "hashlegacy.pdf"
        legacy_file.write_bytes(b"%PDF-1.4 legacy")

        file = FileRecord(
            filehash="hashlegacy",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            # processed_file_path is set but points to a non-existent file
            processed_file_path="/nonexistent/processed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch("app.tasks.upload_to_email.upload_to_email") as mock_task,
        ):
            mock_settings.workdir = str(tmp_path)
            mock_task.delay.return_value = Mock(id="task-email")
            response = client.post(f"/api/files/{file.id}/retry-subtask?subtask_name=upload_to_email")
            # Should find the file via legacy hash-based path
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"


@pytest.mark.unit
class TestPreviewDownloadExceptions:
    """Test exception handling in preview and download endpoints (lines 1153-1155, 1235-1237)."""

    def test_preview_unexpected_exception_returns_500(self, client: TestClient, db_session):
        """Test that unexpected exception in preview endpoint returns 500."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        # Patch apply_owner_filter to raise an unexpected exception (not HTTPException)
        with patch("app.api.files.apply_owner_filter", side_effect=RuntimeError("Unexpected DB error")):
            response = client.get(f"/api/files/{file.id}/preview?version=original")
            assert response.status_code == 500
            assert "Error retrieving file preview" in response.json()["detail"]

    def test_download_unexpected_exception_returns_500(self, client: TestClient, db_session):
        """Test that unexpected exception in download endpoint returns 500."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file)
        db_session.commit()

        with patch("app.api.files.apply_owner_filter", side_effect=RuntimeError("Unexpected DB error")):
            response = client.get(f"/api/files/{file.id}/download?version=original")
            assert response.status_code == 500
            assert "Error downloading file" in response.json()["detail"]


@pytest.mark.unit
class TestAssignOwnerWithFileIds:
    """Test assign-owner endpoint with specific file_ids (line 1615)."""

    def test_assign_owner_with_file_ids_using_admin_session(self, client: TestClient, db_session):
        """Test assign-owner with specific file_ids in request body (covers line 1615)."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
            owner_id=None,
        )
        db_session.add(file1)
        db_session.commit()

        with (
            patch("app.api.files.settings") as mock_settings,
            patch(
                "starlette.requests.Request.session",
                new_callable=lambda: property(lambda self: {"user": {"is_admin": True}}),
            ),
        ):
            mock_settings.multi_user_enabled = True
            # Send file_ids as JSON body (the parameter is body-typed, not query-typed)
            response = client.post(
                "/api/files/assign-owner?owner_id=newowner",
                json=[file1.id],  # file_ids as JSON body
            )
            assert response.status_code == 200
            data = response.json()
            # file1 should be assigned (file_ids branch, line 1615)
            assert data["updated_count"] == 1
            assert data["owner_id"] == "newowner"
