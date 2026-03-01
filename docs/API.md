# API Documentation

DocuElevate provides a powerful REST API for programmatic access to all its features. This document serves as a reference for the available endpoints and their usage.

## API Overview

- Base URL: `http://<your-docuelevate-instance>/api`
- Authentication: OAuth2 (when enabled)
- Response Format: JSON
- Rate Limiting: Enabled by default (see Rate Limiting section below)

## Interactive API Documentation

The most up-to-date and interactive API documentation is available at:

`http://<your-docuelevate-instance>/docs`

This Swagger UI provides a complete reference with the ability to try out API calls directly from your browser.

## Rate Limiting

DocuElevate implements rate limiting to protect against abuse and DoS attacks. Rate limits are enforced per IP address for unauthenticated requests and per user for authenticated requests.

### Default Limits

- **Default endpoints**: 100 requests per minute
- **File upload**: 600 requests per minute
- **Authentication**: 10 requests per minute

**Note**: Document processing endpoints (OCR, metadata extraction) use built-in queue throttling to control processing rates and prevent upstream API overloads. No additional API-level rate limit is applied to processing endpoints.

### Rate Limit Headers

When a rate limit is exceeded, the API returns a `429 Too Many Requests` response:

```json
{
  "detail": "Rate limit exceeded: 100 per 1 minute"
}
```

The response includes a `Retry-After` header indicating when the client can retry the request.

### Configuration

Rate limits can be configured via environment variables:

```bash
RATE_LIMITING_ENABLED=true
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_UPLOAD=600/minute
RATE_LIMIT_AUTH=10/minute
```

See [Configuration Guide](ConfigurationGuide.md) for more details.

### Best Practices

1. **Respect rate limits**: Monitor your request rates and implement backoff strategies
2. **Cache responses**: Reduce unnecessary API calls by caching responses when appropriate
3. **Batch operations**: Use bulk endpoints when available instead of making multiple individual requests
4. **Handle 429 responses**: Implement retry logic with exponential backoff when rate limits are exceeded

### Example: Handling Rate Limits

```python
import requests
import time

def make_api_request(url, max_retries=3):
    """Make API request with rate limit handling."""
    for attempt in range(max_retries):
        response = requests.get(url)

        if response.status_code == 429:
            # Rate limit exceeded
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            continue

        return response

    raise Exception("Max retries exceeded")
```

## Authentication

When authentication is enabled, you must include an authentication token in your requests:

```bash
curl -X GET "http://<your-docuelevate-instance>/api/files" \
  -H "Authorization: Bearer <your-token>"
```

## Common Endpoints

### Document Upload

#### Upload from Computer

Upload a file from your computer to DocuElevate for processing.

**Endpoint**: `POST /api/upload`

**Request**:
```bash
curl -X POST "http://<your-docuelevate-instance>/api/upload" \
  -H "Authorization: Bearer <your-token>" \
  -F "file=@/path/to/document.pdf"
```

**Response (201 Created)**:
```json
{
  "task_id": "abc-123-def",
  "status": "queued",
  "message": "File uploaded and queued for processing",
  "filename": "document.pdf"
}
```

#### Upload from URL

Download and process a file from a URL. This endpoint is used by the browser extension.

**Endpoint**: `POST /api/process-url`

**Security Features**:
- SSRF protection (blocks private IPs, localhost, cloud metadata endpoints)
- File type validation (only supported document/image types)
- File size limits (enforces maximum upload size)
- Timeout protection (prevents hanging on slow/malicious servers)

**Request**:
```bash
curl -X POST "http://<your-docuelevate-instance>/api/process-url" \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/document.pdf",
    "filename": "custom-name.pdf"
  }'
```

**Request Body**:
```json
{
  "url": "https://example.com/document.pdf",
  "filename": "optional-custom-name.pdf"
}
```

**Response (200 OK)**:
```json
{
  "task_id": "abc-123-def",
  "status": "queued",
  "message": "File downloaded from URL and queued for processing",
  "filename": "document.pdf",
  "size": 1048576
}
```

**Error Responses**:

