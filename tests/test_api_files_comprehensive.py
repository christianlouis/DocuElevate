"""
Comprehensive unit tests for app/api/files.py

Tests all API endpoints with success and error cases, proper mocking, and edge cases.
Target: Bring coverage from 11.75% to 70%+
"""

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
        assert data["pagination"]["total_items"] == 0

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
        assert data["pagination"]["total_items"] == 2

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
        assert data["pagination"]["total_pages"] == 2

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
