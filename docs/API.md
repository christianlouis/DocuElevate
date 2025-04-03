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

Reprocess a specific file.

**Response**:
```json
{
  "success": true,
  "message": "File queued for reprocessing"
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