```json
// 400 Bad Request - Invalid URL or unsupported file type
{
  "detail": "Unsupported file type: text/html. Supported types: PDF, Office documents, images, plain text"
}

// 400 Bad Request - Private IP (SSRF protection)
{
  "detail": "Access to private/internal IP addresses is not allowed for security reasons"
}

// 408 Request Timeout
{
  "detail": "Request timeout: server took too long to respond"
}

// 413 Payload Too Large
{
  "detail": "File too large: 2097152 bytes (max 1048576 bytes)"
}

// 502 Bad Gateway
{
  "detail": "Failed to connect to URL: Connection refused"
}
```

**Usage with Browser Extension**:

The DocuElevate browser extension uses this endpoint to send files directly from your browser. See the [Browser Extension Guide](BrowserExtension.md) for installation and usage instructions.

**Supported File Types**:
- Documents: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV, RTF
- Images: JPG, PNG, GIF, BMP, TIFF, WebP, SVG

**POST** `/api/ui-upload`

Upload one or more files from your computer for processing.

**Request**:
- Multipart form data with file(s)

**Response**:
```json
{
  "success": true,
  "file_ids": [123, 124],
  "message": "Files uploaded and queued for processing"
}
```

#### Upload from URL

**POST** `/api/process-url`

Download a file from a URL and enqueue it for processing.

**Security Features**:
- SSRF protection: Blocks private IPs, localhost, and cloud metadata endpoints
- File type validation: Only allows supported document/image types
- File size limits: Enforces maximum upload size
- Timeout protection: Prevents hanging on slow/malicious servers

**Request Body**:
```json
{
  "url": "https://example.com/document.pdf",
  "filename": "my-document.pdf"  // optional
}
```

**Response**:
```json
{
  "task_id": "abc123",
  "status": "queued",
  "message": "File downloaded from URL and queued for processing",
  "filename": "document.pdf",
  "size": 1024000
}
```

**Error Responses**:
- `400`: Invalid URL, unsupported file type, or SSRF protection triggered
- `408`: Request timeout (server too slow)
- `413`: File too large
- `502`: Connection error
- `404`: File not found at URL
- `500`: Server error

**Supported File Types**:
- PDF documents
- Microsoft Office (Word, Excel, PowerPoint)
- Images (JPEG, PNG, GIF, BMP, TIFF, WebP, SVG)
- Plain text and CSV files

**Example**:
```bash
curl -X POST "http://localhost:8000/api/process-url" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/invoice.pdf",
    "filename": "march-invoice.pdf"
  }'
```

**SSRF Protection**:
The endpoint blocks access to:
- Private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Localhost (127.0.0.1, ::1)
- Link-local addresses (169.254.0.0/16)
- Cloud metadata endpoints (169.254.169.254, metadata.google.internal)

### Get Files

**GET** `/api/files`

Retrieve a paginated list of processed files with advanced filtering and sorting.

**Query Parameters**:
- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 25, max: 200): Items per page
- `sort_by` (optional, default: created_at): Sort field (`id`, `original_filename`, `file_size`, `mime_type`, `created_at`)
- `sort_order` (optional, default: desc): Sort order (`asc` or `desc`)
- `search` (optional): Search in filename (partial match)
- `mime_type` (optional): Filter by exact MIME type (e.g. `application/pdf`)
- `status` (optional): Filter by processing status (`pending`, `processing`, `completed`, `failed`, `duplicate`)
- `date_from` (optional): Filter files created on or after this date (ISO 8601, e.g. `2026-01-01`)
- `date_to` (optional): Filter files created on or before this date (ISO 8601, e.g. `2026-12-31`)
- `storage_provider` (optional): Filter by storage provider (e.g. `dropbox`, `s3`, `google_drive`, `onedrive`, `nextcloud`)
- `tags` (optional): Filter by tags in AI metadata (comma-separated, AND logic, e.g. `invoice,amazon`)
- `ocr_quality` (optional): Filter by AI-assessed OCR quality score (`poor` = score below threshold, `good` = score at or above threshold, `unchecked` = not yet assessed). The threshold is configured via `TEXT_QUALITY_THRESHOLD` (default: 85).

