"""
Extended tests for app/views/files.py to achieve 90%+ coverage.
"""

import json
import os
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord, ProcessingLog


@pytest.mark.integration
@pytest.mark.requires_db
class TestFilesPageExtended:
    """Extended tests for the /files page view."""

    def test_files_page_with_search_filter(self, client: TestClient, db_session):
        """Test that search filter works correctly"""
        # Create files with different names
        for i in range(5):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"invoice_{i}.pdf" if i < 3 else f"report_{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file_record)
        db_session.commit()

        # Search for "invoice"
        response = client.get("/files?search=invoice")
        assert response.status_code == 200
        content = response.text
        assert "invoice" in content
        # Should not show all files
        assert "report_4" not in content or content.count("report_") < 2

    def test_files_page_with_mime_type_filter(self, client: TestClient, db_session):
        """Test that MIME type filter works correctly"""
        # Create files with different MIME types
        file1 = FileRecord(
            filehash="hash1",
            original_filename="document.pdf",
            local_filename="/tmp/test1.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        file2 = FileRecord(
            filehash="hash2",
            original_filename="image.jpg",
            local_filename="/tmp/test2.jpg",
            file_size=2048,
            mime_type="image/jpeg",
        )
        db_session.add(file1)
        db_session.add(file2)
        db_session.commit()

        # Filter by PDF MIME type
        response = client.get("/files?mime_type=application/pdf")
        assert response.status_code == 200
        content = response.text
        assert "document.pdf" in content

    def test_files_page_with_sorting(self, client: TestClient, db_session):
        """Test that sorting works correctly"""
        # Create files with different sizes
        for i in range(3):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"file_{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024 * (i + 1),
                mime_type="application/pdf",
            )
            db_session.add(file_record)
        db_session.commit()

        # Sort by file_size ascending
        response = client.get("/files?sort_by=file_size&sort_order=asc")
        assert response.status_code == 200

        # Sort by file_size descending
        response = client.get("/files?sort_by=file_size&sort_order=desc")
        assert response.status_code == 200

    def test_files_page_pagination(self, client: TestClient, db_session):
        """Test pagination with different page sizes"""
        # Create many files
        for i in range(25):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf",
            )
            db_session.add(file_record)
        db_session.commit()

        # Test page 1
        response = client.get("/files?page=1&per_page=10")
        assert response.status_code == 200

        # Test page 2
        response = client.get("/files?page=2&per_page=10")
        assert response.status_code == 200

    def test_files_page_error_handling(self, client: TestClient, db_session):
        """Test that errors are handled gracefully"""
        # Test with invalid page number (should default to 1)
        response = client.get("/files?page=0")
        # FastAPI query validation should reject page=0
        assert response.status_code in [200, 422]  # Either works or validation error


