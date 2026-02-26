"""
Canonical file-type lists for DocuElevate uploads.

All file types listed here are supported by Gotenberg (the PDF-conversion service
used by DocuElevate) via its LibreOffice, Chromium, or Markdown routes.  This
module is the single source of truth consumed by:

  - app/api/files.py        (ui-upload endpoint)
  - app/api/url_upload.py   (URL-upload endpoint)
  - app/tasks/imap_tasks.py (IMAP email-attachment ingestion)
  - frontend/static/js/upload.js  (client-side validation mirror)

Keep in sync with the OFFICE_EXTENSIONS / IMAGE_EXTENSIONS sets defined in
app/tasks/convert_to_pdf.py.
"""

# ---------------------------------------------------------------------------
# Document / office MIME types (converted via Gotenberg LibreOffice route)
# ---------------------------------------------------------------------------
DOCUMENT_MIME_TYPES: set[str] = {
    # PDF
    "application/pdf",
    # Word
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "application/vnd.ms-word.document.macroEnabled.12",
    "application/vnd.ms-word.template.macroEnabled.12",
    # Excel
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    # PowerPoint
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    # OpenDocument (LibreOffice native)
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.graphics",
    "application/vnd.oasis.opendocument.formula",
    # Plain text / data
    "text/plain",
    "text/csv",
    "application/rtf",
    "text/rtf",
    # HTML (converted via Gotenberg Chromium route)
    "text/html",
    # Markdown (converted via Gotenberg Chromium/Markdown route)
    "text/markdown",
    "text/x-markdown",
}

# ---------------------------------------------------------------------------
# Image MIME types (converted via Gotenberg LibreOffice route)
# ---------------------------------------------------------------------------
IMAGE_MIME_TYPES: set[str] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/webp",
    "image/svg+xml",
}

# ---------------------------------------------------------------------------
# Combined set – every MIME type accepted by the upload endpoints
# ---------------------------------------------------------------------------
ALLOWED_MIME_TYPES: set[str] = DOCUMENT_MIME_TYPES | IMAGE_MIME_TYPES

# ---------------------------------------------------------------------------
# File extensions (lower-case, with leading dot) accepted by Gotenberg
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS: set[str] = {
    # PDF
    ".pdf",
    # Word
    ".doc",
    ".docx",
    ".docm",
    ".dot",
    ".dotx",
    ".dotm",
    # Excel
    ".xls",
    ".xlsx",
    ".xlsm",
    ".xlsb",
    ".xlt",
    ".xltx",
    ".xlw",
    # PowerPoint
    ".ppt",
    ".pptx",
    ".pptm",
    ".pps",
    ".ppsx",
    ".pot",
    ".potx",
    # OpenDocument
    ".odt",
    ".ods",
    ".odp",
    ".odg",
    ".odf",
    # Text / data
    ".rtf",
    ".txt",
    ".csv",
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".svg",
    # Web
    ".html",
    ".htm",
    # Markdown
    ".md",
    ".markdown",
}
