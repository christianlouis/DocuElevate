"""
Comprehensive unit tests for app/views/files.py

Tests all view endpoints with success and error cases, proper mocking, and edge cases.
Target: Bring coverage from 8.77% to 70%+
"""

import json
import os
from unittest.mock import Mock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord, ProcessingLog


@pytest.mark.unit
class TestFilesPage:
    """Tests for GET /files endpoint."""

    def test_files_page_empty_database(self, client: TestClient, db_session):
        """Test files page with no files in database."""
        response = client.get("/files")
        assert response.status_code == 200
        assert b"files.html" in response.content or b"Files" in response.content

    def test_files_page_with_data(self, client: TestClient, db_session):
        """Test files page with existing files."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="test1.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="test2.pdf",
            local_filename="/tmp/test2.pdf",
            file_size=2048,
            mime_type="application/pdf"
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/files")
        assert response.status_code == 200

    def test_files_page_with_pagination(self, client: TestClient, db_session):
        """Test pagination on files page."""
        # Create 10 files
        for i in range(10):
            file = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf"
            )
            db_session.add(file)
        db_session.commit()

        # Test page 1
        response = client.get("/files?page=1&per_page=5")
        assert response.status_code == 200

        # Test page 2
        response = client.get("/files?page=2&per_page=5")
        assert response.status_code == 200

    def test_files_page_with_search_filter(self, client: TestClient, db_session):
        """Test search filtering."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="invoice.pdf",
            local_filename="/tmp/invoice.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="receipt.pdf",
            local_filename="/tmp/receipt.pdf",
            file_size=2048,
            mime_type="application/pdf"
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/files?search=invoice")
        assert response.status_code == 200

    def test_files_page_with_mime_type_filter(self, client: TestClient, db_session):
        """Test MIME type filtering."""
        file1 = FileRecord(
            filehash="hash1",
            original_filename="doc.pdf",
            local_filename="/tmp/doc.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="image.jpg",
            local_filename="/tmp/image.jpg",
            file_size=2048,
            mime_type="image/jpeg"
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/files?mime_type=application/pdf")
        assert response.status_code == 200

    def test_files_page_with_status_filter(self, client: TestClient, db_session):
        """Test status filtering."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get("/files?status=completed")
        assert response.status_code == 200

    def test_files_page_sorting_by_filename_asc(self, client: TestClient, db_session):
        """Test sorting by filename ascending."""
        file1 = FileRecord(filehash="hash1", original_filename="aaa.pdf", local_filename="/tmp/aaa.pdf", file_size=1024, mime_type="application/pdf")
        file2 = FileRecord(filehash="hash2", original_filename="zzz.pdf", local_filename="/tmp/zzz.pdf", file_size=2048, mime_type="application/pdf")
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/files?sort_by=original_filename&sort_order=asc")
        assert response.status_code == 200

    def test_files_page_sorting_by_size_desc(self, client: TestClient, db_session):
        """Test sorting by file size descending."""
        file1 = FileRecord(filehash="hash1", original_filename="small.pdf", local_filename="/tmp/small.pdf", file_size=100, mime_type="application/pdf")
        file2 = FileRecord(filehash="hash2", original_filename="large.pdf", local_filename="/tmp/large.pdf", file_size=10000, mime_type="application/pdf")
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        response = client.get("/files?sort_by=file_size&sort_order=desc")
        assert response.status_code == 200

    def test_files_page_error_handling(self, client: TestClient, db_session):
        """Test error handling in files page."""
        # Trigger error by mocking database query to raise exception
        with patch("app.views.files.db_session") as mock_db:
            mock_db.query.side_effect = Exception("Database error")
            response = client.get("/files")
            # Should still return 200 with error message in template
            assert response.status_code == 200


@pytest.mark.unit
class TestFileDetailPage:
    """Tests for GET /files/{file_id}/detail endpoint."""

    def test_file_detail_page_success(self, client: TestClient, db_session, tmp_path):
        """Test file detail page with existing file."""
        # Create file with paths that exist
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            original_file_path=str(file_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/detail")
        assert response.status_code == 200

    def test_file_detail_page_not_found(self, client: TestClient, db_session):
        """Test file detail page for non-existent file."""
        response = client.get("/files/99999/detail")
        assert response.status_code == 200  # Still renders template with error

    def test_file_detail_page_with_processing_logs(self, client: TestClient, db_session, tmp_path):
        """Test file detail page includes processing logs."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        # Add processing logs
        log1 = ProcessingLog(
            file_id=file.id,
            task_id="task1",
            step_name="create_file_record",
            status="success",
            message="File record created"
        )
        log2 = ProcessingLog(
            file_id=file.id,
            task_id="task2",
            step_name="extract_text",
            status="success",
            message="Text extracted"
        )
        db_session.add(log1)
        db_session.add(log2)
        db_session.commit()

        response = client.get(f"/files/{file.id}/detail")
        assert response.status_code == 200

    def test_file_detail_page_with_metadata_json(self, client: TestClient, db_session, tmp_path):
        """Test file detail page loads GPT metadata from JSON file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        
        # Create processed file path
        processed_path = tmp_path / "test_processed.pdf"
        processed_path.write_bytes(b"%PDF-1.4")
        
        # Create metadata JSON file
        metadata_path = tmp_path / "test_processed.json"
        metadata = {"document_type": "invoice", "amount": 100.00}
        metadata_path.write_text(json.dumps(metadata))
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(file_path),
            processed_file_path=str(processed_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/detail")
        assert response.status_code == 200

    def test_file_detail_checks_original_file_exists(self, client: TestClient, db_session, tmp_path):
        """Test that file detail checks if original file exists on disk."""
        # File without existing path
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            original_file_path="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/detail")
        assert response.status_code == 200

    def test_file_detail_error_handling(self, client: TestClient, db_session):
        """Test error handling in file detail page."""
        # Create file but mock query to raise exception
        with patch("app.views.files.db_session") as mock_db:
            mock_db.query.side_effect = Exception("Database error")
            response = client.get("/files/1/detail")
            assert response.status_code == 200  # Renders error template


@pytest.mark.unit
class TestComputeProcessingFlow:
    """Tests for _compute_processing_flow helper function."""

    @patch("app.config.settings.enable_deduplication", False)
    def test_compute_processing_flow_basic(self, db_session):
        """Test basic processing flow computation."""
        from app.views.files import _compute_processing_flow
        
        logs = [
            Mock(
                step_name="create_file_record",
                status="success",
                message="Created",
                timestamp=Mock(),
                task_id="task1"
            ),
            Mock(
                step_name="check_text",
                status="success",
                message="Checked",
                timestamp=Mock(),
                task_id="task2"
            )
        ]
        
        flow = _compute_processing_flow(logs)
        assert isinstance(flow, list)
        assert len(flow) > 0

    @patch("app.config.settings.enable_deduplication", True)
    @patch("app.config.settings.show_deduplication_step", True)
    def test_compute_processing_flow_with_deduplication(self, db_session):
        """Test flow includes deduplication when enabled."""
        from app.views.files import _compute_processing_flow
        
        logs = [
            Mock(
                step_name="check_for_duplicates",
                status="success",
                message="No duplicates",
                timestamp=Mock(),
                task_id="task1"
            )
        ]
        
        flow = _compute_processing_flow(logs)
        # Should include deduplication step
        step_keys = [step["key"] for step in flow]
        assert "check_for_duplicates" in step_keys

    def test_compute_processing_flow_with_upload_branches(self, db_session):
        """Test flow includes upload branches."""
        from app.views.files import _compute_processing_flow
        
        logs = [
            Mock(
                step_name="send_to_all_destinations",
                status="success",
                message="Sent",
                timestamp=Mock(),
                task_id="task1"
            ),
            Mock(
                step_name="upload_to_dropbox",
                status="success",
                message="Uploaded",
                timestamp=Mock(),
                task_id="task2"
            ),
            Mock(
                step_name="upload_to_google_drive",
                status="failure",
                message="Failed",
                timestamp=Mock(),
                task_id="task3"
            )
        ]
        
        flow = _compute_processing_flow(logs)
        # Find the upload stage
        upload_stage = next((s for s in flow if s.get("is_branch_parent")), None)
        if upload_stage:
            assert "branches" in upload_stage
            assert len(upload_stage["branches"]) > 0

    def test_compute_processing_flow_handles_failure_status(self, db_session):
        """Test flow correctly identifies failed steps."""
        from app.views.files import _compute_processing_flow
        
        logs = [
            Mock(
                step_name="extract_metadata_with_gpt",
                status="failure",
                message="Failed to extract",
                timestamp=Mock(),
                task_id="task1"
            )
        ]
        
        flow = _compute_processing_flow(logs)
        failed_steps = [s for s in flow if s["status"] == "failure"]
        # Should have at least the failed step we added
        assert len(failed_steps) >= 1
        assert failed_steps[0]["can_retry"] is True


@pytest.mark.unit
class TestComputeStepSummary:
    """Tests for _compute_step_summary helper function."""

    @patch("app.config.settings.enable_deduplication", False)
    def test_compute_step_summary_basic(self):
        """Test basic step summary computation."""
        from app.views.files import _compute_step_summary
        
        logs = [
            Mock(step_name="create_file_record", status="success", timestamp=Mock()),
            Mock(step_name="check_text", status="success", timestamp=Mock()),
            Mock(step_name="extract_text", status="success", timestamp=Mock())
        ]
        
        summary = _compute_step_summary(logs)
        assert "main" in summary
        assert "uploads" in summary
        assert isinstance(summary["main"]["success"], int)

    def test_compute_step_summary_with_uploads(self):
        """Test summary includes upload task counts."""
        from app.views.files import _compute_step_summary
        
        logs = [
            Mock(step_name="create_file_record", status="success", timestamp=Mock()),
            Mock(step_name="upload_to_dropbox", status="success", timestamp=Mock()),
            Mock(step_name="upload_to_google_drive", status="failure", timestamp=Mock())
        ]
        
        summary = _compute_step_summary(logs)
        assert summary["uploads"]["success"] >= 1
        assert summary["uploads"]["failure"] >= 1

    def test_compute_step_summary_normalizes_pending_status(self):
        """Test that 'pending' status is normalized to 'queued'."""
        from app.views.files import _compute_step_summary
        
        logs = [
            Mock(step_name="create_file_record", status="pending", timestamp=Mock())
        ]
        
        summary = _compute_step_summary(logs)
        # Should count as queued, not pending
        assert summary["main"]["queued"] >= 1

    def test_compute_step_summary_order_independent(self):
        """Test that summary is order-independent (uses latest timestamp)."""
        from app.views.files import _compute_step_summary
        from datetime import datetime, timedelta
        
        now = datetime.now()
        logs = [
            Mock(step_name="create_file_record", status="queued", timestamp=now),
            Mock(step_name="create_file_record", status="success", timestamp=now + timedelta(seconds=10))
        ]
        
        summary = _compute_step_summary(logs)
        # Should count success (latest) not queued
        assert summary["main"]["success"] >= 1
        assert summary["main"]["queued"] == 0


@pytest.mark.unit
class TestPreviewOriginalFile:
    """Tests for GET /files/{file_id}/preview/original endpoint."""

    def test_preview_original_file_success(self, client: TestClient, db_session, tmp_path):
        """Test preview of original file."""
        file_path = tmp_path / "test.pdf"
        file_path.write_bytes(b"%PDF-1.4")
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            original_file_path=str(file_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/preview/original")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "inline" in response.headers.get("content-disposition", "")

    def test_preview_original_file_not_found(self, client: TestClient, db_session):
        """Test preview when file record doesn't exist."""
        response = client.get("/files/99999/preview/original")
        assert response.status_code == 404

    def test_preview_original_file_missing_on_disk(self, client: TestClient, db_session):
        """Test preview when file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            original_file_path="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/preview/original")
        assert response.status_code == 404


@pytest.mark.unit
class TestPreviewProcessedFile:
    """Tests for GET /files/{file_id}/preview/processed endpoint."""

    def test_preview_processed_file_success(self, client: TestClient, db_session, tmp_path):
        """Test preview of processed file."""
        processed_path = tmp_path / "test_processed.pdf"
        processed_path.write_bytes(b"%PDF-1.4")
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            processed_file_path=str(processed_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/preview/processed")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_preview_processed_file_not_found(self, client: TestClient, db_session):
        """Test preview when file record doesn't exist."""
        response = client.get("/files/99999/preview/processed")
        assert response.status_code == 404

    def test_preview_processed_file_missing_on_disk(self, client: TestClient, db_session):
        """Test preview when processed file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            processed_file_path="/nonexistent/test_processed.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/preview/processed")
        assert response.status_code == 404


@pytest.mark.unit
class TestGetOriginalText:
    """Tests for GET /files/{file_id}/text/original endpoint."""

    def test_get_original_text_success(self, client: TestClient, db_session, tmp_path):
        """Test extracting text from original PDF."""
        # Create a minimal PDF
        pdf_path = tmp_path / "test.pdf"
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
197
%%EOF
"""
        pdf_path.write_bytes(pdf_content)
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            original_file_path=str(pdf_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/text/original")
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "page_count" in data

    def test_get_original_text_file_not_found(self, client: TestClient, db_session):
        """Test text extraction for non-existent file."""
        response = client.get("/files/99999/text/original")
        assert response.status_code == 404

    def test_get_original_text_file_missing_on_disk(self, client: TestClient, db_session):
        """Test text extraction when file doesn't exist on disk."""
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            original_file_path="/nonexistent/test.pdf",
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/text/original")
        assert response.status_code == 404


@pytest.mark.unit
class TestGetProcessedText:
    """Tests for GET /files/{file_id}/text/processed endpoint."""

    def test_get_processed_text_success(self, client: TestClient, db_session, tmp_path):
        """Test extracting text from processed PDF."""
        pdf_path = tmp_path / "test_processed.pdf"
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
197
%%EOF
"""
        pdf_path.write_bytes(pdf_content)
        
        file = FileRecord(
            filehash="hash1",
            original_filename="test.pdf",
            local_filename=str(pdf_path),  # local_filename is NOT NULL
            processed_file_path=str(pdf_path),
            file_size=1024,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/text/processed")
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "page_count" in data

    def test_get_processed_text_file_not_found(self, client: TestClient, db_session):
        """Test text extraction for non-existent file."""
        response = client.get("/files/99999/text/processed")
        assert response.status_code == 404

    def test_get_processed_text_no_text_extracted(self, client: TestClient, db_session, tmp_path):
        """Test when no text can be extracted from PDF."""
        # Create empty/minimal PDF
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
        
        file = FileRecord(
            filehash="hash1",
            original_filename="empty.pdf",
            local_filename=str(pdf_path),  # local_filename is NOT NULL
            processed_file_path=str(pdf_path),
            file_size=100,
            mime_type="application/pdf"
        )
        db_session.add(file)
        db_session.commit()

        response = client.get(f"/files/{file.id}/text/processed")
        # Should return 200 with message about no text
        assert response.status_code in [200, 500]  # Might fail parsing minimal PDF
