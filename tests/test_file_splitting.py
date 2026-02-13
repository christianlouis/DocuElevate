"""
Tests for the file splitting utility module.

Tests cover:
- PDF splitting by size
- Handling of edge cases (empty PDFs, single-page PDFs, etc.)
- Error handling
- should_split_file function
"""

import os
import tempfile

import pytest
from pypdf import PdfReader, PdfWriter  # Upgraded from PyPDF2 to fix CVE-2023-36464

from app.utils.file_splitting import should_split_file, split_pdf_by_size


@pytest.fixture
def sample_multipage_pdf():
    """Create a sample multi-page PDF for testing."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        writer = PdfWriter()

        # Add 5 pages to the PDF
        for i in range(5):
            writer.add_blank_page(width=200, height=200)

        writer.write(f)
        pdf_path = f.name

    yield pdf_path

    # Cleanup
    if os.path.exists(pdf_path):
        os.remove(pdf_path)


@pytest.fixture
def sample_single_page_pdf():
    """Create a sample single-page PDF for testing."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as f:
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.write(f)
        pdf_path = f.name

    yield pdf_path

    # Cleanup
    if os.path.exists(pdf_path):
        os.remove(pdf_path)


@pytest.mark.unit
class TestSplitPdfBySize:
    """Tests for the split_pdf_by_size function."""

    def test_split_pdf_basic(self, sample_multipage_pdf):
        """Test basic PDF splitting functionality."""
        # Use a very small size limit to force splitting
        max_size = 2000  # 2KB - should split the 5-page PDF

        split_files = split_pdf_by_size(sample_multipage_pdf, max_size)

        # Verify files were created (should be at least 1 file)
        assert len(split_files) >= 1, "PDF should create at least one file"

        # Verify all split files exist
        for split_file in split_files:
            assert os.path.exists(split_file), f"Split file {split_file} should exist"
            assert os.path.getsize(split_file) > 0, f"Split file {split_file} should not be empty"

        # Verify total pages match original
        original_reader = PdfReader(sample_multipage_pdf)
        total_split_pages = sum(len(PdfReader(f).pages) for f in split_files)
        assert total_split_pages == len(original_reader.pages), "Total pages should match original"

        # If we got more than 1 file, verify each file is under the limit (with some margin for PDF overhead)
        if len(split_files) > 1:
            # PDF_OVERHEAD_MULTIPLIER: PDFs have structural overhead (headers, metadata, compression)
            # that can cause files to exceed the target size by ~20-50%. We allow 1.5x (50%) margin.
            PDF_OVERHEAD_MULTIPLIER = 1.5
            for split_file in split_files:
                assert os.path.getsize(split_file) <= max_size * PDF_OVERHEAD_MULTIPLIER, (
                    f"Split file {split_file} should respect size limit (with PDF overhead allowance)"
                )

        # Cleanup split files
        for split_file in split_files:
            if os.path.exists(split_file):
                os.remove(split_file)

    def test_split_pdf_with_output_dir(self, sample_multipage_pdf):
        """Test PDF splitting with custom output directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            max_size = 5000

            split_files = split_pdf_by_size(sample_multipage_pdf, max_size, output_dir=temp_dir)

            # Verify files are in the specified directory
            for split_file in split_files:
                assert os.path.dirname(split_file) == temp_dir, "Split files should be in output_dir"
                assert os.path.exists(split_file), f"Split file {split_file} should exist"

            # Files will be cleaned up with temp_dir

    def test_split_pdf_single_page(self, sample_single_page_pdf):
        """Test splitting a single-page PDF."""
        max_size = 1000  # Very small limit

        split_files = split_pdf_by_size(sample_single_page_pdf, max_size)

        # Should create at least one file (might be just the single page)
        assert len(split_files) >= 1, "Should create at least one output file"

        # Verify the split file exists
        for split_file in split_files:
            assert os.path.exists(split_file), f"Split file {split_file} should exist"

        # Cleanup
        for split_file in split_files:
            if os.path.exists(split_file):
                os.remove(split_file)

    def test_split_pdf_large_limit(self, sample_multipage_pdf):
        """Test that PDF is not split when limit is very large."""
        max_size = 10 * 1024 * 1024  # 10MB - much larger than test PDF

        split_files = split_pdf_by_size(sample_multipage_pdf, max_size)

        # Should create only one file (no splitting needed)
        assert len(split_files) == 1, "PDF should not be split with large limit"

        # Verify total pages match
        original_reader = PdfReader(sample_multipage_pdf)
        split_reader = PdfReader(split_files[0])
        assert len(split_reader.pages) == len(original_reader.pages), "All pages should be in single file"

        # Cleanup
        for split_file in split_files:
            if os.path.exists(split_file):
                os.remove(split_file)

    def test_split_pdf_file_not_found(self):
        """Test error handling when PDF file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            split_pdf_by_size("/nonexistent/file.pdf", 1000)

    def test_split_pdf_invalid_pdf(self):
        """Test error handling with invalid/corrupted PDF."""
        # Create a file that's not a valid PDF
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pdf", delete=False) as f:
            f.write("This is not a PDF file")
            invalid_pdf = f.name

        try:
            with pytest.raises(ValueError, match="Invalid or corrupted PDF"):
                split_pdf_by_size(invalid_pdf, 1000)
        finally:
            if os.path.exists(invalid_pdf):
                os.remove(invalid_pdf)

    def test_split_pdf_naming_convention(self, sample_multipage_pdf):
        """Test that split files follow expected naming convention."""
        max_size = 5000

        split_files = split_pdf_by_size(sample_multipage_pdf, max_size)

        # Verify naming pattern: basename_partN.pdf
        base_name = os.path.splitext(os.path.basename(sample_multipage_pdf))[0]

        for i, split_file in enumerate(split_files, start=1):
            filename = os.path.basename(split_file)
            assert filename.startswith(base_name), f"Filename should start with {base_name}"
            assert f"_part{i}.pdf" in filename, f"Filename should contain _part{i}.pdf"

        # Cleanup
        for split_file in split_files:
            if os.path.exists(split_file):
                os.remove(split_file)

    def test_split_pdfs_are_valid_and_readable(self, sample_multipage_pdf):
        """Test that split PDFs are valid, complete PDFs that can be opened and read.

        This test verifies that PDF splitting is done at PAGE BOUNDARIES,
        not by byte position, ensuring no corrupted/broken PDFs are created.
        """
        max_size = 5000  # Small size to force splitting

        split_files = split_pdf_by_size(sample_multipage_pdf, max_size)

        try:
            # Verify each split file is a valid, readable PDF
            for split_file in split_files:
                assert os.path.exists(split_file), f"Split file {split_file} should exist"

                # Try to open and read the PDF - this will fail if PDF is corrupted
                try:
                    reader = PdfReader(split_file)
                    # Verify it has pages (not an empty or broken PDF)
                    assert len(reader.pages) > 0, f"Split PDF {split_file} should have pages"

                    # Try to access first page content to ensure PDF structure is valid
                    first_page = reader.pages[0]
                    # If the PDF was corrupted by byte-splitting, this would raise an error
                    _ = first_page.extract_text()  # This validates PDF structure

                except Exception as e:
                    pytest.fail(
                        f"Split PDF {split_file} is corrupted or unreadable. "
                        f"This indicates byte-level splitting instead of page-level splitting. Error: {e}"
                    )

        finally:
            # Cleanup
            for split_file in split_files:
                if os.path.exists(split_file):
                    os.remove(split_file)


