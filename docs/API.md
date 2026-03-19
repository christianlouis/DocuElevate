# API Documentation

DocuElevate provides a powerful REST API for programmatic access to all its features. This document serves as a reference for the available endpoints and their usage.

> **Looking for a quick way to script against DocuElevate?**
> The built-in [CLI tool](./CLIGuide.md) wraps the API and is ready to use from a terminal or shell script — no HTTP client code required.

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

When authentication is enabled, you must include an authentication token in your requests.

### API Tokens (Recommended)

DocuElevate supports personal API tokens for programmatic access. Tokens are the recommended
way to authenticate scripts, CI/CD pipelines, and webhook integrations.

**Creating a token:**

1. Log in to DocuElevate and navigate to **API Tokens** (available in your user menu or at `/api-tokens`).
2. Enter a descriptive name (e.g. "CI Pipeline", "Scanner Integration") and click **Create Token**.
3. Copy the token immediately — it is shown only once.

**Using a token:**

```bash
curl -X GET "http://<your-docuelevate-instance>/api/files" \
  -H "Authorization: Bearer <your-api-token>"
```

**Managing tokens programmatically:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/api-tokens/` | Create a new token |
| `GET` | `/api/api-tokens/` | List all your tokens |
| `DELETE` | `/api/api-tokens/{id}` | Revoke (active) or permanently delete (revoked) a token |
| `POST` | `/api/api-tokens/{id}/reactivate` | Reactivate a revoked token |

### Session Authentication

Browser-based users authenticate via OAuth or local login. Session cookies are set
automatically and used for subsequent requests:

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

### Document Ownership (Multi-User Mode)

These endpoints are available when `MULTI_USER_ENABLED=true`.

---

**POST** `/api/files/{file_id}/claim`

Claim an unclaimed document (owner_id is NULL) for the current user.

```bash
curl -X POST "http://<your-instance>/api/files/42/claim"
```

**Response**:
```json
{
  "status": "success",
  "message": "Document claimed successfully",
  "file_id": 42,
  "owner_id": "alice@example.com"
}
```

**Error Responses**:
- `400`: Multi-user mode is not enabled
- `401`: Authentication required
- `403`: Document is already owned by another user

---

**POST** `/api/files/bulk-claim`

Claim multiple unclaimed documents at once. Already-owned documents are skipped.

**Request body**: JSON array of file IDs

```bash
curl -X POST "http://<your-instance>/api/files/bulk-claim" \
  -H "Content-Type: application/json" \
  -d '[1, 2, 3]'
```

**Response**:
```json
{
  "status": "success",
  "claimed_count": 2,
  "claimed_ids": [1, 3],
  "skipped": [{"file_id": 2, "reason": "already owned"}],
  "owner_id": "alice@example.com"
}
```

---

**POST** `/api/files/assign-owner`

**Admin only.** Assign an owner to documents. If `file_ids` body is omitted, assigns all
currently unclaimed documents to the specified owner.

**Query Parameters**:
- `owner_id` (required): The user identifier to assign

**Request body** (optional): JSON array of specific file IDs

```bash
# Assign all unclaimed documents to a user
curl -X POST "http://<your-instance>/api/files/assign-owner?owner_id=alice@example.com"

# Assign specific files
curl -X POST "http://<your-instance>/api/files/assign-owner?owner_id=alice@example.com" \
  -H "Content-Type: application/json" \
  -d '[1, 2, 3]'
```

**Response**:
```json
{
  "status": "success",
  "message": "Assigned owner to 5 document(s)",
  "updated_count": 5,
  "owner_id": "alice@example.com"
}
```

**Error Responses**:
- `400`: Multi-user mode is not enabled
- `403`: Only admins can assign document owners

---

**GET** `/api/users/search`

Search known user identifiers from existing documents. Powers the autocomplete widget
in the settings page for the `DEFAULT_OWNER_ID` field.

**Query Parameters**:
- `q` (optional): Substring to match against known owner IDs (case-insensitive)
- `limit` (optional): Maximum results to return (default: 5, max: 20)

```bash
curl "http://<your-instance>/api/users/search?q=risti&limit=5"
```

**Response**:
```json
{
  "users": ["christianlouis"]
}
```

---

### Admin User Management

**Admin only.** These endpoints let administrators list all known users, view per-user statistics,
and manage per-user settings such as custom upload limits, display names, and blocked status.

---

**GET** `/api/admin/users/`

List all known users — anyone who has uploaded a document or has an explicit profile.
Returns aggregate document statistics merged with profile data.

**Query Parameters**:
- `q` (optional): Substring filter on user ID (case-insensitive)
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Items per page (default: 25, max: 100)

```bash
curl "http://<your-instance>/api/admin/users/" \
  -H "Cookie: session=<admin-session>"
