"""
Tests for enhanced logging and original_file_path fallback in retry-subtask endpoint.
"""

import shutil
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord


@pytest.mark.integration
class TestRetrySubtaskEnhancedLogging:
    """Tests for enhanced logging in retry-subtask endpoint."""

    def test_embed_metadata_retry_with_original_file_path(
        self, client: TestClient, db_session, sample_pdf_path, tmp_path
    ):
        """Test that embed_metadata_into_pdf retry uses original_file_path as fallback."""
        mock_task = MagicMock()
        mock_task.id = "embed-original-fallback-task"

        # Create original directory and copy file there
        original_dir = tmp_path / "original"
        original_dir.mkdir(exist_ok=True)
        original_file = original_dir / "original_doc.pdf"
        shutil.copy(sample_pdf_path, original_file)

        # Create file record with non-existent local_filename and processed_file_path
        # but existing original_file_path
        file_record = FileRecord(
            filehash="embed_original_test",
            original_filename="original_doc.pdf",
            local_filename="/nonexistent/tmp/doc.pdf",  # File no longer in tmp
            processed_file_path="/nonexistent/processed/doc.pdf",  # Also not in processed
            original_file_path=str(original_file),  # But exists in original
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        with patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_extract:
            mock_extract.delay.return_value = mock_task
            response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=embed_metadata_into_pdf")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["subtask_name"] == "embed_metadata_into_pdf"

        # Verify the task was called with the original_file_path
        mock_extract.delay.assert_called_once()
        call_args = mock_extract.delay.call_args
        # First argument should be the file path (original_file_path in this case)
        assert call_args[0][0] == str(original_file)

    def test_embed_metadata_retry_error_includes_all_checked_paths(self, client: TestClient, db_session):
        """Test that error message includes all checked paths with their existence status."""
        # Create file record with all non-existent paths
        file_record = FileRecord(
            filehash="embed_error_paths_test",
            original_filename="missing.pdf",
            local_filename="/nonexistent/tmp/missing.pdf",
            processed_file_path="/nonexistent/processed/missing.pdf",
            original_file_path="/nonexistent/original/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=embed_metadata_into_pdf")

        assert response.status_code == 400
        error_detail = response.json()["detail"]

        # Verify the error message contains diagnostic information
        assert "Cannot retry metadata embedding" in error_detail
        assert "Paths checked:" in error_detail
        assert "local_filename" in error_detail
        assert "processed_file_path" in error_detail
        assert "original_file_path" in error_detail
        assert "workdir_tmp_fallback" in error_detail
        assert "exists=False" in error_detail

    def test_process_document_error_includes_checked_path(self, client: TestClient, db_session):
        """Test that process_document error message includes checked path."""
        file_record = FileRecord(
            filehash="process_error_test",
            original_filename="missing.pdf",
            local_filename="/nonexistent/tmp/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=process_document")

        assert response.status_code == 400
        error_detail = response.json()["detail"]

        # Verify the error message contains diagnostic information
        assert "Cannot retry" in error_detail
        assert "Path checked:" in error_detail
        assert "local_filename" in error_detail
        assert "exists=False" in error_detail

    def test_ocr_retry_error_includes_checked_path(self, client: TestClient, db_session):
        """Test that OCR retry error message includes checked path."""
        file_record = FileRecord(
            filehash="ocr_error_test",
            original_filename="missing.pdf",
            local_filename="/nonexistent/tmp/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        response = client.post(
            f"/api/files/{file_record.id}/retry-subtask?subtask_name=process_with_azure_document_intelligence"
        )

        assert response.status_code == 400
        error_detail = response.json()["detail"]

        # Verify the error message contains diagnostic information
        assert "Cannot retry OCR" in error_detail
        assert "Path checked:" in error_detail
        assert "local_filename" in error_detail
        assert "exists=False" in error_detail

    def test_metadata_extraction_error_includes_checked_path(self, client: TestClient, db_session):
        """Test that metadata extraction retry error message includes checked path."""
        file_record = FileRecord(
            filehash="metadata_error_test",
            original_filename="missing.pdf",
            local_filename="/nonexistent/tmp/missing.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=extract_metadata_with_gpt")

        assert response.status_code == 400
        error_detail = response.json()["detail"]

        # Verify the error message contains diagnostic information
        assert "Cannot retry metadata extraction" in error_detail
        assert "Path checked:" in error_detail
        assert "local_filename" in error_detail
        assert "exists=False" in error_detail

    def test_upload_retry_error_includes_all_checked_paths(self, client: TestClient, db_session):
        """Test that upload retry error message includes all checked paths."""
        file_record = FileRecord(
            filehash="upload_error_test",
            original_filename="missing.pdf",
            local_filename="/nonexistent/tmp/missing.pdf",
            processed_file_path="/nonexistent/processed/missing_gpt.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=upload_to_dropbox")

        assert response.status_code == 400
        error_detail = response.json()["detail"]

        # Verify the error message contains diagnostic information
        assert "Cannot retry upload" in error_detail
        assert "Paths checked:" in error_detail
        assert "processed_file_path" in error_detail
        assert "exists=False" in error_detail

    def test_upload_retry_uses_processed_file_path_from_db(
        self, client: TestClient, db_session, sample_pdf_path, tmp_path
    ):
        """Test that upload retry uses processed_file_path from DB when legacy paths don't exist."""
        mock_task = MagicMock()
        mock_task.id = "upload-processed-path-task"

        # Create processed file at the DB-stored path (GPT-suggested filename)
        processed_file = tmp_path / "2023-10-01_Unknown.pdf"
        shutil.copy(sample_pdf_path, processed_file)

        # Create file record where only processed_file_path exists
        # (simulates the real scenario: original filename != GPT-suggested filename)
        file_record = FileRecord(
            filehash="upload_db_path_test",
            original_filename="cable_graphic.pdf",
            local_filename="/nonexistent/tmp/uuid.pdf",
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        with patch("app.tasks.upload_to_onedrive.upload_to_onedrive") as mock_upload:
            mock_upload.delay.return_value = mock_task
            response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=upload_to_onedrive")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["subtask_name"] == "upload_to_onedrive"

        # Verify the task was called with the processed_file_path from DB
        mock_upload.delay.assert_called_once()
        call_args = mock_upload.delay.call_args
        assert call_args[0][0] == str(processed_file)

    def test_upload_retry_processed_file_path_takes_priority(
        self, client: TestClient, db_session, sample_pdf_path, tmp_path
    ):
        """Test that processed_file_path from DB takes priority over legacy hash-based paths."""
        mock_task = MagicMock()
        mock_task.id = "upload-priority-task"

        # Create the DB-stored processed file
        processed_file = tmp_path / "2024-01-01_Invoice.pdf"
        shutil.copy(sample_pdf_path, processed_file)

        file_record = FileRecord(
            filehash="upload_priority_test",
            original_filename="scan001.pdf",
            local_filename="/nonexistent/tmp/uuid.pdf",
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        with patch("app.tasks.upload_to_dropbox.upload_to_dropbox") as mock_upload:
            mock_upload.delay.return_value = mock_task
            response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=upload_to_dropbox")

        assert response.status_code == 200

        # Verify the task was called with the processed_file_path (first priority for uploads)
        mock_upload.delay.assert_called_once()
        call_args = mock_upload.delay.call_args
        assert call_args[0][0] == str(processed_file)

    def test_embed_metadata_path_order(self, client: TestClient, db_session, sample_pdf_path, tmp_path):
        """Test that embed_metadata_into_pdf checks paths in the correct order."""
        mock_task = MagicMock()
        mock_task.id = "embed-path-order-task"

        # Create all three directories with files
        local_file = tmp_path / "local_file.pdf"
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(exist_ok=True)
        processed_file = processed_dir / "processed_file.pdf"
        original_dir = tmp_path / "original"
        original_dir.mkdir(exist_ok=True)
        original_file = original_dir / "original_file.pdf"

        # Copy sample PDF to all locations
        shutil.copy(sample_pdf_path, local_file)
        shutil.copy(sample_pdf_path, processed_file)
        shutil.copy(sample_pdf_path, original_file)

        # Create file record with all paths existing
        file_record = FileRecord(
            filehash="embed_path_order_test",
            original_filename="doc.pdf",
            local_filename=str(local_file),
            processed_file_path=str(processed_file),
            original_file_path=str(original_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        with patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_extract:
            mock_extract.delay.return_value = mock_task
            response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=embed_metadata_into_pdf")

        assert response.status_code == 200

        # Verify the task was called with the local_filename (first priority)
        mock_extract.delay.assert_called_once()
        call_args = mock_extract.delay.call_args
        assert call_args[0][0] == str(local_file)

    def test_embed_metadata_prefers_processed_over_original(
        self, client: TestClient, db_session, sample_pdf_path, tmp_path
    ):
        """Test that when local_filename is missing, processed_file_path is preferred over original_file_path."""
        mock_task = MagicMock()
        mock_task.id = "embed-processed-priority-task"

        # Create processed and original directories with files
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir(exist_ok=True)
        processed_file = processed_dir / "processed_file.pdf"
        original_dir = tmp_path / "original"
        original_dir.mkdir(exist_ok=True)
        original_file = original_dir / "original_file.pdf"

        # Copy sample PDF to both locations
        shutil.copy(sample_pdf_path, processed_file)
        shutil.copy(sample_pdf_path, original_file)

        # Create file record with non-existent local_filename but existing processed and original
        file_record = FileRecord(
            filehash="embed_processed_priority_test",
            original_filename="doc.pdf",
            local_filename="/nonexistent/tmp/doc.pdf",
            processed_file_path=str(processed_file),
            original_file_path=str(original_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()
        db_session.refresh(file_record)

        with patch("app.tasks.extract_metadata_with_gpt.extract_metadata_with_gpt") as mock_extract:
            mock_extract.delay.return_value = mock_task
            response = client.post(f"/api/files/{file_record.id}/retry-subtask?subtask_name=embed_metadata_into_pdf")

        assert response.status_code == 200

        # Verify the task was called with the processed_file_path (second priority)
        mock_extract.delay.assert_called_once()
        call_args = mock_extract.delay.call_args
        assert call_args[0][0] == str(processed_file)
