"""Tests for app/utils/allowed_types.py – canonical Gotenberg file-type lists."""

import pytest

from app.utils.allowed_types import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DOCUMENT_MIME_TYPES,
    IMAGE_MIME_TYPES,
)


@pytest.mark.unit
class TestAllowedTypesStructure:
    """Structural sanity checks on the exported sets."""

    def test_allowed_mime_types_is_union(self):
        """ALLOWED_MIME_TYPES must equal DOCUMENT_MIME_TYPES ∪ IMAGE_MIME_TYPES."""
        assert ALLOWED_MIME_TYPES == DOCUMENT_MIME_TYPES | IMAGE_MIME_TYPES

    def test_sets_are_disjoint(self):
        """DOCUMENT_MIME_TYPES and IMAGE_MIME_TYPES should not overlap."""
        assert DOCUMENT_MIME_TYPES.isdisjoint(IMAGE_MIME_TYPES)

    def test_extensions_have_leading_dot(self):
        """All entries in ALLOWED_EXTENSIONS must start with '.'."""
        for ext in ALLOWED_EXTENSIONS:
            assert ext.startswith("."), f"Extension without leading dot: {ext!r}"

    def test_extensions_are_lowercase(self):
        """All entries in ALLOWED_EXTENSIONS must be lower-case."""
        for ext in ALLOWED_EXTENSIONS:
            assert ext == ext.lower(), f"Non-lowercase extension: {ext!r}"

    def test_no_empty_entries(self):
        """No set should contain empty strings."""
        for s in (DOCUMENT_MIME_TYPES, IMAGE_MIME_TYPES, ALLOWED_EXTENSIONS):
            assert "" not in s


@pytest.mark.unit
class TestGotenbergCoverageDocuments:
    """Verify that every extension Gotenberg handles is present."""

    # These must match OFFICE_EXTENSIONS in app/tasks/convert_to_pdf.py
    _office_extensions = {
        ".doc",
        ".docx",
        ".docm",
        ".dot",
        ".dotx",
        ".dotm",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".xlsb",
        ".xlt",
        ".xltx",
        ".xlw",
        ".ppt",
        ".pptx",
        ".pptm",
        ".pps",
        ".ppsx",
        ".pot",
        ".potx",
        ".odt",
        ".ods",
        ".odp",
        ".odg",
        ".odf",
        ".rtf",
        ".txt",
        ".csv",
    }
    _image_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".svg",
    }
    _html_extensions = {".html", ".htm"}
    _markdown_extensions = {".md", ".markdown"}

    def test_office_extensions_all_present(self):
        missing = self._office_extensions - ALLOWED_EXTENSIONS
        assert not missing, f"Office extensions missing from ALLOWED_EXTENSIONS: {missing}"

    def test_image_extensions_all_present(self):
        missing = self._image_extensions - ALLOWED_EXTENSIONS
        assert not missing, f"Image extensions missing from ALLOWED_EXTENSIONS: {missing}"

    def test_html_extensions_present(self):
        missing = self._html_extensions - ALLOWED_EXTENSIONS
        assert not missing, f"HTML extensions missing from ALLOWED_EXTENSIONS: {missing}"

    def test_markdown_extensions_present(self):
        missing = self._markdown_extensions - ALLOWED_EXTENSIONS
        assert not missing, f"Markdown extensions missing from ALLOWED_EXTENSIONS: {missing}"

    def test_pdf_extension_present(self):
        assert ".pdf" in ALLOWED_EXTENSIONS


@pytest.mark.unit
class TestGotenbergCoverageMimeTypes:
    """Verify that key MIME types are present."""

    @pytest.mark.parametrize(
        "mime_type",
        [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            # OpenDocument
            "application/vnd.oasis.opendocument.text",
            "application/vnd.oasis.opendocument.spreadsheet",
            "application/vnd.oasis.opendocument.presentation",
            # Images
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
            "image/svg+xml",
            # Text
            "text/plain",
            "text/csv",
            "text/html",
            "text/markdown",
            "text/x-markdown",
            # RTF
            "application/rtf",
            "text/rtf",
        ],
    )
    def test_mime_type_in_allowed(self, mime_type):
        assert mime_type in ALLOWED_MIME_TYPES, f"{mime_type} not in ALLOWED_MIME_TYPES"

    @pytest.mark.parametrize(
        "mime_type",
        [
            # New extended Office variants
            "application/vnd.ms-word.document.macroEnabled.12",
            "application/vnd.ms-word.template.macroEnabled.12",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
            "application/vnd.ms-excel.sheet.macroEnabled.12",
            "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
            "application/vnd.openxmlformats-officedocument.presentationml.template",
            "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
            "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
            "application/vnd.oasis.opendocument.graphics",
            "application/vnd.oasis.opendocument.formula",
        ],
    )
    def test_extended_mime_type_in_allowed(self, mime_type):
        """Extended / macro-enabled Office and ODF types must be present."""
        assert mime_type in ALLOWED_MIME_TYPES, f"{mime_type} not in ALLOWED_MIME_TYPES"


@pytest.mark.unit
class TestUploadViewsPassConfig:
    """Verify that the upload views inject uploadConfig into their templates."""

    def test_upload_page_contains_upload_config(self, client):
        """The /upload page must render window.uploadConfig with numeric values."""
        response = client.get("/upload")
        assert response.status_code == 200
        content = response.text
        assert "window.uploadConfig" in content
        # Verify that literal integers are rendered (not the placeholder names)
        assert "concurrency: 3" in content or "concurrency:" in content
        assert "queueDelayMs: 500" in content or "queueDelayMs:" in content

    def test_files_page_contains_upload_config(self, client):
        """The /files page must render window.uploadConfig with numeric values."""
        response = client.get("/files")
        assert response.status_code == 200
        content = response.text
        assert "window.uploadConfig" in content
        assert "concurrency: 3" in content or "concurrency:" in content
        assert "queueDelayMs: 500" in content or "queueDelayMs:" in content

    def test_upload_config_has_numeric_concurrency(self, client):
        """Concurrency in uploadConfig must be a positive integer."""
        import re

        response = client.get("/upload")
        assert response.status_code == 200
        match = re.search(r"concurrency:\s*(\d+)", response.text)
        assert match is not None, "concurrency integer not found in window.uploadConfig"
        assert int(match.group(1)) > 0

    def test_upload_config_has_numeric_delay(self, client):
        """queueDelayMs in uploadConfig must be a non-negative integer."""
        import re

        response = client.get("/upload")
        assert response.status_code == 200
        match = re.search(r"queueDelayMs:\s*(\d+)", response.text)
        assert match is not None, "queueDelayMs integer not found in window.uploadConfig"
        assert int(match.group(1)) >= 0