All filters are combinable using AND logic.

**Example**:
```
GET /api/files?status=completed&mime_type=application/pdf&tags=invoice&date_from=2026-01-01&sort_by=created_at&sort_order=desc
```

**Response**:
```json
{
  "files": [
    {
      "id": 123,
      "original_filename": "invoice.pdf",
      "file_size": 1024000,
      "mime_type": "application/pdf",
      "created_at": "2026-04-15T12:30:45Z",
      "processing_status": {
        "status": "completed",
        "last_step": "send_to_all_destinations",
        "has_errors": false,
        "total_steps": 8
      }
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 150,
    "pages": 6,
    "next": "http://host/api/files?page=2",
    "previous": null
  }
}
```

> **Tip**: Filter state is reflected in query parameters, making URLs shareable as bookmarks or direct links.

### Full-Text Search

**GET** `/api/search`

Search documents by full text across OCR content, titles, filenames, tags, sender, and document type. Powered by Meilisearch.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Full-text search query (1–512 chars) |
| `mime_type` | string | No | Filter by MIME type (e.g. `application/pdf`) |
| `document_type` | string | No | Filter by document type (e.g. `Invoice`) |
| `language` | string | No | Filter by language code (e.g. `de`, `en`) |
| `tags` | string | No | Filter by tag (exact match on a single tag) |
| `sender` | string | No | Filter by sender/absender (exact match) |
| `text_quality` | string | No | Filter by OCR text quality: `no_text`, `low`, `medium`, `high` |
| `date_from` | int | No | Filter results created after this Unix timestamp |
| `date_to` | int | No | Filter results created before this Unix timestamp |
| `page` | int | No | Page number, default: 1 |
| `per_page` | int | No | Results per page (1–100), default: 20 |

**Example**:
```
GET /api/search?q=invoice&document_type=Invoice&tags=amazon&text_quality=high&page=1
```

**Response**:
```json
{
  "results": [
    {
      "file_id": 42,
      "original_filename": "2026-01-15_Invoice_Amazon.pdf",
      "document_title": "Amazon Invoice January 2026",
      "document_type": "Invoice",
      "tags": ["amazon", "invoice"],
      "_formatted": {
        "document_title": "Amazon <mark>Invoice</mark> January 2026",
        "ocr_text": "...total amount of the <mark>invoice</mark> is..."
      }
    }
  ],
  "total": 42,
  "page": 1,
  "pages": 3,
  "query": "invoice"
}
```

### Saved Searches

Saved searches allow users to save and reuse filter combinations. Each user can store up to 50 saved searches.

Saved searches are used on both the **Files** page (for file management filters) and the **Search** page (for content-finding filters including full-text queries).

#### List Saved Searches

**GET** `/api/saved-searches`

Returns all saved searches for the current user.

**Response**:
```json
[
  {
    "id": 1,
    "name": "Recent Invoices",
    "filters": {
      "q": "invoice total",
      "tags": "invoice",
      "document_type": "Invoice",
      "date_from": "2026-01-01"
    },
    "created_at": "2026-03-01T10:00:00Z",
    "updated_at": "2026-03-01T10:00:00Z"
  }
]
```

#### Create Saved Search

**POST** `/api/saved-searches`

**Request Body**:
```json
{
  "name": "Recent Invoices",
  "filters": {
    "q": "invoice total",
    "tags": "invoice",
    "document_type": "Invoice",
    "date_from": "2026-01-01"
  }
}
```

**Allowed filter keys**:

Files-view keys: `search`, `mime_type`, `status`, `storage_provider`, `sort_by`, `sort_order`

Search-view keys: `q`, `document_type`, `language`, `sender`, `text_quality`

Shared keys: `tags`, `date_from`, `date_to`

**Response** (201 Created): The created saved search object.

#### Update Saved Search

**PUT** `/api/saved-searches/{id}`

**Request Body** (all fields optional):
```json
{
  "name": "Updated Name",
  "filters": {
    "tags": "invoice,amazon"
  }
}
```

**Response**: The updated saved search object.

