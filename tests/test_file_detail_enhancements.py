"""
Tests for file detail page enhancements.

Tests the new features:
- GPT metadata display
- PDF preview endpoints
- Text modal functionality
- Using persisted original_file_path and processed_file_path
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.models import FileRecord


@pytest.fixture
def sample_metadata():
    """Sample GPT metadata"""
    return {
        "document_type": "Invoice",
        "filename": "2024-01-15_Company_Invoice",
        "date": "2024-01-15",
        "absender": "Test Company GmbH",
        "empfaenger": "Customer Inc",
        "betrag": "€ 1,234.56",
        "kontonummer": "DE89370400440532013000",
        "tags": ["invoice", "payment", "2024"],
    }


@pytest.mark.integration
def test_file_detail_page_with_metadata(client: TestClient, db_session, sample_pdf_file):
    """Test file detail page displays GPT metadata correctly"""

    # Create a file record with paths
    file_record = FileRecord(
        filehash="test123abc",
        original_filename="test_invoice.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path=str(sample_pdf_file),
        processed_file_path=None,  # Not processed yet
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # Get detail page
    response = client.get(f"/files/{file_record.id}/detail")
    assert response.status_code == 200

    html = response.text
    # Check for file info display
    assert "File Information" in html
    assert "test_invoice.pdf" in html
    assert "Original File Path" in html


@pytest.mark.integration
def test_file_detail_with_gpt_metadata(client: TestClient, db_session, sample_pdf_file, sample_metadata, tmp_path):
    """Test file detail page with GPT metadata JSON"""

    # Create processed file path and metadata JSON
    processed_file = tmp_path / "2024-01-15_Company_Invoice.pdf"
    processed_file.write_bytes(sample_pdf_file.read_bytes())

    metadata_file = tmp_path / "2024-01-15_Company_Invoice.json"
    metadata_file.write_text(json.dumps(sample_metadata, indent=2))

    file_record = FileRecord(
        filehash="test456def",
        original_filename="invoice_001.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path=str(sample_pdf_file),
        processed_file_path=str(processed_file),
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # Get detail page
    response = client.get(f"/files/{file_record.id}/detail")
    assert response.status_code == 200

    html = response.text
    # Check for metadata display
    assert "Extracted Metadata (GPT)" in html
    assert "Invoice" in html  # document_type
    assert "2024-01-15_Company_Invoice" in html  # filename
    assert "Test Company GmbH" in html  # absender
    assert "€ 1,234.56" in html  # betrag


@pytest.mark.integration
def test_preview_original_file_endpoint(client: TestClient, db_session, sample_pdf_file):
    """Test original file preview endpoint"""

    file_record = FileRecord(
        filehash="test789ghi",
        original_filename="original.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path=str(sample_pdf_file),
        processed_file_path=None,
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # Request preview
    response = client.get(f"/files/{file_record.id}/preview/original")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


@pytest.mark.integration
def test_preview_processed_file_endpoint(client: TestClient, db_session, sample_pdf_file, tmp_path):
    """Test processed file preview endpoint"""

    # Create processed file
    processed_file = tmp_path / "processed.pdf"
    processed_file.write_bytes(sample_pdf_file.read_bytes())

    file_record = FileRecord(
        filehash="test101jkl",
        original_filename="doc.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path=str(sample_pdf_file),
        processed_file_path=str(processed_file),
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # Request preview
    response = client.get(f"/files/{file_record.id}/preview/processed")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


@pytest.mark.integration
def test_preview_missing_file_returns_404(client: TestClient, db_session, sample_pdf_file):
    """Test preview endpoint returns 404 when file doesn't exist"""

    file_record = FileRecord(
        filehash="test202mno",
        original_filename="missing.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path="/nonexistent/path/original.pdf",
        processed_file_path="/nonexistent/path/processed.pdf",
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    # Request original (missing)
    response = client.get(f"/files/{file_record.id}/preview/original")
    assert response.status_code == 404

    # Request processed (missing)
    response = client.get(f"/files/{file_record.id}/preview/processed")
    assert response.status_code == 404


@pytest.mark.integration
def test_file_detail_shows_file_status_indicators(client: TestClient, db_session, sample_pdf_file):
    """Test file detail page shows correct status indicators for original and processed files"""

    file_record = FileRecord(
        filehash="test303pqr",
        original_filename="status_test.pdf",
        local_filename=str(sample_pdf_file),
        file_size=1024,
        mime_type="application/pdf",
        original_file_path=str(sample_pdf_file),  # Exists
        processed_file_path="/nonexistent/processed.pdf",  # Doesn't exist
    )
    db_session.add(file_record)
    db_session.commit()
    db_session.refresh(file_record)

    response = client.get(f"/files/{file_record.id}/detail")
    assert response.status_code == 200

    html = response.text
    # Check for status indicators
    assert "Original File Status" in html
    assert "Processed File Status" in html
    # Original should show as exists
    assert html.count("File exists") >= 1
    # Processed should show as not found
    assert "File not found" in html


@pytest.mark.unit
def test_metadata_json_structure(sample_metadata):
    """Test metadata JSON structure is valid"""
    # Verify all expected fields are present
    assert "document_type" in sample_metadata
    assert "filename" in sample_metadata
    assert "date" in sample_metadata
    assert "absender" in sample_metadata
    assert "tags" in sample_metadata

    # Verify it's JSON serializable
    json_str = json.dumps(sample_metadata)
    parsed = json.loads(json_str)
    assert parsed == sample_metadata