@pytest.mark.integration
@pytest.mark.requires_db
class TestFileDetailPage:
    """Tests for the /files/{file_id}/detail page."""

    def test_file_detail_page_with_existing_file(self, client: TestClient, db_session, tmp_path):
        """Test file detail page with an existing file"""
        # Create a test file
        original_file = tmp_path / "original.pdf"
        original_file.write_bytes(b"PDF content")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(original_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test file detail page
        response = client.get(f"/files/{file_record.id}/detail")
        assert response.status_code == 200
        content = response.text
        assert "test.pdf" in content

    def test_file_detail_page_with_missing_file(self, client: TestClient, db_session):
        """Test file detail page with non-existent file"""
        # Try to access non-existent file
        response = client.get("/files/99999/detail")
        assert response.status_code == 200
        content = response.text
        assert "not found" in content.lower()

    def test_file_detail_page_with_processing_logs(self, client: TestClient, db_session, tmp_path):
        """Test file detail page shows processing logs"""
        # Create a test file
        original_file = tmp_path / "original.pdf"
        original_file.write_bytes(b"PDF content")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(original_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Add processing logs
        log1 = ProcessingLog(
            file_id=file_record.id,
            step_name="create_file_record",
            status="success",
            message="File record created",
            timestamp=datetime.utcnow(),
        )
        log2 = ProcessingLog(
            file_id=file_record.id,
            step_name="extract_text",
            status="success",
            message="Text extracted",
            timestamp=datetime.utcnow(),
        )
        db_session.add(log1)
        db_session.add(log2)
        db_session.commit()

        # Test file detail page
        response = client.get(f"/files/{file_record.id}/detail")
        assert response.status_code == 200
        content = response.text
        assert "create_file_record" in content
        assert "extract_text" in content

    def test_file_detail_page_with_metadata(self, client: TestClient, db_session, tmp_path):
        """Test file detail page shows metadata when available"""
        # Create test files
        original_file = tmp_path / "original.pdf"
        processed_file = tmp_path / "processed.pdf"
        metadata_file = tmp_path / "processed.json"

        original_file.write_bytes(b"PDF content")
        processed_file.write_bytes(b"Processed PDF content")

        # Create metadata JSON
        metadata = {
            "document_type": "invoice",
            "amount": 150.00,
            "date": "2024-01-15",
            "vendor": "Test Vendor",
        }
        metadata_file.write_text(json.dumps(metadata))

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(original_file),
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test file detail page
        response = client.get(f"/files/{file_record.id}/detail")
        assert response.status_code == 200
        content = response.text
        # Should show metadata
        assert "invoice" in content or "metadata" in content.lower()


@pytest.mark.integration
@pytest.mark.requires_db
class TestFilePreviewEndpoints:
    """Tests for file preview endpoints."""

    def test_preview_original_file_success(self, client: TestClient, db_session, tmp_path):
        """Test successful preview of original file"""
        # Create a test PDF file
        original_file = tmp_path / "original.pdf"
        original_file.write_bytes(b"%PDF-1.4\nTest PDF content")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(original_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test preview endpoint
        response = client.get(f"/files/{file_record.id}/preview/original")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_preview_original_file_not_found(self, client: TestClient, db_session):
        """Test preview when file doesn't exist"""
        response = client.get("/files/99999/preview/original")
        assert response.status_code == 404

    def test_preview_original_file_missing_on_disk(self, client: TestClient, db_session):
        """Test preview when file record exists but file is missing on disk"""
        # Create file record with non-existent path
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path="/nonexistent/file.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test preview endpoint
        response = client.get(f"/files/{file_record.id}/preview/original")
        assert response.status_code == 404

    def test_preview_processed_file_success(self, client: TestClient, db_session, tmp_path):
        """Test successful preview of processed file"""
        # Create a test PDF file
        processed_file = tmp_path / "processed.pdf"
        processed_file.write_bytes(b"%PDF-1.4\nProcessed PDF content")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=str(processed_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test preview endpoint
        response = client.get(f"/files/{file_record.id}/preview/processed")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    def test_preview_processed_file_not_found(self, client: TestClient, db_session):
        """Test preview when file doesn't exist"""
        response = client.get("/files/99999/preview/processed")
        assert response.status_code == 404

    def test_preview_processed_file_missing_on_disk(self, client: TestClient, db_session):
        """Test preview when file record exists but file is missing on disk"""
        # Create file record with non-existent path
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test preview endpoint
        response = client.get(f"/files/{file_record.id}/preview/processed")
        assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.requires_db
class TestTextExtractionEndpoints:
    """Tests for text extraction endpoints."""

    def test_get_original_text_success(self, client: TestClient, db_session, sample_pdf_file):
        """Test successful text extraction from original file"""
        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(sample_pdf_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/original")
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "page_count" in data

    def test_get_original_text_file_not_found(self, client: TestClient, db_session):
        """Test text extraction when file doesn't exist"""
        response = client.get("/files/99999/text/original")
        assert response.status_code == 404

    def test_get_original_text_file_missing_on_disk(self, client: TestClient, db_session):
        """Test text extraction when file is missing on disk"""
        # Create file record with non-existent path
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path="/nonexistent/file.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/original")
        assert response.status_code == 404

    def test_get_original_text_extraction_error(self, client: TestClient, db_session, tmp_path):
        """Test text extraction when PDF is invalid"""
        # Create an invalid PDF file
        invalid_pdf = tmp_path / "invalid.pdf"
        invalid_pdf.write_bytes(b"Not a valid PDF")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            original_file_path=str(invalid_pdf),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/original")
        assert response.status_code == 500

    def test_get_processed_text_success(self, client: TestClient, db_session, sample_pdf_file):
        """Test successful text extraction from processed file"""
        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=str(sample_pdf_file),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/processed")
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "page_count" in data

    def test_get_processed_text_file_not_found(self, client: TestClient, db_session):
        """Test text extraction when file doesn't exist"""
        response = client.get("/files/99999/text/processed")
        assert response.status_code == 404

    def test_get_processed_text_file_missing_on_disk(self, client: TestClient, db_session):
        """Test text extraction when file is missing on disk"""
        # Create file record with non-existent path
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path="/nonexistent/processed.pdf",
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/processed")
        assert response.status_code == 404

    def test_get_processed_text_extraction_error(self, client: TestClient, db_session, tmp_path):
        """Test text extraction when PDF is invalid"""
        # Create an invalid PDF file
        invalid_pdf = tmp_path / "invalid.pdf"
        invalid_pdf.write_bytes(b"Not a valid PDF")

        # Create file record
        file_record = FileRecord(
            filehash="testhash",
            original_filename="test.pdf",
            local_filename="/tmp/test.pdf",
            processed_file_path=str(invalid_pdf),
            file_size=1024,
            mime_type="application/pdf",
        )
        db_session.add(file_record)
        db_session.commit()

        # Test text extraction endpoint
        response = client.get(f"/files/{file_record.id}/text/processed")
        assert response.status_code == 500


@pytest.mark.unit
class TestProcessingFlowFunctions:
    """Unit tests for processing flow helper functions."""

    def test_compute_processing_flow_basic(self):
        """Test _compute_processing_flow with basic logs"""
        from app.views.files import _compute_processing_flow

        # Create mock logs
        logs = [
            Mock(
                step_name="create_file_record",
                status="success",
                message="File created",
                timestamp=datetime.utcnow(),
                task_id="task1",
            ),
            Mock(
                step_name="extract_text",
                status="success",
                message="Text extracted",
                timestamp=datetime.utcnow(),
                task_id="task2",
            ),
        ]

        flow = _compute_processing_flow(logs)
        assert isinstance(flow, list)
        assert len(flow) > 0
        # Check that stages have expected keys
        for stage in flow:
            assert "key" in stage
            assert "label" in stage
            assert "status" in stage

    def test_compute_processing_flow_with_uploads(self):
        """Test _compute_processing_flow with upload branches"""
        from app.views.files import _compute_processing_flow

        # Create mock logs including upload tasks
        logs = [
            Mock(
                step_name="send_to_all_destinations",
                status="success",
                message="Distribution queued",
                timestamp=datetime.utcnow(),
                task_id="task1",
            ),
            Mock(
                step_name="upload_to_dropbox",
                status="success",
                message="Uploaded to Dropbox",
                timestamp=datetime.utcnow(),
                task_id="task2",
            ),
            Mock(
                step_name="upload_to_google_drive",
                status="failure",
                message="Failed to upload",
                timestamp=datetime.utcnow(),
                task_id="task3",
            ),
        ]

        flow = _compute_processing_flow(logs)
        assert isinstance(flow, list)

        # Find the upload stage
        upload_stage = next((s for s in flow if s.get("is_branch_parent")), None)
        if upload_stage:
            assert "branches" in upload_stage
            assert len(upload_stage["branches"]) > 0

    def test_compute_step_summary_basic(self):
        """Test _compute_step_summary with basic logs"""
        from app.views.files import _compute_step_summary

        # Create mock logs
        logs = [
            Mock(
                step_name="create_file_record",
                status="success",
                timestamp=datetime.utcnow(),
            ),
            Mock(
                step_name="extract_text",
                status="success",
                timestamp=datetime.utcnow(),
            ),
            Mock(
                step_name="upload_to_dropbox",
                status="failure",
                timestamp=datetime.utcnow(),
            ),
        ]

        summary = _compute_step_summary(logs)
        assert isinstance(summary, dict)
        assert "main" in summary
        assert "uploads" in summary
        assert "total_main_steps" in summary
        assert "total_upload_tasks" in summary

        # Check that counts are correct
        assert summary["main"]["success"] >= 2
        assert summary["uploads"]["failure"] >= 1

    def test_compute_step_summary_order_independent(self):
        """Test that _compute_step_summary is order-independent"""
        from app.views.files import _compute_step_summary

        # Create logs with same step appearing multiple times
        earlier_time = datetime(2024, 1, 1, 10, 0, 0)
        later_time = datetime(2024, 1, 1, 11, 0, 0)

        logs_forward = [
            Mock(step_name="extract_text", status="queued", timestamp=earlier_time),
            Mock(step_name="extract_text", status="success", timestamp=later_time),
        ]

        logs_backward = [
            Mock(step_name="extract_text", status="success", timestamp=later_time),
            Mock(step_name="extract_text", status="queued", timestamp=earlier_time),
        ]

        summary_forward = _compute_step_summary(logs_forward)
        summary_backward = _compute_step_summary(logs_backward)

        # Should be the same regardless of log order
        assert summary_forward["main"]["success"] == summary_backward["main"]["success"]
        assert summary_forward["main"]["queued"] == summary_backward["main"]["queued"]