#### Delete Saved Search

**DELETE** `/api/saved-searches/{id}`

**Response**: 204 No Content

### File Metadata

**GET** `/api/files/{file_id}/metadata`

Retrieve metadata for a specific file.

**Response**:
```json
{
  "document_type": "invoice",
  "date": "2023-04-10",
  "vendor": "Acme Corp",
  "amount": "$1,234.56",
  "extracted_text": "..."
}
```

### Process Control

**POST** `/api/files/{file_id}/reprocess`

Reprocess a specific file. This queues the file for complete reprocessing through the entire pipeline.

**Response**:
```json
{
  "status": "success",
  "message": "File queued for reprocessing",
  "file_id": 123,
  "filename": "invoice.pdf",
  "task_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6"
}
```

**Error Responses**:
- `404`: File not found
- `400`: Local file not found on disk (cannot reprocess)

**POST** `/api/files/{file_id}/reprocess-with-cloud-ocr`

Reprocess a specific file with forced Cloud OCR, regardless of embedded text quality. This is useful for documents with low-quality embedded text or when higher quality OCR is needed.

**Response**:
```json
{
  "status": "success",
  "message": "File queued for Cloud OCR reprocessing",
  "file_id": 123,
  "filename": "invoice.pdf",
  "task_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
  "force_cloud_ocr": true
}
```

**Error Responses**:
- `404`: File not found
- `400`: Neither original nor local file found on disk (cannot reprocess)

**Note**: This endpoint forces Azure Document Intelligence OCR processing even if the PDF contains embedded text. The original file (if available) is used for reprocessing to ensure the highest quality result.

### Bulk Operations

**POST** `/api/files/bulk-delete`

Delete multiple file records in a single request.

**Request body**: JSON array of file IDs

```bash
curl -X POST "http://<your-instance>/api/files/bulk-delete" \
  -H "Content-Type: application/json" \
  -d '[1, 2, 3]'
```

**Response**:
```json
{
  "status": "success",
  "message": "Successfully deleted 3 file records",
  "deleted_ids": [1, 2, 3]
}
```

**Error Responses**:
- `403`: File deletion is disabled in configuration
- `404`: No files found with the provided IDs

---

**POST** `/api/files/bulk-reprocess`

Queue multiple files for full reprocessing.

**Request body**: JSON array of file IDs

**Response**:
```json
{
  "status": "success",
  "message": "Successfully queued 2 files for reprocessing",
  "processed_files": [
    {"file_id": 1, "filename": "a.pdf", "task_id": "abc123"},
    {"file_id": 2, "filename": "b.pdf", "task_id": "def456"}
  ],
  "errors": [],
  "task_ids": ["abc123", "def456"]
}
```

---

**POST** `/api/files/bulk-reprocess-cloud-ocr`

Queue multiple files for reprocessing with forced Cloud OCR (Azure Document Intelligence). Useful for files that have missing or low-quality OCR text.

**Request body**: JSON array of file IDs

**Response**:
```json
{
  "status": "success",
  "message": "Successfully queued 2 files for Cloud OCR reprocessing",
  "processed_files": [
    {"file_id": 1, "filename": "a.pdf", "task_id": "abc123"}
  ],
  "errors": [],
  "task_ids": ["abc123"]
}
```

---

**POST** `/api/files/bulk-download`

Download multiple files as a single ZIP archive. For each file, the processed version is preferred; falls back to the original. Files not found on disk are silently skipped.

**Request body**: JSON array of file IDs

**Response**: `application/zip` stream with `Content-Disposition: attachment; filename="docuelevate_bulk_<timestamp>.zip"`

```bash
curl -X POST "http://<your-instance>/api/files/bulk-download" \
  -H "Content-Type: application/json" \
  -d '[1, 2, 3]' \
  --output bulk_download.zip
```

**Error Responses**:
- `404`: No files found with the provided IDs, or none of the selected files exist on disk

### File Preview

**GET** `/api/files/{file_id}/preview`

Retrieve the file content for preview purposes.