```

**Response**:
```json
{
  "users": [
    {
      "user_id": "alice@example.com",
      "display_name": "Alice Smith",
      "daily_upload_limit": 50,
      "notes": null,
      "is_blocked": false,
      "profile_id": 1,
      "document_count": 42,
      "last_upload": "2026-02-15T10:23:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 25,
  "pages": 1
}
```

---

**GET** `/api/admin/users/{user_id}`

Return profile and document statistics for a specific user.

```bash
curl "http://<your-instance>/api/admin/users/alice%40example.com"
```

---

**PUT** `/api/admin/users/{user_id}`

Create or update the admin-managed profile for a user. If no profile exists one is created.

**Request body**:
```json
{
  "display_name": "Alice Smith",
  "daily_upload_limit": 50,
  "notes": "VIP customer",
  "is_blocked": false
}
```

- `display_name` (optional): Human-readable name shown in the admin UI
- `daily_upload_limit` (optional): Per-user daily cap; `null` = use global default; `0` = unlimited
- `notes` (optional): Admin-only text notes
- `is_blocked`: When `true`, blocks new uploads from this user

---

**DELETE** `/api/admin/users/{user_id}`

Delete the admin-managed profile for a user. Documents owned by the user are **not** removed.
Returns `204 No Content` on success, `404` if no profile exists.

---

**POST** `/api/admin/users/{user_id}/payment-issue`

Report a payment issue for a user. Sends an admin notification (via configured Apprise channels) and
fires a `user.payment_issue` webhook event.  Use this endpoint when a payment processor (e.g.
Stripe, PayPal) sends a failed-charge notification or when a manual billing review identifies a
problem.

**Request body**:
```json
{
  "issue": "Card declined: insufficient funds"
}
```

- `issue` (required): Human-readable description of the payment problem (1–2048 characters)

**Response (200)**:
```json
{
  "acknowledged": true,
  "user_id": "alice@example.com",
  "profile": { ... }
}
```

**Error Responses**:
- `404`: User profile not found
- `403`: Admin access required
- `422`: Validation error (e.g. empty issue string)

---

**GET** `/api/admin/users/local`

List all local (email/password) user accounts with basic metadata.

---

**POST** `/api/admin/users/local`

Create a new local user account (admin-only, immediately active — no email verification required).

**Request body**:
```json
{
  "email": "user@example.com",
  "username": "alice",
  "display_name": "Alice Smith",
  "password": "securepassword",
  "is_admin": false
}
```

---

**PATCH** `/api/admin/users/local/{local_user_id}`

Update an existing local user account. Only the provided (non-null) fields are modified.
If the email is changed, the associated `UserProfile.user_id` is also updated automatically.

**Request body** (all fields optional):
```json
{
  "email": "newemail@example.com",
  "display_name": "Alice Wonderland",
  "is_admin": true,
  "is_active": false
}
```

**Error Responses**:
- `404`: Local user not found
- `409`: New email already taken by another account

---

**POST** `/api/admin/users/local/{local_user_id}/send-password-reset`

Send a password reset email to a local user on their behalf. Useful when a user is locked out.
Returns `{"sent": true}` on success or `{"sent": false, "reason": "..."}` when SMTP is not
configured or sending fails (never returns an error status so the admin always gets feedback).

**Error Responses**:
- `404`: Local user not found

---

**POST** `/api/admin/users/local/{local_user_id}/set-password`

Directly set a new password for a local user without requiring an email token (last resort when
email delivery is unavailable). The user should be advised to change their password after logging in.

**Request body**:
```json
{
  "password": "temporarypassword"
}
```

**Error Responses**:
- `404`: Local user not found
- `422`: Password shorter than 8 characters

---

**DELETE** `/api/admin/users/local/{local_user_id}`

Delete a local user account by numeric ID. The associated `UserProfile` is also removed. Documents
owned by this user are **not** deleted. Returns `204 No Content` on success.

---

### Local Authentication (self-service)

These endpoints are for local (email/password) users and do not require authentication.

**POST** `/api/auth/request-password-reset`

Send a password reset email. Always returns 200 to avoid leaking whether an email is registered.

**Request body**:
```json
{ "email": "user@example.com" }
```

---

**POST** `/api/auth/reset-password`

Set a new password using a valid reset token (received via email).

**Request body**:
```json
{
  "token": "the-token-from-email",
  "new_password": "newpassword",
  "new_password_confirm": "newpassword"
}
```

**Error Responses**:
- `400`: Token is invalid or expired
- `422`: Passwords do not match

---

**POST** `/api/auth/forgot-username`

Send a username reminder email. Always returns 200 to avoid leaking whether an email is registered.

**Request body**:
```json
{ "email": "user@example.com" }
```

---

### Settings Suggestions (Autocomplete)

**GET** `/api/settings/{key}/suggestions`

Return dynamic autocomplete suggestions for a setting. Providers attempt to
resolve values from cloud SDKs or installed tools and fall back to curated
static lists when unavailable.

**Supported keys**: `aws_region`, `azure_region`, `tesseract_language`,
`easyocr_languages`, `embedding_model`

**Query Parameters**:
- `q` (optional): Substring to filter suggestions (case-insensitive)
- `limit` (optional): Maximum results to return (default: 10, max: 50)

```bash
curl "http://<your-instance>/api/settings/aws_region/suggestions?q=east&limit=5"
```

**Response**:
```json
{
  "key": "aws_region",
  "suggestions": ["ap-east-1", "ap-northeast-1", "ap-southeast-1", "us-east-1", "us-east-2"]
}
```

**Error Responses**:
- `404`: No suggestion provider registered for the given key

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

### Similar Documents

**GET** `/api/files/{file_id}/similar`

Find documents similar to the specified file using pre-computed text embeddings and cosine similarity. Similarity scores range from 0 (completely different) to 1 (identical content). Embeddings are computed automatically during document ingestion and cached in the database.

**Parameters**:
- `limit` (optional, default: `5`, max: `20`): Maximum number of similar documents to return
- `threshold` (optional, default: `0.3`, range: `0.0–1.0`): Minimum similarity score to include

**Response**:
```json
{
  "file_id": 42,
  "similar_documents": [
    {
      "file_id": 15,
      "original_filename": "Invoice_2026-01.pdf",
      "document_title": "January Invoice",
      "similarity_score": 0.8934,
      "mime_type": "application/pdf",
      "created_at": "2026-01-15T10:30:00+00:00"
    }
  ],
  "count": 1
}
```

**Example**:
```bash
# Find top 5 similar documents
curl "http://<your-instance>/api/files/42/similar"

# Find top 10 documents with at least 50% similarity
curl "http://<your-instance>/api/files/42/similar?limit=10&threshold=0.5"
```

**Error Responses**:
- `404`: File not found
- `422`: Invalid query parameters (limit or threshold out of range)
- `500`: Internal error

> **Note:** Only pre-computed embeddings are used — no API calls are made during the query. If a file's embedding has not been computed yet, the response includes a `message` field explaining this. Documents without OCR text are excluded from similarity comparisons.

### Similarity Pairs (Corpus-Wide)

**GET** `/api/similarity/pairs`

Scan the entire document corpus for pairs of highly similar documents, ranked by score. Unlike the per-file `/files/{id}/similar` endpoint, this discovers all matching pairs across all files.

**Parameters**:
- `threshold` (optional, default: `0.7`, range: `0.0–1.0`): Minimum similarity score for a pair
- `limit` (optional, default: `50`, max: `200`): Maximum pairs per page
- `page` (optional, default: `1`): Page number

**Response**:
```json
{
  "pairs": [
    {
      "file_a": {
        "file_id": 1,
        "original_filename": "invoice_jan.pdf",
        "document_title": "January Invoice",
        "mime_type": "application/pdf",
        "created_at": "2026-01-15T10:30:00+00:00"
      },
      "file_b": {
        "file_id": 5,
        "original_filename": "invoice_feb.pdf",
        "document_title": "February Invoice",
        "mime_type": "application/pdf",
        "created_at": "2026-02-15T10:30:00+00:00"
      },
      "similarity_score": 0.94
    }
  ],
  "total_pairs": 12,
  "threshold": 0.7,
  "page": 1,
  "pages": 1,
  "per_page": 50,
  "embedding_coverage": {
    "total_files": 120,
    "files_with_embedding": 95
  }
}
```

**Example**:
```bash
# Find all document pairs above 90% similarity
curl "http://<your-instance>/api/similarity/pairs?threshold=0.9"
```

### Embedding Diagnostics

**GET** `/api/files/{file_id}/embedding-status`

Check the embedding status for a specific file: whether OCR text is available, whether an embedding has been computed, and how many dimensions it has.

```bash
curl "http://<your-instance>/api/files/42/embedding-status"
```

**POST** `/api/files/{file_id}/compute-embedding`

Manually trigger embedding computation for a single file. Useful for debugging or re-computing after configuration changes. Requires OCR text to be available.

```bash
curl -X POST "http://<your-instance>/api/files/42/compute-embedding"
```

**GET** `/api/diagnostic/embeddings`

Get an overview of embedding coverage across all files: total files, how many have OCR text, how many have embeddings, and per-file status.

```bash
curl "http://<your-instance>/api/diagnostic/embeddings"
```

**POST** `/api/diagnostic/compute-all-embeddings`

Queue embedding computation for all files that have OCR text but no embedding yet. Each file is processed as a separate background task.

```bash
curl -X POST "http://<your-instance>/api/diagnostic/compute-all-embeddings"
```

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

## Integrations

Manage per-user integrations (sources and destinations). All endpoints require authentication and are scoped to the current user's integrations. Subscription-tier quota enforcement is applied on creation.

### Quota Enforcement

When creating an integration, the API checks the user's subscription tier:

| Tier | Storage Destinations | IMAP Sources |
|------|---------------------|--------------|
| **Free** | 1 | 0 |
| **Starter** | 2 | 1 |
| **Professional** | 5 | 3 |
| **Power** | 10 | Unlimited |

Exceeding a quota returns HTTP 403 with a descriptive error message.

### GET /api/integrations/

List all integrations for the current user. Supports optional query-string filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `direction` | string | Filter by `SOURCE` or `DESTINATION` |
| `integration_type` | string | Filter by type (e.g. `IMAP`, `S3`, `DROPBOX`) |

**Response (200):**

```json
[
  {
    "id": 1,
    "owner_id": "user@example.com",
    "direction": "DESTINATION",
    "integration_type": "S3",
    "name": "Archive Bucket",
    "config": {"bucket": "my-bucket", "region": "us-east-1"},
    "has_credentials": true,
    "is_active": true,
    "last_used_at": null,
    "last_error": null,
    "created_at": "2025-01-01T00:00:00",
    "updated_at": "2025-01-01T00:00:00"
  }
]
```

### POST /api/integrations/

Create a new integration. Quota is enforced before creation.

**Request:**

```json
{
  "direction": "DESTINATION",
  "integration_type": "S3",
  "name": "Archive Bucket",
  "config": {"bucket": "my-bucket", "region": "us-east-1"},
  "credentials": {"access_key_id": "AKIA...", "secret_access_key": "..."},
  "is_active": true
}
```

**Response (201):** The created integration (same shape as list response).

**Response (403):** Quota exceeded.

```json
{
  "detail": "You have reached your plan limit of 1 storage destination(s). Please remove an existing destination or upgrade your plan."
}
```

### PUT /api/integrations/{id}

Update an existing integration. Only provided fields are changed.

### DELETE /api/integrations/{id}

Delete an integration permanently. Returns 204 on success.

### POST /api/integrations/test

Test an integration connection without saving. Useful for "Test connection" UI buttons.

**Request:**

```json
{
  "integration_type": "IMAP",
  "config": {"host": "imap.gmail.com", "port": 993, "username": "user@example.com", "use_ssl": true},
  "credentials": {"password": "app-password"}
}
```

**Response (200):**

```json
{"success": true, "message": "IMAP connection successful"}
```

Supported connection tests: `IMAP`, `S3`, `WEBDAV`, `NEXTCLOUD`. Other types return a message that testing is not yet supported.

### GET /api/integrations/quota/

Get the current user's integration quota usage.

**Response (200):**

```json
{
  "tier_id": "starter",
  "tier_name": "Starter",
  "destinations": {
    "current_count": 1,
    "max_allowed": 2,
    "can_add": true
  },
  "sources": {
    "current_count": 0,
    "max_allowed": 1,
    "can_add": true
  }
}
```

## Webhooks

Manage webhook configurations for notifying external systems when document events occur. All webhook endpoints require admin access.

### Supported Events

| Event | Description |
|-------|-------------|
| `document.uploaded` | A new document has been ingested |
| `document.processed` | A document finished processing successfully |
| `document.failed` | Document processing failed |
| `user.signup` | A new user account was created |
| `user.plan_changed` | A user's subscription plan changed |
| `user.payment_issue` | A payment issue was reported for a user |

### GET /api/webhooks/events/

List all valid webhook event types.

**Response (200):**
```json
["document.failed", "document.processed", "document.uploaded", "user.payment_issue", "user.plan_changed", "user.signup"]
```

### GET /api/webhooks/

List all webhook configurations. Secrets are never included in responses.

**Response (200):**
```json
[
  {
    "id": 1,
    "url": "https://example.com/webhook",
    "events": ["document.processed", "document.uploaded"],
    "is_active": true,
    "description": "Production webhook",
    "has_secret": true
  }
]
```

### POST /api/webhooks/

Create a new webhook configuration.

**Request:**
```json
{
  "url": "https://example.com/webhook",
  "secret": "my-shared-secret",
  "events": ["document.uploaded", "document.processed", "document.failed"],
  "is_active": true,
  "description": "My integration"
}
```

**Response (201):**
```json
{
  "id": 1,
  "url": "https://example.com/webhook",
  "events": ["document.failed", "document.processed", "document.uploaded"],
  "is_active": true,
  "description": "My integration",
  "has_secret": true
}
```

### GET /api/webhooks/{webhook_id}

Get a single webhook configuration.

**Response (200):** Same shape as list items above.

### PUT /api/webhooks/{webhook_id}

Update an existing webhook. Only supplied fields are changed.

**Request:**
```json
{
  "url": "https://new-url.example.com/webhook",
  "is_active": false
}
```

### DELETE /api/webhooks/{webhook_id}

Delete a webhook configuration. Returns `204 No Content` on success.

### Webhook Payload Format

When a subscribed event occurs, a JSON POST request is sent to the configured URL:

```json
{
  "event": "document.processed",
  "timestamp": 1709322559.123456,
  "data": {
    "file_id": 42,
    "filename": "invoice.pdf"
  }
}
```

### HMAC Signature

If a secret is configured, an `X-Webhook-Signature` header is included with each request. The signature is computed as `sha256=<hex-digest>` using HMAC-SHA256 over the raw JSON body.

To verify in Python:

```python
import hashlib, hmac

def verify_signature(body: bytes, secret: str, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Retry Behavior

Failed deliveries (non-2xx responses or network errors) are automatically retried with exponential backoff: 60 s, 300 s, then 900 s (up to 3 retries with ±20 % jitter).

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

## Diagnostic

### GET /api/diagnostic/health

System health endpoint designed for monitoring tools such as Grafana, Uptime Kuma, Prometheus blackbox exporter, or any HTTP-based health checker.

Checks the database and Redis connectivity and returns a machine-readable JSON summary.

**Authentication:** Required (bypassed when `AUTH_ENABLED=False`)

**Response (200 OK) – all subsystems healthy:**
```json
{
  "status": "healthy",
  "version": "1.2.3",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "checks": {
    "database": {"status": "ok"},
    "redis":    {"status": "ok"}
  }
}
```

**Response (200 OK) – one or more non-critical checks failed:**
```json
{
  "status": "degraded",
  "version": "1.2.3",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "checks": {
    "database": {"status": "ok"},
    "redis":    {"status": "error", "detail": "Connection refused"}
  }
}
```

**Response (503 Service Unavailable) – critical check (database) failed:**
```json
{
  "status": "unhealthy",
  "version": "1.2.3",
  "timestamp": "2024-01-15T10:30:00+00:00",
  "checks": {
    "database": {"status": "error", "detail": "..."},
    "redis":    {"status": "ok"}
  }
}
```

The `status` field is always one of:
- `"healthy"` – all checks passed
- `"degraded"` – at least one non-critical check failed (Redis unavailable)
- `"unhealthy"` – a critical check failed (database unavailable); HTTP 503 is returned

**Grafana / Uptime Kuma integration:** point your health check at `GET /api/diagnostic/health` and check for HTTP 200 or the JSON `status` field.

### POST /api/diagnostic/test-notification

Send a test notification through all configured notification channels.

**Authentication:** Required

**Response (200 OK):**
```json
{
  "status": "success",
  "message": "Test notification sent successfully to 2 service(s)",
  "services_count": 2
}
```

## Rate Limiting

The API implements rate limiting to ensure system stability. If you exceed the limits, you'll receive a `429 Too Many Requests` response.


## Database Configuration Wizard

Endpoints for building and testing database connection strings and migrating data between databases.  All write endpoints require admin authentication.

### GET /api/database/backends

List supported database backends with metadata.

**Response (200):**
```json
[
  {
    "id": "sqlite",
    "label": "SQLite (Development)",
    "default_port": null,
    "description": "File-based database. Best for development and single-user setups.",
    "requires_host": false
  },
  {
    "id": "postgresql",
    "label": "PostgreSQL (Recommended for Production)",
    "default_port": 5432,
    "description": "Robust, full-featured database. Recommended for production.",
    "requires_host": true
  }
]
```

### POST /api/database/build-url

Build a SQLAlchemy connection string from individual components.

**Request:**
```json
{
  "backend": "postgresql",
  "host": "my-db.rds.amazonaws.com",
  "port": 5432,
  "database": "docuelevate",
  "username": "admin",
  "password": "secret",
  "ssl_mode": "require"
}
```

**Response (200):**
```json
{
  "url": "postgresql://admin:secret@my-db.rds.amazonaws.com:5432/docuelevate?sslmode=require"
}
```

### POST /api/database/test-connection

Test connectivity to a database.

**Request:**
```json
{
  "url": "postgresql://admin:secret@my-db.rds.amazonaws.com:5432/docuelevate?sslmode=require"
}
```

**Response (200):**
```json
{
  "success": true,
  "message": "Connection successful",
  "backend": "postgresql",
  "server_version": "PostgreSQL 16.2 on x86_64-pc-linux-gnu"
}
```

### POST /api/database/preview-migration

Preview a data migration (table-by-table row counts) without copying data.

**Request:**
```json
{
  "url": "sqlite:///./app/database.db"
}
```

**Response (200):**
```json
{
  "success": true,
  "tables": [
    {"name": "documents", "row_count": 42},
    {"name": "files", "row_count": 150}
  ],
  "total_rows": 192
}
```

### POST /api/database/migrate

Execute a full data migration from source to target database.

**Request:**
```json
{
  "source_url": "sqlite:///./app/database.db",
  "target_url": "postgresql://admin:secret@host:5432/docuelevate"
}
```

**Response (200):**
```json
{
  "success": true,
  "tables_copied": 8,
  "rows_copied": 192,
  "errors": []
}
```


## Pipelines

The pipeline API lets you build and manage custom document processing workflows. Each pipeline is owned by a single user (or by the system when `owner_id` is `null`).

### Step-types catalogue

```bash
GET /api/pipelines/step-types
```

Returns the catalogue of built-in step types.

**Response (200):**
```json
{
  "convert_to_pdf": {
    "label": "Convert to PDF",
    "description": "Convert non-PDF documents to PDF format using Gotenberg.",
    "config_schema": {}
  },
  "ocr": {
    "label": "OCR Processing",
    "description": "Extract text using Azure Document Intelligence or local Tesseract.",
    "config_schema": {
      "force_cloud_ocr": { "type": "boolean", "default": false },
      "ocr_language": {
        "type": "select",
        "default": "auto",
        "description": "Language(s) for OCR. Overrides the global setting for Tesseract/EasyOCR. Azure/Mistral auto-detect.",
        "options": [
          { "value": "auto", "label": "Auto (use system default)" },
          { "value": "eng",  "label": "English" },
          { "value": "deu",  "label": "German" },
          { "value": "fra",  "label": "French" },
          { "value": "spa",  "label": "Spanish" },
          "..."
        ]
      }
    }
  }
}
```

The `ocr_language` field accepts Tesseract language codes (e.g. `"eng"`, `"deu"`, `"eng+deu"` for multi-language) or `"auto"` to fall back to the global system setting.  The full list of 28 supported language codes is returned by the step-types endpoint.

### List pipelines

```bash
GET /api/pipelines
```

Returns pipelines visible to the current user (own + system pipelines). Admins see all pipelines.

### Create pipeline

```bash
POST /api/pipelines
Content-Type: application/json

{
  "name": "My Workflow",
  "description": "Converts, OCRs, and stores documents.",
  "is_default": false,
  "is_active": true
}
```

**Response (201):**
```json
{
  "id": 1,
  "owner_id": "alice",
  "name": "My Workflow",
  "description": "Converts, OCRs, and stores documents.",
  "is_default": false,
  "is_active": true,
  "created_at": "2026-03-07T10:00:00+00:00",
  "updated_at": "2026-03-07T10:00:00+00:00"
}
```

### Create system pipeline (admin only)

```bash
POST /api/pipelines/admin/system
Content-Type: application/json

{
  "name": "Global Default",
  "is_default": true
}
```

### Get pipeline with steps

```bash
GET /api/pipelines/{pipeline_id}
```

**Response (200):**
```json
{
  "id": 1,
  "owner_id": "alice",
  "name": "My Workflow",
  "steps": [
    { "id": 1, "position": 0, "step_type": "convert_to_pdf", "enabled": true, "config": {} },
    { "id": 2, "position": 1, "step_type": "ocr", "enabled": true, "config": { "force_cloud_ocr": false } }
  ]
}
```

### Update pipeline

```bash
PUT /api/pipelines/{pipeline_id}
Content-Type: application/json

{ "name": "Renamed Workflow", "is_default": true }
```

### Delete pipeline

```bash
DELETE /api/pipelines/{pipeline_id}
```

Returns **204 No Content**.

### Add step

```bash
POST /api/pipelines/{pipeline_id}/steps
Content-Type: application/json

{
  "step_type": "ocr",
  "label": "German OCR",
  "config": { "force_cloud_ocr": false, "ocr_language": "deu" },
  "enabled": true
}
```

Multi-language (Tesseract `+`-separated codes):

```bash
{
  "step_type": "ocr",
  "config": { "ocr_language": "eng+deu" }
}
```

Use `"ocr_language": "auto"` (or omit the field) to fall back to the global system language setting.

### Update step

```bash
PUT /api/pipelines/{pipeline_id}/steps/{step_id}
Content-Type: application/json

{ "enabled": false }
```

### Delete step

```bash
DELETE /api/pipelines/{pipeline_id}/steps/{step_id}
```

Returns **204 No Content**.

### Reorder steps

```bash
PUT /api/pipelines/{pipeline_id}/steps/reorder
Content-Type: application/json

[3, 1, 2]
```

Provide a complete ordered list of **all** step IDs. Their positions are reassigned 0, 1, 2, … in the given order.

### Assign pipeline to a file

```bash
POST /api/files/{file_id}/assign-pipeline?pipeline_id=2
```

Pass no `pipeline_id` query parameter (or omit it) to clear the assignment.

**Response (200):**
```json
{ "file_id": 42, "pipeline_id": 2 }
```


## Routing Rules

Routing rules let you conditionally assign documents to different pipelines
based on file properties such as type, size, filename, or AI-extracted
metadata.  Rules are evaluated in **position order** (lowest first); the first
rule that matches wins.  If no rule matches, the system falls back to the
owner's (or global) default pipeline.

### Supported operators and fields

```bash
GET /api/routing-rules/operators
```

Returns the catalogue of valid operators and built-in fields so UIs can
populate dropdowns without hard-coding values.

**Response (200):**
```json
{
  "operators": ["contains", "equals", "gt", "gte", "lt", "lte", "not_contains", "not_equals", "regex"],
  "builtin_fields": ["category", "document_type", "file_type", "filename", "size"],
  "metadata_prefix": "metadata."
}
```

> **Tip:** For AI metadata fields use the `metadata.` prefix, e.g.
> `metadata.sender`, `metadata.amount`.

### List routing rules

```bash
GET /api/routing-rules
```

Returns the current user's rules **plus** any system-wide rules
(`owner_id = null`), ordered by position.

**Response (200):**
```json
[
  {
    "id": 1,
    "owner_id": "alice",
    "name": "Route invoices",
    "position": 0,
    "field": "document_type",
    "operator": "equals",
    "value": "Invoice",
    "target_pipeline_id": 3,
    "is_active": true,
    "created_at": "2026-03-09T12:00:00+00:00",
    "updated_at": "2026-03-09T12:00:00+00:00"
  }
]
```

### Create routing rule

```bash
POST /api/routing-rules
Content-Type: application/json

{
  "name": "Route invoices",
  "field": "document_type",
  "operator": "equals",
  "value": "Invoice",
  "target_pipeline_id": 3
}
```

Optional fields: `position` (auto-assigned if omitted), `is_active` (default `true`).

**Response (201 Created):** The created rule object.

### Get routing rule

```bash
GET /api/routing-rules/{rule_id}
```

**Response (200):** A single rule object.

### Update routing rule

```bash
PUT /api/routing-rules/{rule_id}
Content-Type: application/json

{ "name": "Renamed rule", "operator": "contains", "is_active": false }
```

Only the supplied fields are updated.

**Response (200):** The updated rule object.

### Delete routing rule

```bash
DELETE /api/routing-rules/{rule_id}
```

Returns **204 No Content**.

### Reorder routing rules

```bash
PUT /api/routing-rules/reorder
Content-Type: application/json

{ "rule_ids": [3, 1, 2] }
```

Provide the complete ordered list of your rule IDs.  Positions are reassigned
0, 1, 2, … in the given order.

### Evaluate rules (dry run)

```bash
POST /api/routing-rules/evaluate
Content-Type: application/json

{
  "file_type": "application/pdf",
  "filename": "invoice_2024.pdf",
  "size": 204800,
  "document_type": "Invoice",
  "metadata": { "sender": "Acme Corp" }
}
```

Tests which rule (if any) would match the given properties **without**
actually routing a document.

**Response (200) – match found:**
```json
{
  "matched": true,
  "rule": { "id": 1, "name": "Route invoices", "..." : "..." },
  "target_pipeline": { "id": 3, "name": "Invoice Pipeline", "is_active": true }
}
```

**Response (200) – no match:**
```json
{
  "matched": false,
  "rule": null,
  "target_pipeline": null
}
```


## API Tokens

Personal API tokens allow programmatic access to the DocuElevate API without
session cookies. Tokens are ideal for CI/CD pipelines, webhook integrations,
and automation scripts.

Each token is prefixed with `de_` for easy identification. Only a SHA-256 hash
is stored server-side; the plaintext is returned exactly once at creation time.

Usage tracking records when each token was last used and from which IP address.

### POST /api/api-tokens/

Create a new API token.  Optionally specify a lifetime in days via
`expires_in_days` (1–3650).  If omitted the token never expires.

**Request:**
```json
{
  "name": "CI Pipeline",
  "expires_in_days": 90
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "name": "CI Pipeline",
  "token_prefix": "de_Ab3xY7kL",
  "token": "de_Ab3xY7kLmN9pQrStUvWxYz0123456789abcdef",
  "is_active": true,
  "last_used_at": null,
  "last_used_ip": null,
  "created_at": "2026-03-08T12:00:00Z",
  "revoked_at": null,
  "expires_at": "2026-06-06T12:00:00Z"
}
```

> **Important:** The `token` field is only included in the creation response.
> Copy it immediately — it will not be shown again.

### GET /api/api-tokens/

List all tokens for the authenticated user. The full token value is never included.

**Response (200):**
```json
[
  {
    "id": 1,
    "name": "CI Pipeline",
    "token_prefix": "de_Ab3xY7kL",
    "is_active": true,
    "last_used_at": "2026-03-08T15:30:00Z",
    "last_used_ip": "203.0.113.42",
    "created_at": "2026-03-08T12:00:00Z",
    "revoked_at": null,
    "expires_at": "2026-06-06T12:00:00Z"
  }
]
```

### DELETE /api/api-tokens/{token_id}

Revoke or permanently delete a token:

* **Active token** – soft-revoked (kept for audit purposes, marked inactive).
  Response: `{"detail": "Token revoked"}`
* **Already-revoked token** – permanently deleted from the database.
  Response: `{"detail": "Token deleted"}`

**Response (200):**
```json
{
  "detail": "Token revoked"
}
```

### POST /api/api-tokens/{token_id}/reactivate

Reactivate a previously revoked token.  Clears `revoked_at` and sets
`is_active` back to `true`.

**Response (200):** The updated `TokenResponse` object.

### Using API Tokens

Include the token in the `Authorization` header of any API request:

```bash
# Upload a document
curl -X POST "http://your-instance/api/files/ui-upload" \
  -H "Authorization: Bearer de_your_token_here" \
  -F "file=@/path/to/document.pdf"

# List files
curl -X GET "http://your-instance/api/files" \
  -H "Authorization: Bearer de_your_token_here"
```

**Python example:**
```python
import requests

response = requests.post(
    "http://your-instance/api/files/ui-upload",
    headers={"Authorization": "Bearer de_your_token_here"},
    files={"file": open("document.pdf", "rb")},
)
print(response.json())
```


## Further Assistance

For additional help with the API, please contact our support team or refer to the [Development Guide](../CONTRIBUTING.md).

## Mobile App API

The mobile API provides endpoints used by the native iOS and Android app.  All endpoints require authentication (Bearer token or active session cookie).

For full mobile app documentation see [MobileApp.md](./MobileApp.md).

### POST /api/mobile/generate-token

Exchange an active web session for a long-lived API token scoped to the mobile app.

**Request:**
```json
{ "device_name": "John's iPhone" }
```

**Response (201 Created):**
```json
{
  "token": "de_AbCdEfGhIjKl...",
  "token_id": 42,
  "name": "Mobile App – John's iPhone",
  "created_at": "2026-03-10T09:30:00Z"
}
```

> The `token` is shown **once only**.

### POST /api/mobile/register-device

Register an Expo push token to receive push notifications.

**Request:**
```json
{
  "push_token": "ExponentPushToken[xxxxxx]",
  "device_name": "John's iPhone",
  "platform": "ios"
}
```

**Response (201 Created):** Device record with `id`, `platform`, `is_active`, `created_at`.

### GET /api/mobile/devices

List all registered push-notification devices for the current user.

**Response (200 OK):** Array of device records.

### DELETE /api/mobile/devices/{device_id}

Deactivate or permanently delete a push-notification device:

* **Active device** – soft-deactivated (record kept, will no longer receive push notifications).
  Response: `{"detail": "Device deactivated"}`
* **Already-inactive device** – permanently deleted from the database.
  Response: `{"detail": "Device deleted"}`

**Response (200)**

### GET /api/mobile/whoami

Return basic profile information for the authenticated user.

**Response (200 OK):**
```json
{
  "owner_id": "john@example.com",
  "display_name": "John Doe",
  "email": "john@example.com",
  "avatar_url": "https://www.gravatar.com/avatar/...",
  "is_admin": false
}
```

---

## GraphQL API

DocuElevate exposes a GraphQL API at `/graphql` alongside the REST API.  It
supports flexible queries with field selection, making it ideal for dashboards
and integrations that only need a subset of the available data.

### Endpoint

| Method | URL | Description |
|--------|-----|-------------|
| `POST` | `/graphql` | Execute a GraphQL query or mutation |
| `GET`  | `/graphql` | Open the GraphiQL interactive playground |

### Authentication

The GraphQL endpoint honours the same authentication rules as the REST API:

- **`AUTH_ENABLED=False`** (default, single-user mode): all queries are
  allowed without credentials.
- **`AUTH_ENABLED=True`** (multi-user mode): a valid session cookie **or**
  an `Authorization: Bearer <token>` API token is required.  Admin-only
  queries (settings, users) additionally require the `is_admin` flag.

### Available Queries

| Field | Returns | Notes |
|-------|---------|-------|
| `documents(ownerId, limit, offset)` | `[DocumentType]` | Paginated list of documents |
| `document(id)` | `DocumentType` | Single document by primary key |
| `pipelines(ownerId, limit, offset)` | `[PipelineType]` | Paginated list of pipelines with steps |
| `pipeline(id)` | `PipelineType` | Single pipeline by primary key |
| `settings(limit, offset)` | `[SettingType]` | Non-sensitive app settings (**admin only**) |
| `users(limit, offset)` | `[UserType]` | User profiles (**admin only**) |
| `user(userId)` | `UserType` | Single user profile (**admin only**) |

> **Note:** Sensitive configuration keys (API secrets, passwords, tokens) are
> automatically excluded from the `settings` query regardless of the caller's
> privilege level.

### GraphiQL Playground

Navigate to `http://<your-instance>/graphql` in a browser to open the
interactive GraphiQL IDE, which provides schema documentation, auto-complete,
and the ability to run queries directly.

### Example Queries

**List recent documents:**
```graphql
{
  documents(limit: 5) {
    id
    originalFilename
    mimeType
    fileSize
    documentTitle
    createdAt
  }
}
```

**Fetch a pipeline with its steps:**
```graphql
{
  pipeline(id: 1) {
    id
    name
    description
    isDefault
    isActive
    steps {
      position
      stepType
      label
      enabled
    }
  }
}
```

**List application settings (admin only):**
```graphql
{
  settings {
    key
    value
    updatedAt
  }
}
```

**List user profiles (admin only):**
```graphql
{
  users(limit: 10) {
    userId
    displayName
    subscriptionTier
    isBlocked
  }
}
```

**Using variables:**
```graphql
query GetDocument($id: Int!) {
  document(id: $id) {
    id
    originalFilename
    documentTitle
    isDuplicate
    ocrQualityScore
  }
}
```
Variables: `{ "id": 42 }`

## System Reset

Admin-only endpoints for resetting the system to a clean state.  Requires `ENABLE_FACTORY_RESET=True`.

### GET /api/admin/system-reset/status

Check whether the system reset feature is enabled.

**Response (200):**
```json
{
  "enabled": true,
  "factory_reset_on_startup": false
}
```

### POST /api/admin/system-reset/full

Wipe all user data (database + work-files).

**Request:**
```json
{
  "confirmation": "DELETE"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "result": {
    "database": { "files": 42, "processing_logs": 100 },
    "filesystem": { "deleted_dirs": 5, "deleted_files": 12 }
  }
}
```

### POST /api/admin/system-reset/reimport

Move original files to a reimport folder, wipe everything, and configure the reimport folder as a watch folder for re-ingestion.

**Request:**
```json
{
  "confirmation": "REIMPORT"
}
```

**Response (200):**
```json
{
  "status": "ok",
  "result": {
    "database": { "files": 42 },
    "filesystem": { "deleted_dirs": 5, "deleted_files": 12 },
    "reimport": { "files_moved": 42, "reimport_folder": "/workdir/reimport" }
  }
}
```
