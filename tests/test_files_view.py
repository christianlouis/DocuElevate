"""
Test the /files view UI endpoint to ensure template rendering works correctly.
"""
import pytest
from fastapi.testclient import TestClient
from app.models import FileRecord


def _assert_no_template_errors(content: str):
    """Helper function to check that min/max undefined errors are not present."""
    assert "'min' is undefined" not in content
    assert "'max' is undefined" not in content


@pytest.mark.integration
@pytest.mark.requires_db
class TestFilesView:
    """Tests for the /files UI view."""
    
    def test_files_view_renders_without_error(self, client: TestClient, db_session):
        """Test that the /files view renders without 'min' undefined error."""
        # Create some test files to ensure pagination works
        for i in range(10):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024 * (i + 1),
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Access the /files view
        response = client.get("/files")
        assert response.status_code == 200
        
        # Check that the response is HTML
        assert "text/html" in response.headers.get("content-type", "")
        
        # Check that the response contains expected content
        content = response.text
        assert "File Records" in content
        
        # Ensure no 'min' or 'max' is undefined error - this is the key fix we're testing
        _assert_no_template_errors(content)
    
    def test_files_view_pagination_with_many_pages(self, client: TestClient, db_session):
        """Test that pagination works correctly with many pages and min/max functions work."""
        # Create enough files to span multiple pages (e.g., 150 files with 50 per page = 3 pages)
        for i in range(150):
            file_record = FileRecord(
                filehash=f"hash{i}",
                original_filename=f"test{i}.pdf",
                local_filename=f"/tmp/test{i}.pdf",
                file_size=1024,
                mime_type="application/pdf"
            )
            db_session.add(file_record)
        db_session.commit()
        
        # Access the /files view with pagination
        response = client.get("/files?page=2&per_page=50")
        assert response.status_code == 200
        
        content = response.text
        
        # The key test: ensure the min/max functions work in the template
        # (they're used for pagination on lines 397 and 406 of files.html)
        _assert_no_template_errors(content)