**Parameters**:
- `version` (required): Either `original` or `processed`
  - `original`: Returns the immutable original file from the original directory
  - `processed`: Returns the file after metadata embedding from the processed directory

**Response**: Returns the file content with appropriate MIME type for browser display.

**Example**:
```bash
# Preview original file
curl "http://<your-instance>/api/files/123/preview?version=original"

# Preview processed file
curl "http://<your-instance>/api/files/123/preview?version=processed"
```

**Error Responses**:
- `404`: File not found in database or on disk
- `400`: Invalid version parameter

### File Download

**GET** `/api/files/{file_id}/download`

Download a file as an attachment. The `Content-Disposition` header is set to `attachment` with the original filename so the browser prompts a save dialog.

**Parameters**:
- `version` (optional, default: `processed`): Either `processed` or `original`
  - `processed` *(default)*: Downloads the post-processing file (with embedded metadata)
  - `original`: Downloads the raw file as originally uploaded

**Response**: File content with `Content-Disposition: attachment; filename="<original_filename>"`.

**Example**:
```bash
# Download processed file (default)
curl -OJ "http://<your-instance>/api/files/123/download"

# Download original upload
curl -OJ "http://<your-instance>/api/files/123/download?version=original"
```

**Error Responses**:
- `404`: File not found in database or on disk
- `400`: Invalid `version` parameter (must be `processed` or `original`)

### Batch Processing

**POST** `/api/processall`

Process all PDF files in the configured workdir directory.

**Throttling**: For large batches (>20 files by default), tasks are automatically staggered to prevent overwhelming downstream APIs. The throttling behavior can be configured via environment variables:

- `PROCESSALL_THROTTLE_THRESHOLD`: Number of files above which throttling is applied (default: 20)
- `PROCESSALL_THROTTLE_DELAY`: Delay in seconds between each task submission when throttling (default: 3)

**Example**: When processing 25 files with default settings, the first file is queued immediately, the second after 3 seconds, the third after 6 seconds, etc., spreading the load over 72 seconds total.

**Response**:
```json
{
  "message": "Enqueued 25 PDFs for processing (throttled over 72 seconds)",
  "pdf_files": ["file1.pdf", "file2.pdf", ...],
  "task_ids": ["a1b2c3...", "d4e5f6...", ...],
  "throttled": true
}
```

**POST** `/send_to_google_drive/`

Send a processed file to Google Drive.

**Parameters**:
- `file_path`: Path to the file to upload

**Response**:
```json
{
  "task_id": "a1b2c3d4-e5f6-7g8h-9i0j-k1l2m3n4o5p6",
  "status": "queued"
}
```

## Error Handling

Errors follow standard HTTP status codes with descriptive messages:

```json
{
  "detail": "File not found",
  "status_code": 404
}
```

## Queue Monitoring

### GET /api/queue/stats

Get comprehensive queue and processing statistics, including Redis queue lengths, Celery worker inspection data, and database-level processing summaries.

**Authentication:** Required

**Response (200 OK):**
```json
{
  "queues": {
    "document_processor": 12,
    "default": 0,
    "celery": 0
  },
  "total_queued": 12,
  "celery": {
    "active": [
      {"id": "abc123", "name": "process_document", "args": "[42]", "started": 1700000000}
    ],
    "reserved": [],
    "scheduled": [],
    "workers_online": 1
  },
  "db_summary": {
    "total_files": 5000,
    "processing": 3,
    "failed": 1,
    "completed": 4900,
    "pending": 96,
    "recent_processing": [
      {"file_id": 42, "filename": "invoice.pdf", "current_step": "extract_metadata_with_gpt"}
    ]
  }
}
```

### GET /api/queue/pending-count

Lightweight endpoint returning the total number of queued + in-progress items. Designed for the files page banner indicator.

**Authentication:** Required

**Response (200 OK):**
```json
{
  "total_pending": 15
}
```

## Rate Limiting

The API implements rate limiting to ensure system stability. If you exceed the limits, you'll receive a `429 Too Many Requests` response.


## Further Assistance

For additional help with the API, please contact our support team or refer to the [Development Guide](../CONTRIBUTING.md).