@pytest.mark.unit
class TestShouldSplitFile:
    """Tests for the should_split_file function."""

    def test_should_split_when_file_exceeds_limit(self, sample_multipage_pdf):
        """Test that function returns True when file exceeds limit."""
        file_size = os.path.getsize(sample_multipage_pdf)
        max_size = file_size - 1  # Set limit just below file size

        result = should_split_file(sample_multipage_pdf, max_size)
        assert result is True, "Should return True when file exceeds limit"

    def test_should_not_split_when_file_under_limit(self, sample_multipage_pdf):
        """Test that function returns False when file is under limit."""
        file_size = os.path.getsize(sample_multipage_pdf)
        max_size = file_size + 1000  # Set limit above file size

        result = should_split_file(sample_multipage_pdf, max_size)
        assert result is False, "Should return False when file is under limit"

    def test_should_not_split_when_limit_is_none(self, sample_multipage_pdf):
        """Test that function returns False when max_single_file_size is None."""
        result = should_split_file(sample_multipage_pdf, None)
        assert result is False, "Should return False when limit is None (splitting disabled)"

    def test_should_not_split_when_file_not_exists(self):
        """Test that function returns False when file doesn't exist."""
        result = should_split_file("/nonexistent/file.pdf", 1000)
        assert result is False, "Should return False when file doesn't exist"

    def test_should_not_split_exact_size(self, sample_multipage_pdf):
        """Test behavior when file size exactly matches limit."""
        file_size = os.path.getsize(sample_multipage_pdf)

        result = should_split_file(sample_multipage_pdf, file_size)
        assert result is False, "Should return False when file size equals limit"
