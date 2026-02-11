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
