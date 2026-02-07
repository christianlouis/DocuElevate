# API Documentation

DocuElevate provides a powerful REST API for programmatic access to all its features. This document serves as a reference for the available endpoints and their usage.

## API Overview

- Base URL: `http://<your-docuelevate-instance>/api`
- Authentication: OAuth2 (when enabled)
- Response Format: JSON

## Interactive API Documentation

The most up-to-date and interactive API documentation is available at:

`http://<your-docuelevate-instance>/docs`

This Swagger UI provides a complete reference with the ability to try out API calls directly from your browser.

## Authentication

When authentication is enabled, you must include an authentication token in your requests:

```bash
curl -X GET "http://<your-docuelevate-instance>/api/files" \
  -H "Authorization: Bearer <your-token>"
```

## Common Endpoints

### Document Upload

**POST** `/api/upload`

Upload one or more files for processing.

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

### Get Files

**GET** `/api/files`

Retrieve a list of processed files.

**Parameters**:
- `limit` (optional): Maximum number of files to return
- `offset` (optional): Pagination offset
- `search` (optional): Search term

**Response**:
```json
[
  {
    "id": 123,
    "original_filename": "invoice.pdf",
    "file_size": 1024000,
    "mime_type": "application/pdf",
    "created_at": "2023-04-15T12:30:45Z"
  },
  ...
]
```

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

### File Preview

**GET** `/api/files/{file_id}/preview`

Retrieve the file content for preview purposes.

**Parameters**:
- `version` (required): Either `original` or `processed`
  - `original`: Returns the file as it was uploaded (from tmp directory)
  - `processed`: Returns the file after metadata embedding (from processed directory)

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

## Rate Limiting

The API implements rate limiting to ensure system stability. If you exceed the limits, you'll receive a `429 Too Many Requests` response.


## Further Assistance

For additional help with the API, please contact our support team or refer to the [Development Guide](../CONTRIBUTING.md).
