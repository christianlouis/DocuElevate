# Configuration Guide

DocuElevate is designed to be highly configurable through environment variables. This guide explains all available configuration options and how to use them effectively.

## Environment Variables

Configuration is primarily done through environment variables specified in a `.env` file.

### Core Settings

| **Variable**           | **Description**                                          | **Example**                    |
|------------------------|----------------------------------------------------------|--------------------------------|
| `DATABASE_URL`         | Path/URL to the SQLite database (or other SQL backend). Use the [Database Wizard](/database-wizard) for guided setup. See [Database Configuration](DatabaseConfiguration.md). | `sqlite:///./app/database.db`  |
| `DB_POOL_SIZE`         | Number of persistent connections in the pool per worker (PostgreSQL/MySQL only; ignored for SQLite). | `10` |
| `DB_MAX_OVERFLOW`      | Additional connections beyond `DB_POOL_SIZE` under burst load (PostgreSQL/MySQL only). | `20` |
| `DB_POOL_TIMEOUT`      | Seconds to wait for a pool connection before raising `TimeoutError` (PostgreSQL/MySQL only). | `30` |
| `DB_POOL_RECYCLE`      | Recycle connections after this many seconds to avoid stale connections (PostgreSQL/MySQL only). | `1800` |
| `REDIS_URL`            | URL for Redis, used by Celery for broker & result store. | `redis://redis:6379/0`         |
| `WORKDIR`              | Working directory for the application.                  | `/workdir`                     |
| `GOTENBERG_URL`        | Gotenberg PDF processing URL.                           | `http://gotenberg:3000`        |
| `EXTERNAL_HOSTNAME`    | The external hostname for the application.             | `docuelevate.example.com`      |
| `ALLOW_FILE_DELETE`    | Enable file deletion in the web interface (`true`/`false`). | `true`                      |
| `COMPLIANCE_ENABLED`   | Enable the compliance templates dashboard (GDPR, HIPAA, SOC 2). | `true`                      |
| `FACTORY_RESET_ON_STARTUP` | Wipe all user data on every startup (demo/testing). | `false` |
| `ENABLE_FACTORY_RESET` | Show the System Reset page in the admin UI.         | `false` |

### Batch Processing Settings

Control how the `/processall` endpoint handles large batches of files to prevent overwhelming downstream APIs.

| **Variable**                      | **Description**                                                                                    | **Default** |
|-----------------------------------|----------------------------------------------------------------------------------------------------|-------------|
| `PROCESSALL_THROTTLE_THRESHOLD`   | Number of files above which throttling is applied. Files <= threshold are processed immediately.  | `20`        |
| `PROCESSALL_THROTTLE_DELAY`       | Delay in seconds between each task submission when throttling is active.                          | `3`         |

**Example Usage**: When processing 25 files with default settings:
- Files are staggered: file 0 at 0s, file 1 at 3s, file 2 at 6s, etc.
- Total queue time: (25-1) × 3 = 72 seconds
- Prevents API rate limit issues and ensures smooth processing

### Task Retry Settings

Failed Celery tasks are automatically retried with exponential backoff and optional jitter. Different task types use different default delays (OCR tasks wait longer than upload tasks to account for API rate limits).

| **Variable**             | **Description**                                                                                                                                   | **Default**     |
|--------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|-----------------|
| `TASK_RETRY_MAX_RETRIES` | Maximum number of retry attempts for any failed task.                                                                                             | `3`             |
| `TASK_RETRY_DELAYS`      | Comma-separated list of countdown values in seconds for each retry attempt. Values beyond the list double the last entry for subsequent retries. | `60,300,900`    |
| `TASK_RETRY_JITTER`      | Apply ±20 % random jitter to countdowns to prevent thundering-herd problems when many tasks fail at the same time.                               | `true`          |

**Per-task-type policies** (not overridable via environment variables; set in code):

| Task type               | Default delays (s)     | Notes                                               |
|-------------------------|------------------------|-----------------------------------------------------|
| General tasks           | 60, 300, 900           | Controlled by `TASK_RETRY_DELAYS`                   |
| OCR / AI tasks          | 120, 600, 1800         | Longer waits for API rate-limit windows to clear    |
| Cloud-storage uploads   | 60, 300, 900           | Controlled by `TASK_RETRY_DELAYS`                   |

**Example – aggressive retries for a high-availability setup:**

```dotenv
TASK_RETRY_MAX_RETRIES=5
TASK_RETRY_DELAYS=30,120,600,1800,3600
TASK_RETRY_JITTER=true
```

**Example – conservative retries with longer back-off:**

```dotenv
TASK_RETRY_MAX_RETRIES=3
TASK_RETRY_DELAYS=300,900,3600
TASK_RETRY_JITTER=true
```

### Client-Side Upload Throttling

Control how the web UI queues and paces file uploads to avoid overwhelming the backend, especially when dragging large directories (potentially thousands of files) onto the upload area.

| **Variable**               | **Description**                                                                                                               | **Default** |
|----------------------------|-------------------------------------------------------------------------------------------------------------------------------|-------------|
| `UPLOAD_CONCURRENCY`       | Maximum number of files uploaded simultaneously from the browser.                                                            | `3`         |
| `UPLOAD_QUEUE_DELAY_MS`    | Delay in milliseconds between starting each upload slot. Staggers upload starts to smooth out server load.                   | `500`       |

**Adaptive back-off**: The browser automatically slows down if the server responds with HTTP 429 (Too Many Requests). It reads the `Retry-After` header, pauses the queue for the indicated time, doubles the inter-slot delay (exponential back-off, capped at 30 s), and reduces concurrency to 1. After 5 consecutive successes it gradually recovers toward the configured values.

**Example**: With `UPLOAD_CONCURRENCY=3` and `UPLOAD_QUEUE_DELAY_MS=500`, a directory of 5,000 files is uploaded ≈ 3 at a time with 500 ms pacing – the backend processes files at its own rate while the queue drains in the background without triggering API rate limits.

### File Upload Size Limits

**Security Feature**: Control file upload sizes to prevent resource exhaustion attacks. See [SECURITY_AUDIT.md](../SECURITY_AUDIT.md#5-file-upload-size-limits) for security details.

| **Variable**              | **Description**                                                                                              | **Default**   |
|---------------------------|--------------------------------------------------------------------------------------------------------------|---------------|
| `MAX_UPLOAD_SIZE`         | Maximum file upload size in bytes. Files exceeding this limit are rejected.                                | `1073741824` (1GB) |
| `MAX_SINGLE_FILE_SIZE`    | Optional: Maximum size for a single file chunk in bytes. Files exceeding this are split into smaller parts. | `None` (no splitting) |
| `MAX_REQUEST_BODY_SIZE`   | Maximum request body size in bytes for non-file-upload requests (JSON, form data, etc.). File uploads use `MAX_UPLOAD_SIZE` instead. | `1048576` (1MB) |

**Configuration Examples:**

```bash
# Default: Allow up to 1GB uploads, no splitting, 1MB JSON/form body limit
MAX_UPLOAD_SIZE=1073741824
MAX_REQUEST_BODY_SIZE=1048576

# Conservative: 100MB max, split files over 50MB
MAX_UPLOAD_SIZE=104857600
MAX_SINGLE_FILE_SIZE=52428800

# Large files: 2GB max, split files over 500MB
MAX_UPLOAD_SIZE=2147483648
MAX_SINGLE_FILE_SIZE=524288000
```

**File Splitting Behavior:**
- When `MAX_SINGLE_FILE_SIZE` is configured and a PDF exceeds this size, it is automatically split into smaller chunks
- **IMPORTANT:** Splitting is done at **PAGE BOUNDARIES**, not by byte position
  - Uses pypdf to properly parse PDF structure
  - Each output file is a complete, valid PDF containing whole pages
  - No risk of corrupted or broken PDF files
  - Pages are distributed across output files to stay under size limit
- Each chunk is processed sequentially as a separate task
- Only works for PDF files (images and office documents are converted to PDF first)
- Original file is removed after successful splitting
- Useful for very large PDFs to prevent memory issues during processing

**Use Cases:**
- **Default (1GB, no splitting)**: Suitable for most deployments handling typical documents
- **With splitting**: Recommended for servers with limited memory or when processing very large scanned documents
- **Higher limits**: For environments specifically designed to handle large architectural plans, books, or scanned archives

### Watch Folder Ingestion

DocuElevate can automatically monitor directories for new files and ingest them without any manual action.
This works for:
- **Local filesystem paths** — including SMB/CIFS shares, NFS mounts, or any path accessible to the Docker container
- **FTP server directories** — using the configured FTP connection credentials
- **SFTP server directories** — using the configured SFTP connection credentials

#### Local Watch Folders

Mount the share or directory into the Docker container and configure one or more paths to watch.

| **Variable**                        | **Description**                                                                              | **Default** |
|-------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `WATCH_FOLDERS`                     | Comma-separated list of **absolute** local filesystem paths to poll for new files.          | *(empty)*   |
| `WATCH_FOLDER_POLL_INTERVAL`        | How often to scan the folders, in minutes.                                                  | `1`         |
| `WATCH_FOLDER_DELETE_AFTER_PROCESS` | Delete source files from the watch folder after they are successfully enqueued. When `false`, processed files are tracked in a cache file to prevent re-ingestion. | `false` |

**Example (docker-compose.yaml):**

```yaml
services:
  worker:
    volumes:
      - /mnt/smb/scanner:/watchfolders/scanner  # SMB/CIFS share mounted on the host
      - /mnt/nfs/inbox:/watchfolders/inbox       # NFS mount
    environment:
      WATCH_FOLDERS: /watchfolders/scanner,/watchfolders/inbox
      WATCH_FOLDER_POLL_INTERVAL: 1
      WATCH_FOLDER_DELETE_AFTER_PROCESS: false
```

> **Tip for HP Scanners and MFPs**: Configure your scanner's "Scan to Network Folder" to point at an SMB share that is also mounted into the DocuElevate worker container. DocuElevate will pick up the scan files automatically every minute. No email forwarding is required.

#### FTP Ingest (Watch Folder)

DocuElevate can poll an FTP server directory for new files. It reuses the FTP connection settings already configured for uploads.

| **Variable**                      | **Description**                                                                                | **Default** |
|-----------------------------------|------------------------------------------------------------------------------------------------|-------------|
| `FTP_INGEST_ENABLED`              | Enable FTP folder watching (`true`/`false`).                                                  | `false`     |
| `FTP_INGEST_FOLDER`               | Path on the FTP server to poll (e.g. `/incoming`). Uses the existing FTP connection settings. | *(empty)*   |
| `FTP_INGEST_DELETE_AFTER_PROCESS` | Delete files from the FTP server after they are downloaded and enqueued.                      | `false`     |

**Example:**

```dotenv
# Existing FTP upload settings (also used for ingest)
FTP_HOST=ftp.example.com
FTP_USERNAME=docuelevate
FTP_PASSWORD=secret

# FTP ingest configuration
FTP_INGEST_ENABLED=true
FTP_INGEST_FOLDER=/incoming
FTP_INGEST_DELETE_AFTER_PROCESS=false
```

#### SFTP Ingest (Watch Folder)

DocuElevate can poll an SFTP server directory for new files. It reuses the SFTP connection settings already configured for uploads.

| **Variable**                       | **Description**                                                                                 | **Default** |
|------------------------------------|-------------------------------------------------------------------------------------------------|-------------|
| `SFTP_INGEST_ENABLED`              | Enable SFTP folder watching (`true`/`false`).                                                  | `false`     |
| `SFTP_INGEST_FOLDER`               | Path on the SFTP server to poll (e.g. `/uploads/inbox`). Uses the existing SFTP connection settings. | *(empty)* |
| `SFTP_INGEST_DELETE_AFTER_PROCESS` | Delete files from the SFTP server after they are downloaded and enqueued.                      | `false`     |

**Example:**

```dotenv
# Existing SFTP upload settings (also used for ingest)
SFTP_HOST=sftp.example.com
SFTP_USERNAME=docuelevate
SFTP_PRIVATE_KEY=/run/secrets/sftp_key

# SFTP ingest configuration
SFTP_INGEST_ENABLED=true
SFTP_INGEST_FOLDER=/uploads/inbox
SFTP_INGEST_DELETE_AFTER_PROCESS=false
```

#### Supported File Types for Watch Folders

Watch folder ingestion accepts the same file types as the web upload interface: PDF, Word, Excel, PowerPoint, images (JPEG, PNG, TIFF, BMP, GIF), plain text, CSV, RTF, and more. Unsupported files (executables, archives, etc.) are silently skipped.

#### Dropbox Ingest (Watch Folder)

DocuElevate can poll a Dropbox folder for new files. It reuses the Dropbox OAuth credentials already configured for uploads.

| **Variable**                          | **Description**                                                                              | **Default** |
|---------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `DROPBOX_INGEST_ENABLED`              | Enable Dropbox folder watching (`true`/`false`).                                            | `false`     |
| `DROPBOX_INGEST_FOLDER`               | Dropbox folder path to poll (e.g. `/Inbox/Scanner`). Uses the existing Dropbox OAuth credentials. | *(empty)* |
| `DROPBOX_INGEST_DELETE_AFTER_PROCESS` | Delete files from Dropbox after they are downloaded and enqueued.                          | `false`     |

#### Google Drive Ingest (Watch Folder)

DocuElevate can poll a Google Drive folder for new files. It reuses the existing Google Drive service-account or OAuth credentials.

| **Variable**                                 | **Description**                                                                              | **Default** |
|----------------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `GOOGLE_DRIVE_INGEST_ENABLED`                | Enable Google Drive folder watching (`true`/`false`).                                       | `false`     |
| `GOOGLE_DRIVE_INGEST_FOLDER_ID`              | Google Drive **folder ID** to poll (copy from the URL of the target folder in Drive). Uses the existing Google Drive credentials. | *(empty)* |
| `GOOGLE_DRIVE_INGEST_DELETE_AFTER_PROCESS`   | Delete files from Google Drive after they are downloaded and enqueued.                      | `false`     |

#### OneDrive Ingest (Watch Folder)

DocuElevate can poll a OneDrive folder for new files. It reuses the existing OneDrive MSAL (client ID/secret/refresh token) credentials.

| **Variable**                               | **Description**                                                                              | **Default** |
|--------------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `ONEDRIVE_INGEST_ENABLED`                  | Enable OneDrive folder watching (`true`/`false`).                                           | `false`     |
| `ONEDRIVE_INGEST_FOLDER_PATH`              | OneDrive folder path to poll (e.g. `/Inbox/Scanner`). Uses the existing OneDrive credentials. | *(empty)* |
| `ONEDRIVE_INGEST_DELETE_AFTER_PROCESS`     | Delete files from OneDrive after they are downloaded and enqueued.                          | `false`     |

#### Nextcloud Ingest (Watch Folder)

DocuElevate can poll a Nextcloud folder via WebDAV for new files. It reuses the existing Nextcloud upload URL and credentials.

| **Variable**                               | **Description**                                                                              | **Default** |
|--------------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `NEXTCLOUD_INGEST_ENABLED`                 | Enable Nextcloud folder watching (`true`/`false`).                                          | `false`     |
| `NEXTCLOUD_INGEST_FOLDER`                  | Nextcloud folder path to poll (e.g. `/Scans/Inbox`). Uses the existing Nextcloud upload URL and credentials. | *(empty)* |
| `NEXTCLOUD_INGEST_DELETE_AFTER_PROCESS`    | Delete files from Nextcloud after they are downloaded and enqueued.                         | `false`     |

#### Amazon S3 Ingest (Watch Folder)

DocuElevate can poll an S3 bucket prefix for new objects. It reuses the existing S3/AWS credentials and bucket name.

| **Variable**                          | **Description**                                                                              | **Default** |
|---------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `S3_INGEST_ENABLED`                   | Enable S3 prefix watching (`true`/`false`).                                                 | `false`     |
| `S3_INGEST_PREFIX`                    | S3 key prefix to poll (e.g. `inbox/scanner/`). Uses the existing S3 bucket and AWS credentials. | *(empty)* |
| `S3_INGEST_DELETE_AFTER_PROCESS`      | Delete objects from S3 after they are downloaded and enqueued.                              | `false`     |

#### WebDAV Ingest (Watch Folder)

DocuElevate can poll a WebDAV folder for new files. It reuses the existing WebDAV URL and credentials.

| **Variable**                          | **Description**                                                                              | **Default** |
|---------------------------------------|----------------------------------------------------------------------------------------------|-------------|
| `WEBDAV_INGEST_ENABLED`               | Enable WebDAV folder watching (`true`/`false`).                                             | `false`     |
| `WEBDAV_INGEST_FOLDER`                | WebDAV folder path to poll. Uses the existing WebDAV URL and credentials.                   | *(empty)* |
| `WEBDAV_INGEST_DELETE_AFTER_PROCESS`  | Delete files from WebDAV after they are downloaded and enqueued.                            | `false`     |

#### Per-User Watch Folder Integrations

In addition to system-level watch folders, each user can configure personal watch folder sources through the **Integrations** dashboard (`/integrations`). Documents ingested from per-user watch folder integrations are automatically attributed to the owning user's `owner_id`.

Per-user watch folder integrations are stored in the `user_integrations` table with `integration_type='WATCH_FOLDER'` and `direction='SOURCE'`. The `config` JSON field stores:
- `source_type` — the type of source to scan (`local`, `s3`, `dropbox`, `google_drive`, `onedrive`, `nextcloud`, `webdav`; default: `local`)
- `folder_path` — path to the directory/folder to scan (used by local, Dropbox, OneDrive, Nextcloud, WebDAV)
- `delete_after_process` — whether to remove source files after ingestion (default: `false`)

Additional type-specific config fields:
- **S3**: `bucket`, `region`, `prefix`, `endpoint_url`
- **Google Drive**: `folder_id`
- **Nextcloud / WebDAV**: `url`, `folder_path`

> **Security**: Path traversal protection is enforced on local watch folder paths. Relative paths, `..` components, and symlink escapes are rejected. Cloud source types use per-user encrypted credentials instead.

- Individual scan failures are handled gracefully and recorded on the integration's `last_error` field without interrupting the scanning of other integrations.
- The scan runs alongside the system-level watch folder polling cycle.

### IMAP Email Ingestion

DocuElevate can automatically pull document attachments from IMAP mailboxes — no need to forward emails manually. Configure one or two system-wide mailboxes using environment variables, and/or let each user configure their own IMAP sources via the **Integrations** dashboard.

> **For HP Scanners (Scan to Email)**: If your scanner is set up to email scanned documents to a dedicated mailbox, configure that mailbox in DocuElevate using the settings below. DocuElevate will automatically retrieve the scanned PDFs from the inbox and process them. You do **not** need to configure DocuElevate as an email server — it acts as an email *client* that reads from your existing mailbox.

#### System-Level IMAP Configuration

| **Variable**                  | **Description**                                              | **Example**       |
|-------------------------------|--------------------------------------------------------------|-------------------|
| `IMAP1_HOST`                  | Hostname for first IMAP server.                             | `mail.example.com`|
| `IMAP1_PORT`                  | Port number (usually `993`).                                | `993`             |
| `IMAP1_USERNAME`              | IMAP login (first mailbox).                                 | `user@example.com`|
| `IMAP1_PASSWORD`              | IMAP password (first mailbox).                              | `*******`         |
| `IMAP1_SSL`                   | Use SSL (`true`/`false`).                                   | `true`            |
| `IMAP1_POLL_INTERVAL_MINUTES` | Frequency in minutes to poll for new mail.                  | `5`               |
| `IMAP_READONLY_MODE`          | When `true`, fetches and processes attachments but does **not** modify the mailbox (no starring, labeling, deleting, or flag changes). Use for pre-production instances sharing a mailbox with production. Default: `false`. | `false` |
| `IMAP_ATTACHMENT_FILTER`      | System-wide fallback for which attachment types are ingested when no ingestion profile is assigned to a mailbox. `documents_only` (default) ingests PDFs and office files only — images are skipped. `all` ingests every supported file type including images. Individual IMAP accounts can override this using ingestion profiles. | `documents_only` |

#### IMAP Ingestion Profiles

For fine-grained control, DocuElevate supports **Ingestion Profiles** — named configurations that let you choose exactly which file-type categories to accept from each mailbox.

Each profile contains a list of enabled **categories**:

| Category | Description |
|----------|-------------|
| `pdf` | PDF documents (`.pdf`) |
| `office` | Microsoft Office files (Word, Excel, PowerPoint — `.docx`, `.xlsx`, `.pptx`, …) |
| `opendocument` | LibreOffice/OpenOffice files (`.odt`, `.ods`, `.odp`, …) |
| `text` | Plain text, CSV and RTF files (`.txt`, `.csv`, `.rtf`) |
| `web` | HTML and Markdown files (`.html`, `.htm`, `.md`, `.markdown`) |
| `images` | Image files (`.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp`, `.svg`) |

Two built-in system profiles are seeded automatically:

| Profile | Categories |
|---------|------------|
| **Documents Only** | pdf, office, opendocument, text, web (no images) |
| **All Files** | All categories, including images |

Users can create their own custom profiles via the **Email Ingestion** dashboard (`/imap-accounts`) by clicking the **Manage profiles** link or the **+** button next to the profile dropdown. Custom profiles are private to the creating user and can be freely edited or deleted.

**API endpoints for ingestion profiles:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/imap-profiles/` | List all visible profiles (system + user's own) |
| `POST` | `/api/imap-profiles/` | Create a new profile |
| `GET` | `/api/imap-profiles/categories` | List available file-type categories |
| `GET` | `/api/imap-profiles/{id}` | Get a single profile |
| `PUT` | `/api/imap-profiles/{id}` | Update a profile (not built-in) |
| `DELETE` | `/api/imap-profiles/{id}` | Delete a profile (not built-in) |

#### Per-User IMAP Integrations

In addition to system-level mailboxes, each user can configure personal IMAP sources through the **Integrations** dashboard (`/integrations`). Documents ingested from per-user IMAP integrations are automatically attributed to the owning user's `owner_id`.

Per-user IMAP integrations are stored in the `user_integrations` table with `integration_type='IMAP'` and `direction='SOURCE'`. The `config` JSON field stores:
- `host` — IMAP server hostname (required)
- `port` — IMAP server port (default: `993`)
- `username` — IMAP login username (required)
- `use_ssl` — whether to use SSL/TLS (default: `true`)
- `delete_after_process` — whether to delete emails from the mailbox after processing (default: `false`)
- `gmail_apply_labels` — whether to apply Gmail-specific labels and stars to processed emails (default: `true`). When enabled, processed emails are starred and tagged with an "Ingested" label. Only applies to Gmail hosts.

Credentials are encrypted at rest using Fernet encryption.

- Individual connection failures are handled gracefully and recorded on the integration's `last_error` field without interrupting the polling of other integrations.
- The polling loop runs every minute and processes all active IMAP sources (system-level and per-user) in sequence.

### Authentication

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `AUTH_ENABLED`          | Enable or disable authentication (`true`/`false`).           |
| `SESSION_SECRET`        | Secret key used to encrypt sessions and cookies (at least 32 chars). |
| `SESSION_LIFETIME_DAYS` | Number of days before a server-side session expires. Default: `30`. |
| `SESSION_LIFETIME_CUSTOM_DAYS` | Override for `SESSION_LIFETIME_DAYS` when set.        |
| `QR_LOGIN_CHALLENGE_TTL_SECONDS` | How long a QR login challenge is valid (seconds). Default: `120`. |
| `ADMIN_USERNAME`        | Username for basic authentication (when not using OIDC).     |
| `ADMIN_PASSWORD`        | Password for basic authentication (when not using OIDC).     |
| `ADMIN_GROUP_NAME`      | Group name in OIDC claims that grants admin access. Default: `admin`. |
| `AUTHENTIK_CLIENT_ID`   | Client ID for Authentik OAuth2/OIDC authentication.          |
| `AUTHENTIK_CLIENT_SECRET` | Client secret for Authentik OAuth2/OIDC authentication.    |
| `AUTHENTIK_CONFIG_URL`  | Configuration URL for Authentik OpenID Connect.             |
| `OAUTH_PROVIDER_NAME`   | Display name for the OAuth provider button.                  |

### Social Login Providers

Social login lets users sign in with their existing Google, Microsoft, Apple, or Dropbox accounts. Each provider is independently enabled and configured. For detailed setup instructions see the [Social Login Setup Guide](SocialLoginSetup.md).

| **Variable** | **Description** | **Default** |
|---|---|---|
| `SOCIAL_AUTH_GOOGLE_ENABLED` | Enable Google Sign-In. | `false` |
| `SOCIAL_AUTH_GOOGLE_CLIENT_ID` | Google OAuth2 client ID from the Google Cloud Console. | *(empty)* |
| `SOCIAL_AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth2 client secret. | *(empty)* |
| `SOCIAL_AUTH_MICROSOFT_ENABLED` | Enable Microsoft Sign-In (Azure AD / Microsoft Entra ID). | `false` |
| `SOCIAL_AUTH_MICROSOFT_CLIENT_ID` | Microsoft application (client) ID from Azure App Registrations. | *(empty)* |
| `SOCIAL_AUTH_MICROSOFT_CLIENT_SECRET` | Microsoft client secret. | *(empty)* |
| `SOCIAL_AUTH_MICROSOFT_TENANT` | Azure AD tenant: `common`, `organizations`, `consumers`, or a tenant GUID. | `common` |
| `SOCIAL_AUTH_APPLE_ENABLED` | Enable Sign in with Apple. | `false` |
| `SOCIAL_AUTH_APPLE_CLIENT_ID` | Apple Services ID (e.g. `com.example.docuelevate`). | *(empty)* |
| `SOCIAL_AUTH_APPLE_TEAM_ID` | Apple Developer Team ID. | *(empty)* |
| `SOCIAL_AUTH_APPLE_KEY_ID` | Apple Sign-In private key ID. | *(empty)* |
| `SOCIAL_AUTH_APPLE_PRIVATE_KEY` | Apple Sign-In private key (PEM format). | *(empty)* |
| `SOCIAL_AUTH_DROPBOX_ENABLED` | Enable Dropbox Sign-In. | `false` |
| `SOCIAL_AUTH_DROPBOX_CLIENT_ID` | Dropbox OAuth2 App Key. | *(empty)* |
| `SOCIAL_AUTH_DROPBOX_CLIENT_SECRET` | Dropbox OAuth2 App Secret. | *(empty)* |

### Multi-User Mode

When multi-user mode is enabled, each authenticated user gets their own isolated document space.
Uploads, search results, and file management are scoped to the individual user. Shared settings
(AI configuration, OCR providers, storage destinations) remain global.

Admin users (determined by `ADMIN_GROUP_NAME`) bypass the user filter and can see all documents.

Requires `AUTH_ENABLED=true`.

| **Variable**                | **Description**                                                                 | **Default** |
|-----------------------------|---------------------------------------------------------------------------------|-------------|
| `MULTI_USER_ENABLED`        | Enable multi-user mode with individual document spaces per user.               | `false`     |
| `DEFAULT_DAILY_UPLOAD_LIMIT`| Maximum document uploads allowed per user per day. `0` = unlimited.            | `0`         |
| `UNOWNED_DOCS_VISIBLE_TO_ALL` | Show unclaimed documents (no owner) to all users. When `false`, only admins see them. | `true` |
| `DEFAULT_OWNER_ID`          | Automatically assign this owner to newly ingested documents without a session (e.g. IMAP, API). Leave empty to keep unowned. | *(empty)* |

#### Unclaimed Documents

Documents ingested via **system-level** sources (environment variable IMAP mailboxes, system watch folders)
without a user session have `owner_id = NULL` unless `DEFAULT_OWNER_ID` is set. These are called **unclaimed** documents.

Documents ingested via **per-user integrations** (IMAP or Watch Folder integrations configured through
the Integrations dashboard) are automatically attributed to the owning user's `owner_id` and are never unclaimed.

- When `UNOWNED_DOCS_VISIBLE_TO_ALL=true` (default), every authenticated user sees unclaimed
  documents alongside their own files. This allows users to discover and claim them.
- When `UNOWNED_DOCS_VISIBLE_TO_ALL=false`, only admins can see unclaimed documents.

#### Claiming Documents

Users can claim unclaimed documents via the API:

- **`POST /api/files/{file_id}/claim`** — Claim a single unclaimed document.
- **`POST /api/files/bulk-claim`** — Claim multiple unclaimed documents at once.

Only documents with `owner_id = NULL` can be claimed. Already-owned documents cannot be claimed
by another user.

#### Admin Owner Assignment

Admins can assign ownership of documents to any user:

- **`POST /api/files/assign-owner?owner_id=<user_id>`** — Assign all unclaimed documents to
  the specified user, or pass a `file_ids` JSON body to assign specific files.

The `DEFAULT_OWNER_ID` setting can also be configured via the Settings page, which provides an
autocomplete field that searches existing users by substring.

### Subscriptions & Upload Quotas

DocuElevate supports configurable subscription plans with per-user upload quotas enforced at upload time.
Plans are managed via the **Plan Designer** at `/admin/plans`. The following global setting controls the
default overage buffer applied across all plans.

| **Variable**                     | **Description**                                                                                                                                                                                                     | **Default** |
|----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|
| `SUBSCRIPTION_OVERAGE_PERCENT`   | Soft-limit overage buffer in percent (0–200). The announced monthly quota is multiplied by `(1 + percent/100)` for actual enforcement. E.g. `20` means a 150-doc/month plan enforces at 180 docs (150 × 1.20). Set `0` to enforce exactly at the announced limit. Per-plan `overage_percent` configured in the Plan Designer overrides this global default. | `20` |

### Security Headers

DocuElevate supports HTTP security headers to improve browser-side security. **These headers are disabled by default** since most deployments use a reverse proxy (Traefik, Nginx, etc.) that already adds them. Enable only if deploying directly without a reverse proxy. See [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for detailed configuration examples.

### Application Logging

DocuElevate uses Python's standard `logging` module. Two environment variables control log verbosity:

| **Variable** | **Description** | **Default** |
|-------------|----------------|-------------|
| `LOG_LEVEL` | Root logger level. Accepts standard Python level names: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. | `INFO` |
| `DEBUG` | Enable debug mode. When `true` **and** `LOG_LEVEL` is **not** explicitly set, the effective log level is automatically lowered to `DEBUG`. | `false` |

**Precedence rules (standard behaviour):**

1. If `LOG_LEVEL` is explicitly set, it always wins — regardless of `DEBUG`.
2. If only `DEBUG=true` is set (no `LOG_LEVEL`), the effective level becomes `DEBUG`.
3. If neither is set, the default level is `INFO`.

```bash
# Typical production (default)
# LOG_LEVEL=INFO

# Quick debug mode — sets level to DEBUG automatically
DEBUG=true

# Explicit level override (DEBUG flag is ignored for level selection)
LOG_LEVEL=WARNING
```

> **Tip:** At `DEBUG` level, noisy third-party libraries (httpx, authlib, urllib3, etc.) are automatically pinned to `WARNING` so that application debug output remains readable.

#### Structured JSON Logging

Set `LOG_FORMAT=json` to emit structured JSON lines on stdout — one JSON object per log message. This is the standard format for log collectors and SIEM tools:

| **Variable** | **Description** | **Default** |
|-------------|----------------|-------------|
| `LOG_FORMAT` | Log output format: `text` (human-readable) or `json` (structured JSON lines). | `text` |

Each JSON log line contains: `timestamp` (ISO 8601), `level`, `logger`, `message`, `module`, `funcName`, `lineno`, and `exc_info` (when an exception is logged).

```bash
# Enable JSON logging for SIEM / log aggregation
LOG_FORMAT=json
```

**Example JSON output:**
```json
{"timestamp": "2025-03-16T09:18:05.192000+00:00", "level": "INFO", "logger": "app.auth", "message": "[SECURITY] OAUTH_LOGIN_SUCCESS user=alice@example.com admin=False", "module": "auth", "funcName": "oauth_callback", "lineno": 654}
```

**Compatible with:**
- **Grafana Loki** — Promtail scrapes JSON from Docker stdout
- **Splunk** — Universal Forwarder or HEC with JSON sourcetype
- **ELK / OpenSearch** — Filebeat with JSON codec
- **Datadog** — Agent auto-parses JSON logs
- **Fluentd / Vector** — JSON input plugin
- **Docker log drivers** — `--log-driver=json-file` (default) preserves structure

#### Syslog Forwarding (Application Logs)

For traditional (non-container) deployments, application logs can be forwarded directly to a syslog receiver. This is **separate** from audit-log SIEM forwarding (see below) — it sends _every_ Python log message, not just audit events.

| **Variable** | **Description** | **Default** |
|-------------|----------------|-------------|
| `LOG_SYSLOG_ENABLED` | Forward application logs to a syslog receiver in addition to stdout. | `false` |
| `LOG_SYSLOG_HOST` | Hostname or IP of the syslog receiver. | `localhost` |
| `LOG_SYSLOG_PORT` | Port of the syslog receiver. | `514` |
| `LOG_SYSLOG_PROTOCOL` | Protocol: `udp` or `tcp`. | `udp` |

```bash
# Forward all application logs to syslog
LOG_SYSLOG_ENABLED=true
LOG_SYSLOG_HOST=syslog.internal.example.com
LOG_SYSLOG_PORT=514
LOG_SYSLOG_PROTOCOL=udp

# Combine with JSON format for structured syslog messages
LOG_FORMAT=json
LOG_SYSLOG_ENABLED=true
```

> **Note:** When `LOG_FORMAT=json`, syslog messages are also sent as JSON. When `LOG_FORMAT=text`, syslog messages use the standard `name - level - message` format.

### Audit Logging

DocuElevate provides comprehensive audit logging that records significant actions (logins, document CRUD, settings changes) to an append-only database table. Every entry captures the timestamp, user, action, resource, client IP, and optional JSON details.

| **Variable**                   | **Description**                                                                                   | **Default** |
|--------------------------------|---------------------------------------------------------------------------------------------------|-------------|
| `AUDIT_LOGGING_ENABLED`       | Enable the HTTP request audit-logging middleware.                                                  | `true`      |
| `AUDIT_LOG_INCLUDE_CLIENT_IP` | Include the client IP address in audit log entries. Disable for GDPR-sensitive deployments.       | `true`      |

#### SIEM Integration

Audit events can be forwarded in real time to external SIEM systems for centralised monitoring, alerting, and long-term retention. Two transports are supported:

* **Syslog** – RFC 5424 structured-data messages over UDP or TCP. Works with rsyslog, syslog-ng, Graylog, Datadog, etc.
* **HTTP** – JSON POST payloads compatible with Splunk HEC, Logstash HTTP input, Grafana Loki push API, and any generic webhook.

| **Variable**                        | **Description**                                                                                   | **Default**   |
|-------------------------------------|---------------------------------------------------------------------------------------------------|---------------|
| `AUDIT_SIEM_ENABLED`               | Enable forwarding of audit events to an external SIEM system.                                     | `false`       |
| `AUDIT_SIEM_TRANSPORT`             | Transport: `syslog` or `http`.                                                                    | `syslog`      |
| `AUDIT_SIEM_SYSLOG_HOST`           | Hostname or IP of the syslog receiver.                                                            | `localhost`   |
| `AUDIT_SIEM_SYSLOG_PORT`           | Port of the syslog receiver.                                                                      | `514`         |
| `AUDIT_SIEM_SYSLOG_PROTOCOL`       | Protocol for syslog: `udp` or `tcp`.                                                              | `udp`         |
| `AUDIT_SIEM_HTTP_URL`              | HTTP endpoint URL for SIEM delivery (e.g. Splunk HEC, Logstash, Loki).                           | *(empty)*     |
| `AUDIT_SIEM_HTTP_TOKEN`            | Bearer / HEC token for the SIEM HTTP endpoint.                                                    | *(empty)*     |
| `AUDIT_SIEM_HTTP_CUSTOM_HEADERS`   | Comma-separated `Key:Value` extra headers for SIEM HTTP requests.                                 | *(empty)*     |

**Example – Syslog to rsyslog:**

```bash
AUDIT_SIEM_ENABLED=true
AUDIT_SIEM_TRANSPORT=syslog
AUDIT_SIEM_SYSLOG_HOST=syslog.internal.example.com
AUDIT_SIEM_SYSLOG_PORT=514
AUDIT_SIEM_SYSLOG_PROTOCOL=udp
```

**Example – Splunk HEC:**

```bash
AUDIT_SIEM_ENABLED=true
AUDIT_SIEM_TRANSPORT=http
AUDIT_SIEM_HTTP_URL=https://splunk.example.com:8088/services/collector/event
AUDIT_SIEM_HTTP_TOKEN=your-hec-token
```

**Example – Logstash HTTP input:**

```bash
AUDIT_SIEM_ENABLED=true
AUDIT_SIEM_TRANSPORT=http
AUDIT_SIEM_HTTP_URL=https://logstash.example.com:8080
AUDIT_SIEM_HTTP_TOKEN=
```

### Rate Limiting

DocuElevate implements rate limiting to protect against DoS attacks and API abuse. **Rate limiting is enabled by default** and uses Redis for distributed rate limiting across multiple workers.

#### Master Control

| **Variable**              | **Description**                                                                    | **Default** |
|---------------------------|------------------------------------------------------------------------------------|-------------|
| `RATE_LIMITING_ENABLED`   | Enable/disable rate limiting middleware. Recommended for production.               | `true`      |

#### Rate Limit Configuration

Rate limits are specified in the format `count/period`, where:
- `count` is the maximum number of requests allowed
- `period` is one of: `second`, `minute`, `hour`, `day`

| **Variable**           | **Description**                                                      | **Default**      | **Applies To**                          |
|------------------------|----------------------------------------------------------------------|------------------|-----------------------------------------|
| `RATE_LIMIT_DEFAULT`   | Default rate limit for all API endpoints                             | `100/minute`     | Most API endpoints                      |
| `RATE_LIMIT_UPLOAD`    | Rate limit for file upload endpoints (prevents resource exhaustion)  | `600/minute`     | `/api/ui-upload` and similar            |
| `RATE_LIMIT_AUTH`      | Stricter rate limit for authentication (prevents brute force)        | `10/minute`      | Login, authentication endpoints         |

**Note**: Processing endpoints (OCR, metadata extraction) use built-in queue throttling via Celery to control processing rates and prevent upstream API overloads. No additional API-level rate limit is configured for processing endpoints.

#### How Rate Limiting Works

1. **Per-User Tracking**: For authenticated requests, limits are enforced per user ID
2. **Per-IP Tracking**: For unauthenticated requests, limits are enforced per IP address
3. **429 Response**: When limit is exceeded, API returns `429 Too Many Requests` with `Retry-After` header
4. **Redis Backend**: Uses Redis for distributed rate limiting (required for multi-worker deployments)
5. **In-Memory Fallback**: Falls back to in-memory storage if Redis is unavailable (not recommended for production)

#### Configuration Example

```bash
# Enable rate limiting (recommended for production)
RATE_LIMITING_ENABLED=true

# Configure Redis for distributed rate limiting
REDIS_URL=redis://redis:6379/0

# Customize rate limits
RATE_LIMIT_DEFAULT=100/minute     # 100 requests per minute per user/IP
RATE_LIMIT_UPLOAD=600/minute      # 600 uploads per minute
RATE_LIMIT_AUTH=10/minute         # 10 auth attempts per minute (brute force protection)
```

#### Recommended Limits by Deployment Size

**Small Deployment (1-10 users)**:
```bash
RATE_LIMIT_DEFAULT=200/minute
RATE_LIMIT_UPLOAD=1200/minute
RATE_LIMIT_AUTH=20/minute
```

**Medium Deployment (10-100 users)**:
```bash
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_UPLOAD=600/minute
RATE_LIMIT_AUTH=10/minute
```

**Large Deployment (100+ users)**:
```bash
RATE_LIMIT_DEFAULT=50/minute
RATE_LIMIT_UPLOAD=300/minute
RATE_LIMIT_AUTH=5/minute
```

#### Disabling Rate Limiting (Development Only)

For development or testing, you can disable rate limiting:

```bash
RATE_LIMITING_ENABLED=false
```

**Warning**: Do not disable rate limiting in production environments.

#### Monitoring Rate Limits

When rate limits are exceeded, check application logs for details:

```
2024-02-10 16:00:00 - Rate limiting by user: testuser
2024-02-10 16:00:01 - Rate limit exceeded: 100 per 1 minute
```

For more information on handling rate-limited responses in API clients, see [API Documentation - Rate Limiting](API.md#rate-limiting).

---

## Security Headers Configuration

DocuElevate supports HTTP security headers to improve browser-side security. **These headers are disabled by default** since most deployments use a reverse proxy (Traefik, Nginx, etc.) that already adds them. Enable only if deploying directly without a reverse proxy. See [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for detailed configuration examples.

#### Master Control

| **Variable**                | **Description**                                                         | **Default** |
|-----------------------------|-------------------------------------------------------------------------|-------------|
| `SECURITY_HEADERS_ENABLED`  | Enable/disable security headers middleware. Set to `true` if deploying without reverse proxy. | `false` |

#### Strict-Transport-Security (HSTS)

Forces browsers to use HTTPS for all future requests to this domain. **Only effective over HTTPS.**

| **Variable**                   | **Description**                                              | **Default**                              |
|--------------------------------|--------------------------------------------------------------|------------------------------------------|
| `SECURITY_HEADER_HSTS_ENABLED` | Enable HSTS header.                                          | `true`                                   |
| `SECURITY_HEADER_HSTS_VALUE`   | HSTS header value (max-age in seconds, subdomain support).  | `max-age=31536000; includeSubDomains`   |

**Common Values:**
- `max-age=31536000; includeSubDomains` (1 year, recommended for production)
- `max-age=300` (5 minutes, for testing)
- `max-age=63072000; includeSubDomains; preload` (2 years with HSTS preload)

#### Content-Security-Policy (CSP)

Controls which resources browsers are allowed to load. Helps prevent XSS attacks and code injection.

| **Variable**                  | **Description**                                              | **Default**                              |
|-------------------------------|--------------------------------------------------------------|------------------------------------------|
| `SECURITY_HEADER_CSP_ENABLED` | Enable CSP header.                                           | `true`                                   |
| `SECURITY_HEADER_CSP_VALUE`   | CSP policy directives.                                       | See below                                |

**Default Policy:**
```
default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;
```

**Common Customizations:**
```bash
# Stricter CSP (remove 'unsafe-inline', use nonces)
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self'; style-src 'self';"

# Allow specific external domains
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' https://cdn.example.com; style-src 'self' 'unsafe-inline';"
```

**Note:** The default policy includes `'unsafe-inline'` for compatibility with Tailwind CSS and inline JavaScript. For stricter security, use nonces or hashes.

#### X-Frame-Options

Prevents the page from being loaded in frames/iframes. Protects against clickjacking attacks.

| **Variable**                             | **Description**                          | **Default** |
|------------------------------------------|------------------------------------------|-------------|
| `SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED` | Enable X-Frame-Options header.          | `true`      |
| `SECURITY_HEADER_X_FRAME_OPTIONS_VALUE`   | X-Frame-Options header value.           | `DENY`      |

**Valid Values:**
- `DENY` - Page cannot be displayed in a frame (most secure)
- `SAMEORIGIN` - Page can only be displayed in a frame on the same origin
- ~~`ALLOW-FROM uri`~~ - **Deprecated**: Page can only be displayed in a frame on the specified origin. This directive is deprecated in modern browsers; use CSP `frame-ancestors` directive instead.

#### X-Content-Type-Options

Prevents browsers from MIME-sniffing responses away from the declared content-type. Helps prevent XSS attacks.

| **Variable**                                    | **Description**                          | **Default** |
|-------------------------------------------------|------------------------------------------|-------------|
| `SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED` | Enable X-Content-Type-Options header.   | `true`      |

**Note:** This header is always set to `nosniff` when enabled (no configuration needed).

#### Configuration Examples

**Reverse Proxy Deployment (Default - Traefik, Nginx):**
```bash
# Headers disabled by default - reverse proxy handles them
# SECURITY_HEADERS_ENABLED=false  # Can be omitted
```

**Direct Deployment (No Reverse Proxy):**
```bash
# Enable all security headers
SECURITY_HEADERS_ENABLED=true
SECURITY_HEADER_HSTS_ENABLED=true
SECURITY_HEADER_CSP_ENABLED=true
SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED=true
SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED=true
```

**Custom Configuration:**
```bash
# Enable headers but customize values
SECURITY_HEADERS_ENABLED=true
SECURITY_HEADER_HSTS_VALUE="max-age=300"  # 5 minutes for testing
SECURITY_HEADER_X_FRAME_OPTIONS_VALUE="SAMEORIGIN"  # Allow same-origin framing
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' https://trusted-cdn.com;"
```

**See Also:**
- [Deployment Guide - Security Headers](DeploymentGuide.md#security-headers) for Traefik/Nginx examples
- [SECURITY_AUDIT.md](../SECURITY_AUDIT.md#infrastructure-security) for security rationale

### AI Provider & Model Selection

DocuElevate supports multiple AI providers for metadata extraction and OCR text refinement. Select the provider via `AI_PROVIDER` and configure the matching credentials below.

| **Variable**      | **Description**                                                       | **Default**        |
|-------------------|-----------------------------------------------------------------------|--------------------|
| `AI_PROVIDER`     | Active AI provider. See supported values below.                       | `openai`           |
| `AI_MODEL`        | Model name for the selected provider. Falls back to `OPENAI_MODEL` when not set. | *(unset)* |
| `OPENAI_MODEL`    | Default model name (used when `AI_MODEL` is not set).                 | `gpt-4o-mini`      |

**Supported `AI_PROVIDER` values**: `openai`, `azure`, `anthropic`, `gemini`, `ollama`, `openrouter`, `portkey`, `litellm`

---

#### OpenAI (default)

| **Variable**          | **Description**                                  | **Default**                      |
|-----------------------|--------------------------------------------------|----------------------------------|
| `OPENAI_API_KEY`      | OpenAI API key.                                  | *(required)*                     |
| `OPENAI_BASE_URL`     | API base URL. Change for compatible proxies.     | `https://api.openai.com/v1`      |

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

#### Azure OpenAI

| **Variable**                  | **Description**                              | **Default**    |
|-------------------------------|----------------------------------------------|----------------|
| `OPENAI_API_KEY`              | Azure OpenAI API key.                        | *(required)*   |
| `OPENAI_BASE_URL`             | Azure resource endpoint URL.                 | *(required)*   |
| `AZURE_OPENAI_API_VERSION`    | Azure OpenAI API version string.             | `2024-02-01`   |

```bash
AI_PROVIDER=azure
OPENAI_API_KEY=<azure-key>
OPENAI_BASE_URL=https://my-resource.openai.azure.com
AI_MODEL=gpt-4o   # deployment name in Azure
```

#### Anthropic Claude

| **Variable**        | **Description**          |
|---------------------|--------------------------|
| `ANTHROPIC_API_KEY` | Anthropic API key.       |

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
AI_MODEL=claude-3-5-sonnet-20241022
```

#### Google Gemini

| **Variable**      | **Description**            |
|-------------------|----------------------------|
| `GEMINI_API_KEY`  | Google AI Studio API key.  |

```bash
AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...
AI_MODEL=gemini-1.5-pro
```

#### Ollama (local LLMs – CPU-friendly)

Run models locally using [Ollama](https://ollama.com). Recommended for CPU-only deployments:

| **Variable**       | **Description**                         | **Default**               |
|--------------------|-----------------------------------------|---------------------------|
| `OLLAMA_BASE_URL`  | Ollama server URL.                      | `http://localhost:11434`  |

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434   # Docker service name
AI_MODEL=llama3.2                     # or qwen2.5, phi3, etc.
```

Recommended models for document processing on CPU:

- **`llama3.2`** (3B) – good balance of speed and JSON output quality
- **`qwen2.5`** (3B/7B) – excellent at structured extraction
- **`phi3`** (3.8B) – strong reasoning, very fast on CPU

#### OpenRouter

[OpenRouter](https://openrouter.ai) provides access to 100+ models from a single endpoint using the `provider/model` name format.

| **Variable**            | **Description**                     | **Default**                       |
|-------------------------|-------------------------------------|-----------------------------------|
| `OPENROUTER_API_KEY`    | OpenRouter API key.                 | *(required)*                      |
| `OPENROUTER_BASE_URL`   | Override the gateway URL.           | `https://openrouter.ai/api/v1`    |

```bash
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=anthropic/claude-3.5-sonnet
```

#### Portkey AI Gateway

[Portkey](https://portkey.ai) is an AI gateway that adds observability, caching, fallbacks, and load balancing across 200+ models behind a single OpenAI-compatible endpoint.

| **Variable**          | **Description**                                                                                          | **Default**                      |
|-----------------------|----------------------------------------------------------------------------------------------------------|----------------------------------|
| `PORTKEY_API_KEY`     | Portkey account API key.                                                                                 | *(required)*                     |
| `PORTKEY_VIRTUAL_KEY` | Optional Virtual Key (stores provider credentials in Portkey vault, keeping them out of your env file). | *(unset)*                        |
| `PORTKEY_CONFIG`      | Optional saved Config ID (e.g. `pc-fallback-abc123`) for routing rules, fallbacks, and load balancing. | *(unset)*                        |
| `PORTKEY_BASE_URL`    | Override the Portkey gateway URL (for self-hosted deployments).                                         | `https://api.portkey.ai/v1`      |

```bash
AI_PROVIDER=portkey
PORTKEY_API_KEY=pk-...
PORTKEY_VIRTUAL_KEY=vk-openai-abc123   # optional – routes to your OpenAI key stored in Portkey
AI_MODEL=gpt-4o
```

Using a Config for fallback routing:
```bash
AI_PROVIDER=portkey
PORTKEY_API_KEY=pk-...
PORTKEY_CONFIG=pc-fallback-config-xyz  # applies your saved routing rules
AI_MODEL=gpt-4o
```

#### LiteLLM (aggregator proxy)

[LiteLLM](https://litellm.ai) provides a unified `provider/model` interface for 100+ LLMs including OpenAI, Anthropic, Gemini, Cohere, Ollama, and many more.

| **Variable**       | **Description**                                 | **Default**                   |
|--------------------|-------------------------------------------------|-------------------------------|
| `OPENAI_API_KEY`   | API key forwarded to LiteLLM (provider-specific). | *(depends on model)*        |
| `OPENAI_BASE_URL`  | Optional proxy/gateway URL.                     | `https://api.openai.com/v1`   |

```bash
AI_PROVIDER=litellm
AI_MODEL=anthropic/claude-3-5-sonnet-20241022
OPENAI_API_KEY=sk-ant-...   # passed as the api_key to LiteLLM
```

---

### Document Translation

After processing, DocuElevate can automatically translate a document's extracted text into a configurable *default language* (e.g. English). This reference translation is stored alongside the original text so users always have a version in a language they understand.

Other languages are translated **on the fly** via the AI provider and are not persisted.

#### Settings

| **Variable**                 | **Description**                                                                                           | **Default** |
|------------------------------|-----------------------------------------------------------------------------------------------------------|-------------|
| `DEFAULT_DOCUMENT_LANGUAGE`  | ISO 639-1 code for the default translation target (e.g. `en`, `de`, `fr`). Documents whose detected language differs are automatically translated into this language after processing. | `en`        |

Each user can override this global default in their profile (`UserProfile.default_document_language`).

#### How It Works

1. During metadata extraction the AI detects the document language (stored as `detected_language` on the file record).
2. If the detected language differs from the default target language, a background Celery task (`translate_to_default_language`) translates the extracted text.
3. The translated text is persisted in `default_language_text` and the target code in `default_language_code`.
4. The file detail view shows both the original text and the default-language version.
5. Users can also request on-the-fly translations to any language via the **Translate** dropdown.

#### API Endpoints

| **Endpoint**                                  | **Method** | **Description**                                                        |
|-----------------------------------------------|------------|------------------------------------------------------------------------|
| `/api/files/{id}/translation/default`         | GET        | Returns the persisted default-language translation (404 if unavailable)|
| `/api/files/{id}/translate?lang=xx`           | GET        | On-the-fly translation to any ISO 639-1 language code                  |
| `/files/{id}/text/default-language`           | GET        | View endpoint returning the default-language text as JSON              |

#### Example

```bash
# Get the stored English translation of a German document
curl http://localhost:8000/api/files/42/translation/default

# Translate on the fly to French
curl "http://localhost:8000/api/files/42/translate?lang=fr"
```

---

### OCR Providers

DocuElevate supports multiple OCR engines that can be used individually or in combination. Configure the list of active providers with `OCR_PROVIDERS` and tune each provider with the settings below.

#### Provider Selection

| **Variable**          | **Description**                                                                                   | **Default** |
|-----------------------|---------------------------------------------------------------------------------------------------|-------------|
| `OCR_PROVIDERS`       | Comma-separated list of OCR engines to use, e.g. `azure`, `mistral`, `azure,tesseract`.         | `azure`     |
| `OCR_MERGE_STRATEGY`  | Strategy for combining results from multiple providers: `ai_merge`, `longest`, or `primary`.     | `ai_merge`  |

**Supported `OCR_PROVIDERS` values**: `azure`, `tesseract`, `easyocr`, `mistral`, `google_docai`, `aws_textract`

When multiple providers are listed, all run in parallel and their results are merged according to `OCR_MERGE_STRATEGY`.

#### Embedded Text Quality Check

DocuElevate can automatically assess whether the text already embedded in a PDF is of sufficient quality before deciding to skip OCR. This prevents poor OCR output from a previous scan being silently used for downstream processing.

| **Variable**                              | **Description**                                                                                         | **Default**                                                                               |
|-------------------------------------------|---------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `ENABLE_TEXT_QUALITY_CHECK`               | Enable AI-based quality assessment of embedded PDF text.                                                | `true`                                                                                    |
| `TEXT_QUALITY_THRESHOLD`                  | Minimum quality score (0–100) required to accept embedded text without re-OCR.                         | `85`                                                                                      |
| `TEXT_QUALITY_SIGNIFICANT_ISSUES`         | Comma-separated issue labels that force re-OCR even when the score meets the threshold.                 | `excessive_typos,garbage_characters,incoherent_text,fragmented_sentences`                 |

**How it works:**

1. When a PDF with embedded text is received, DocuElevate first examines the PDF metadata (`/Producer`, `/Creator`).
2. If the PDF was **digitally created** (e.g., exported from Word, LibreOffice, LaTeX, or any modern authoring tool), the embedded text is considered trustworthy and the quality check is skipped — digital text cannot be improved by re-OCRing.
3. If the PDF was **previously OCR'd** (Tesseract, ABBYY, ocrmypdf, etc.) or the origin is **unknown**, an AI model evaluates a sample of the extracted text for:
   - Excessive typos and character-substitution artefacts typical of OCR
   - Garbage characters or symbol soup
   - Incoherent or nonsensical sentences
   - Heavy fragmentation
4. The text is **rejected** (and re-OCR triggered) when **either** of these conditions is true:
   - The quality score is **below** `TEXT_QUALITY_THRESHOLD` (default 85), **or**
   - The AI identifies one or more issues listed in `TEXT_QUALITY_SIGNIFICANT_ISSUES` — even if the numeric score is above the threshold. This prevents edge cases such as a score of 68 with `excessive_typos` and `garbage_characters` being silently accepted.
5. After the re-OCR pass, the fresh OCR result is compared **head-to-head** against the original embedded text using an AI side-by-side review. The higher-quality text is passed to downstream processing (metadata extraction, AI analysis). This ensures re-OCR never degrades quality.
6. All quality decisions (score, source, AI feedback, comparison outcome) are recorded in the processing log for review.

> **Tip**: Set `ENABLE_TEXT_QUALITY_CHECK=false` to disable the check entirely and always use embedded text as-is. This is useful when the AI provider is unavailable or when processing speed is more important than text accuracy.

> **Tuning the threshold**: The default of `TEXT_QUALITY_THRESHOLD=85` is intentionally strict. Lower it (e.g., `70`) for environments with consistently good existing OCR. Raise it (up to `100`) for maximum quality enforcement.

#### Searchable PDF Text Layer

Not all OCR providers embed a searchable text layer in the output PDF. The table below summarises each provider's behaviour and how DocuElevate handles it:

| **Provider**      | **Embeds text layer?** | **Notes** |
|-------------------|------------------------|-----------|
| `azure`           | ✅ Yes                 | Azure Document Intelligence returns a PDF/A with an embedded text layer. |
| `tesseract`       | ❌ No (text only)      | Text is extracted but the PDF is not modified. `embed_text_layer` post-processing is applied automatically. |
| `easyocr`         | ❌ No (text only)      | Same as above. |
| `mistral`         | ❌ No (text only)      | Mistral OCR API returns plain text; `embed_text_layer` post-processing is applied automatically. |
| `google_docai`    | ❌ No (text only)      | Google Cloud Document AI returns plain text; `embed_text_layer` post-processing is applied automatically. |
| `aws_textract`    | ❌ No (text only)      | AWS Textract returns plain text; `embed_text_layer` post-processing is applied automatically. |

For providers that do **not** embed a text layer, DocuElevate automatically runs `ocrmypdf --skip-text` after OCR to add an invisible Tesseract-generated text layer to the PDF. This makes the file selectable and searchable in PDF viewers. The step is silently skipped if `ocrmypdf` is not available on `PATH` (a warning is logged).

#### Azure Document Intelligence

| **Variable**                              | **Description**                                          | **How to Obtain**                       |
|-------------------------------------------|----------------------------------------------------------|-----------------------------------------|
| `AZURE_DOCUMENT_INTELLIGENCE_KEY`         | Azure Document Intelligence API key for OCR.            | [Azure Portal](https://portal.azure.com/) |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`   | Endpoint URL for Azure Document Intelligence API.        | [Azure Portal](https://portal.azure.com/) |

#### Tesseract (self-hosted)

Requires `tesseract-ocr` to be installed in the Docker image or on the host. The default Docker image ships with Tesseract (English language data only).

**Automatic language data download**: DocuElevate automatically downloads missing Tesseract `.traineddata` files at startup using `wget` from the [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) repository. No manual installation is required — simply set `TESSERACT_LANGUAGE` to the desired language codes and the data files are fetched on first start. The container must have outbound internet access for this to work.

| **Variable**           | **Description**                                                                   | **Default** |
|------------------------|-----------------------------------------------------------------------------------|-------------|
| `TESSERACT_CMD`        | Path to the `tesseract` binary (optional; auto-detected from `PATH`).            | *(auto)*    |
| `TESSERACT_LANGUAGE`   | Tesseract language code(s), e.g. `eng`, `eng+deu`, `deu`.                       | `eng+deu`   |

```bash
OCR_PROVIDERS=tesseract
TESSERACT_LANGUAGE=eng+deu
```

> **Language codes**: Use ISO 639-2 codes separated by `+`, e.g. `eng+deu+fra` for English + German + French.
> All codes supported by Tesseract are available. See the [tessdata repository](https://github.com/tesseract-ocr/tessdata_fast) for the full list.

> **No internet access?** Set `TESSDATA_PREFIX` to a writable directory and pre-populate it with the required `.traineddata` files. Alternatively, build a custom Docker image that installs the needed language packages via `apt-get install tesseract-ocr-<lang>`.

#### EasyOCR (self-hosted)

Requires the `easyocr` Python package. Install it separately as it is not included in the base requirements.

**Automatic model download**: EasyOCR model files are downloaded automatically on first use (or at startup) to `~/.EasyOCR/model/`. The container must have outbound internet access. Model download can take several minutes depending on the language.

| **Variable**          | **Description**                                                        | **Default** |
|-----------------------|------------------------------------------------------------------------|-------------|
| `EASYOCR_LANGUAGES`   | Comma-separated EasyOCR language codes, e.g. `en,de,fr`.              | `en,de`     |
| `EASYOCR_GPU`         | Enable GPU acceleration for EasyOCR (`true`/`false`).                 | `false`     |

#### Mistral OCR

| **Variable**           | **Description**                                | **How to Obtain**                              |
|------------------------|------------------------------------------------|------------------------------------------------|
| `MISTRAL_API_KEY`      | Mistral API key.                               | [console.mistral.ai](https://console.mistral.ai) |
| `MISTRAL_OCR_MODEL`    | Mistral OCR model name.                        | `mistral-ocr-latest`                           |

#### Google Cloud Document AI

| **Variable**                     | **Description**                                                                       | **Default** |
|----------------------------------|---------------------------------------------------------------------------------------|-------------|
| `GOOGLE_DOCAI_PROJECT_ID`        | GCP project ID (required).                                                           | *(required)* |
| `GOOGLE_DOCAI_PROCESSOR_ID`      | Document AI processor ID (required).                                                 | *(required)* |
| `GOOGLE_DOCAI_LOCATION`          | Processor location, e.g. `us` or `eu`.                                              | `us`         |
| `GOOGLE_DOCAI_CREDENTIALS_JSON`  | Service account JSON (optional; falls back to `GOOGLE_DRIVE_CREDENTIALS_JSON`).      | *(optional)* |

#### AWS Textract

Reuses the AWS credentials already configured for S3 integration.

| **Variable**              | **Description**                      |
|---------------------------|--------------------------------------|
| `AWS_ACCESS_KEY_ID`       | AWS access key ID.                   |
| `AWS_SECRET_ACCESS_KEY`   | AWS secret access key.               |
| `AWS_REGION`              | AWS region, e.g. `us-east-1`.       |

#### Multi-Provider Example

```bash
# Use both Azure (for accuracy) and Tesseract (for redundancy); merge via AI
OCR_PROVIDERS=azure,tesseract
OCR_MERGE_STRATEGY=ai_merge
AZURE_AI_KEY=...
AZURE_ENDPOINT=https://...
TESSERACT_LANGUAGE=eng+deu
```

### Azure Document Intelligence (Legacy)

> **Note:** This section documents the standalone Azure Document Intelligence credentials. When using `OCR_PROVIDERS=azure` these same credentials are used automatically.

| **Variable**                     | **Description**                          | **How to Obtain**                                                        |
|---------------------------------|------------------------------------------|--------------------------------------------------------------------------|
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Azure Document Intelligence API key for OCR. | [Azure Portal](https://portal.azure.com/) |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Endpoint URL for Azure Doc Intelligence API. | [Azure Portal](https://portal.azure.com/) |

### Paperless NGX

| **Variable**                        | **Description**                                                                                     |
|-------------------------------------|-----------------------------------------------------------------------------------------------------|
| `PAPERLESS_ENABLED`                 | Set to `false` to disable Paperless-ngx uploads without removing credentials. Default: `true`       |
| `PAPERLESS_NGX_API_TOKEN`           | API token for Paperless NGX.                                                                        |
| `PAPERLESS_HOST`                    | Root URL for Paperless NGX (e.g. `https://paperless.example.com`).                                 |
| `PAPERLESS_CUSTOM_FIELD_ABSENDER`   | (Optional, Legacy) Name of the custom field in Paperless-ngx to store the sender ("absender") information. If set, the extracted sender will be automatically set as a custom field after document upload. Example: `Absender` or `Sender` |
| `PAPERLESS_CUSTOM_FIELDS_MAPPING`   | (Optional, Recommended) JSON mapping of extracted metadata fields to Paperless custom field names. This allows you to map multiple fields at once. Format: `{"metadata_field": "CustomFieldName", ...}`. See examples below. |

#### Custom Fields Mapping Examples

**Single Field (Legacy Method)**:
```bash
PAPERLESS_CUSTOM_FIELD_ABSENDER=Absender
```

**Multiple Fields (Recommended Method)**:
```bash
# Map multiple metadata fields to custom fields in Paperless
PAPERLESS_CUSTOM_FIELDS_MAPPING='{"absender": "Sender", "empfaenger": "Recipient", "language": "Language"}'
```

**All Available Metadata Fields**:
DocuElevate extracts the following fields that can be mapped to Paperless custom fields:
- `absender` - Sender/author of the document
- `empfaenger` - Recipient of the document
- `correspondent` - The issuing entity/company (shortened name)
- `document_type` - Type classification (Invoice, Contract, etc.)
- `language` - Document language (ISO 639-1 code, e.g., "de", "en")
- `kommunikationsart` - Communication type (German classification)
- `kommunikationskategorie` - Communication category (German classification)
- `reference_number` - Invoice/order/reference number if found
- `title` - Human-readable document title
- `tags` - List of thematic keywords (array)

**Complete Example**:
```bash
PAPERLESS_CUSTOM_FIELDS_MAPPING='{"absender": "Sender", "empfaenger": "Recipient", "correspondent": "Correspondent", "language": "Language", "reference_number": "ReferenceNumber"}'
```

**Note**: Custom fields must be created in your Paperless-ngx instance before DocuElevate can use them. The field names in the mapping (right side of the JSON) must **exactly** match the names in Paperless (case-sensitive).

### Dropbox

| **Variable**            | **Description**                                  |
|-------------------------|--------------------------------------------------|
| `DROPBOX_ENABLED`       | Set to `false` to disable Dropbox uploads without removing credentials. Default: `true` |
| `DROPBOX_APP_KEY`       | Dropbox API app key.                             |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret.                          |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox.                |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads.         |

For detailed setup instructions, see the [Dropbox Setup Guide](DropboxSetup.md).

### Nextcloud

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `NEXTCLOUD_ENABLED`     | Set to `false` to disable Nextcloud uploads without removing credentials. Default: `true` |
| `NEXTCLOUD_UPLOAD_URL`  | Nextcloud WebDAV URL (e.g. `https://nc.example.com/remote.php/dav/files/<USERNAME>`). |
| `NEXTCLOUD_USERNAME`    | Nextcloud login username.                                    |
| `NEXTCLOUD_PASSWORD`    | Nextcloud login password.                                    |
| `NEXTCLOUD_FOLDER`      | Destination folder in Nextcloud (e.g. `"/Documents/Uploads"`). |

### Google Drive

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `GOOGLE_DRIVE_ENABLED`          | Set to `false` to disable Google Drive uploads without removing credentials. Default: `true` |
| `GOOGLE_DRIVE_USE_OAUTH`        | Set to `true` to use OAuth flow (recommended)         |
| `GOOGLE_DRIVE_CLIENT_ID`        | OAuth Client ID (required if using OAuth flow)        |
| `GOOGLE_DRIVE_CLIENT_SECRET`    | OAuth Client Secret (required if using OAuth flow)    |
| `GOOGLE_DRIVE_REFRESH_TOKEN`    | OAuth Refresh Token (required if using OAuth flow)    |
| `GOOGLE_DRIVE_FOLDER_ID`        | Google Drive folder ID for file uploads               |
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | JSON string containing service account credentials (alternative method) |
| `GOOGLE_DRIVE_DELEGATE_TO`      | Email address to delegate permissions (optional for service accounts) |

**Note:** For OAuth method with non-verified apps, refresh tokens expire after 7 days. For production use, either complete the Google verification process or use the Service Account method.

For detailed setup instructions, see the [Google Drive Setup Guide](GoogleDriveSetup.md).

### WebDAV

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `WEBDAV_ENABLED`        | Set to `false` to disable WebDAV uploads without removing credentials. Default: `true` |
| `WEBDAV_URL`            | WebDAV server URL (e.g. `https://webdav.example.com/path`).   |
| `WEBDAV_USERNAME`       | WebDAV authentication username.                               |
| `WEBDAV_PASSWORD`       | WebDAV authentication password.                               |
| `WEBDAV_FOLDER`         | Destination folder on WebDAV server (e.g. `"/Documents/Uploads"`). |
| `WEBDAV_VERIFY_SSL`     | Whether to verify SSL certificates (default: `True`).         |

### FTP

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `FTP_ENABLED`           | Set to `false` to disable FTP uploads without removing credentials. Default: `true` |
| `FTP_HOST`              | FTP server hostname or IP address.                            |
| `FTP_PORT`              | FTP port (default: `21`).                                     |
| `FTP_USERNAME`          | FTP authentication username.                                  |
| `FTP_PASSWORD`          | FTP authentication password.                                  |
| `FTP_FOLDER`            | Destination folder on FTP server (e.g. `"/Documents/Uploads"`). |
| `FTP_USE_TLS`           | Try to use FTPS with TLS encryption first (default: `True`).  |
| `FTP_ALLOW_PLAINTEXT`   | Allow fallback to plaintext FTP if TLS fails (default: `True`). |

### SFTP

| **Variable**                  | **Description**                                         |
|------------------------------|-------------------------------------------------------|
| `SFTP_ENABLED`               | Set to `false` to disable SFTP uploads without removing credentials. Default: `true` |
| `SFTP_HOST`                  | SFTP server hostname or IP address.                    |
| `SFTP_PORT`                  | SFTP port (default: `22`).                             |
| `SFTP_USERNAME`              | SFTP authentication username.                          |
| `SFTP_PASSWORD`              | SFTP authentication password (if not using private key). |
| `SFTP_FOLDER`                | Destination folder on SFTP server.                     |
| `SFTP_PRIVATE_KEY`           | Path to private key file for authentication (optional). |
| `SFTP_PRIVATE_KEY_PASSPHRASE`| Passphrase for private key if required (optional).     |

### Email (shared SMTP – password reset & verification)

> **Note:** These settings configure the shared SMTP connection used for system emails such as
> password resets and account verification. They do **not** enable the email delivery destination.
> To send processed documents via email, configure the dedicated `DEST_EMAIL_*` variables below.

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `EMAIL_HOST`               | SMTP server hostname.                                     |
| `EMAIL_PORT`               | SMTP port (default: `587`).                               |
| `EMAIL_USERNAME`           | SMTP authentication username.                             |
| `EMAIL_PASSWORD`           | SMTP authentication password.                             |
| `EMAIL_USE_TLS`            | Whether to use TLS (default: `True`).                     |
| `EMAIL_SENDER`             | From address (e.g., `"DocuElevate <docuelevate@example.com>"`). |

### Email Destination (document delivery)

> **Note:** These settings are intentionally separate from the shared `EMAIL_*` settings above.
> Configuring `EMAIL_HOST` for password resets does **not** automatically activate the email
> delivery destination. You must set `DEST_EMAIL_HOST` to enable it.

| **Variable**                     | **Description**                                                     |
|----------------------------------|---------------------------------------------------------------------|
| `DEST_EMAIL_ENABLED`            | Set to `false` to disable email delivery without removing credentials. Default: `true` |
| `DEST_EMAIL_HOST`               | SMTP server hostname for document delivery.                          |
| `DEST_EMAIL_PORT`               | SMTP port for document delivery (default: `587`).                    |
| `DEST_EMAIL_USERNAME`           | SMTP authentication username for document delivery.                  |
| `DEST_EMAIL_PASSWORD`           | SMTP authentication password for document delivery.                  |
| `DEST_EMAIL_USE_TLS`            | Whether to use TLS for document delivery (default: `True`).          |
| `DEST_EMAIL_SENDER`             | From address for delivered documents (e.g., `"DocuElevate Delivery <docuelevate@example.com>"`). |
| `DEST_EMAIL_DEFAULT_RECIPIENT`  | Fallback recipient email when none is specified for a delivery task.  |

### OneDrive / Microsoft Graph

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `ONEDRIVE_ENABLED`              | Set to `false` to disable OneDrive uploads without removing credentials. Default: `true` |
| `ONEDRIVE_CLIENT_ID`            | Azure AD application client ID                        |
| `ONEDRIVE_CLIENT_SECRET`        | Azure AD application client secret                    |
| `ONEDRIVE_TENANT_ID`            | Azure AD tenant ID: use "common" for personal accounts or your tenant ID for corporate accounts |
| `ONEDRIVE_REFRESH_TOKEN`        | OAuth 2.0 refresh token (required for personal accounts) |
| `ONEDRIVE_FOLDER_PATH`          | Folder path in OneDrive for storing documents         |

For detailed setup instructions, see the [OneDrive Setup Guide](OneDriveSetup.md).

### Amazon S3

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `S3_ENABLED`                    | Set to `false` to disable S3 uploads without removing credentials. Default: `true` |
| `AWS_ACCESS_KEY_ID`             | AWS IAM access key ID                                 |
| `AWS_SECRET_ACCESS_KEY`         | AWS IAM secret access key                             |
| `AWS_REGION`                    | AWS region where your S3 bucket is located (default: `us-east-1`) |
| `S3_BUCKET_NAME`                | Name of your S3 bucket                                |
| `S3_FOLDER_PREFIX`              | Optional prefix/folder path for uploaded files        |
| `S3_STORAGE_CLASS`              | Storage class for uploaded objects (default: `STANDARD`) |
| `S3_ACL`                        | Access control for uploaded files (default: `private`) |

For detailed setup instructions, see the [Amazon S3 Setup Guide](AmazonS3Setup.md).

### iCloud Drive (Apple)

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `ICLOUD_ENABLED`                | Set to `false` to disable iCloud uploads without removing credentials. Default: `true` |
| `ICLOUD_USERNAME`               | Apple ID email address                                |
| `ICLOUD_PASSWORD`               | App-specific password (generate at [appleid.apple.com](https://appleid.apple.com/account/manage)) |
| `ICLOUD_FOLDER`                 | Target folder path in iCloud Drive (e.g. `Documents/Uploads`) |
| `ICLOUD_COOKIE_DIRECTORY`       | Optional directory for session cookie persistence (default: `~/.pyicloud`) |

> **Note:** Apple does not provide a public REST API for iCloud Drive. This
> integration uses the [pyicloud](https://github.com/picklepete/pyicloud)
> library which relies on an unofficial, reverse-engineered protocol. Because
> most Apple IDs have two-factor authentication enabled, you **must** generate
> an [app-specific password](https://support.apple.com/en-us/102654) and use
> it as `ICLOUD_PASSWORD`.

### Notification System

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `NOTIFICATION_URLS`        | Comma-separated list of Apprise notification URLs         |
| `NOTIFY_ON_TASK_FAILURE`   | Send notifications on task failures (`True`/`False`)     |
| `NOTIFY_ON_CREDENTIAL_FAILURE` | Send notifications on credential failures (`True`/`False`) |
| `NOTIFY_ON_STARTUP`        | Send notification when system starts (`True`/`False`)    |
| `NOTIFY_ON_SHUTDOWN`       | Send notification when system shuts down (`True`/`False`)|
| `NOTIFY_ON_FILE_PROCESSED` | Send notification when a file is successfully processed (`True`/`False`) |
| `NOTIFY_ON_USER_SIGNUP`    | Send admin notification when a new user signs up (`True`/`False`, default `True`) |
| `NOTIFY_ON_PLAN_CHANGE`    | Send admin notification when a user changes their subscription plan (`True`/`False`, default `True`) |
| `NOTIFY_ON_PAYMENT_ISSUE`  | Send admin notification when a payment issue is reported for a user (`True`/`False`, default `True`) |

#### User-Event Notifications

DocuElevate sends admin push notifications (via Apprise) and fires outbound webhooks for three
user-lifecycle events:

| Event | Trigger | Notification type |
|-------|---------|-------------------|
| **New signup** | A first-time user logs in and a UserProfile is created | `NOTIFY_ON_USER_SIGNUP` |
| **Plan change** | A user selects a new subscription tier during onboarding, or an admin changes their tier | `NOTIFY_ON_PLAN_CHANGE` |
| **Payment issue** | An admin POSTs to `/api/admin/users/{user_id}/payment-issue` | `NOTIFY_ON_PAYMENT_ISSUE` |

In addition to the Apprise push notification, each event also fires the matching webhook event
(`user.signup`, `user.plan_changed`, `user.payment_issue`) to all active webhook configurations
subscribed to that event, enabling integration with CRM, helpdesk (Jira, Zendesk, etc.), or
payment processors.

For detailed setup instructions, see the [Notifications Setup Guide](NotificationsSetup.md).

#### Per-User Notification System

In addition to the system-level Apprise notifications, DocuElevate includes a **per-user notification system** that gives each user full control over how they are notified about their own document events.

**Notification Dashboard** — available at `/notifications` for every logged-in user. It has three tabs:

| Tab | Description |
|-----|-------------|
| **Inbox** | In-app bell-icon notification feed. Persisted in the database; shows unread count badge in the navigation bar. Users can mark individual items or all items as read. |
| **Targets** | User-defined notification channels: **Email (SMTP)** and **Webhook (HTTP POST)**. Each target can be tested independently from the UI. |
| **Preferences** | Event/channel matrix. Users choose which channels are triggered for each event type. In-app notifications are always enabled. |

**User-centric event types:**

| Event | Description |
|-------|-------------|
| `document.processed` | A document uploaded by the user was successfully processed and uploaded to destinations |
| `document.failed` | A document uploaded by the user failed during processing |

**Email target configuration fields:**

| Field | Description |
|-------|-------------|
| `smtp_host` | SMTP server hostname |
| `smtp_port` | SMTP port (default `587`) |
| `smtp_username` | SMTP login username |
| `smtp_password` | SMTP login password (stored in database, masked in UI) |
| `smtp_use_tls` | Enable STARTTLS (`true`/`false`, default `true`) |
| `sender_email` | From address (defaults to `smtp_username` if omitted) |
| `recipient_email` | Destination address for this target |

**Webhook target configuration fields:**

| Field | Description |
|-------|-------------|
| `url` | HTTP(S) URL to POST the notification payload to |
| `secret` | Optional secret string sent as `X-DocuElevate-Secret` header |

**Webhook payload format:**
```json
{
  "event": "document.processed",
  "title": "Document processed: invoice.pdf",
  "message": "Your document 'invoice.pdf' has been successfully processed and uploaded."
}
```

> **Note:** There are no additional environment variables for the per-user notification system — all settings are stored in the database and managed through the user-facing `/notifications` dashboard.

### Webhooks

Webhooks notify external systems via HTTP POST when document events occur.
Configurations are stored in the database and managed through the API (see [API docs](API.md#webhooks)).

| **Variable**        | **Description**                                                  | **Default** |
|---------------------|------------------------------------------------------------------|-------------|
| `WEBHOOK_ENABLED`   | Enable or disable webhook delivery globally (`True`/`False`)    | `True`      |

Webhook URLs, secrets, and subscribed events are configured per-webhook via the `/api/webhooks/` endpoints (admin access required). Each delivery includes an optional HMAC-SHA256 signature for verification and is retried with exponential backoff on failure.

### Backup & Restore

DocuElevate automatically backs up the database on a scheduled basis.
Backups are managed from the **Admin → Backup & Restore** dashboard.

Supported database backends: **SQLite** (`.db.gz`), **PostgreSQL** (`.pgsql.gz`), **MySQL / MariaDB** (`.mysql.gz`).
For PostgreSQL and MySQL backups the respective CLI client (`pg_dump` / `psql` or `mysqldump` / `mysql`) must be installed on the Celery worker host.
See the [Database Configuration Guide](DatabaseConfiguration.md#backup-procedures) for setup details.

| **Variable**                   | **Description**                                                                               | **Default**         |
|--------------------------------|-----------------------------------------------------------------------------------------------|---------------------|
| `BACKUP_ENABLED`               | Enable or disable automatic scheduled backups (`True`/`False`).                              | `True`              |
| `BACKUP_DIR`                   | Filesystem path where local backup archives are stored. Defaults to `<WORKDIR>/backups`.     | *(workdir/backups)* |
| `BACKUP_REMOTE_DESTINATION`    | Storage provider to copy backups to. Options: `s3`, `dropbox`, `google_drive`, `onedrive`, `nextcloud`, `webdav`, `ftp`, `sftp`, `email`. Leave empty for local-only storage. | *(empty)*           |
| `BACKUP_REMOTE_FOLDER`         | Sub-folder / key prefix used when uploading to the remote destination.                       | `backups`           |
| `BACKUP_RETAIN_HOURLY`         | Number of hourly snapshots to keep (1 per hour = 96 covers 4 days).                         | `96`                |
| `BACKUP_RETAIN_DAILY`          | Number of daily snapshots to keep (21 = 3 weeks).                                           | `21`                |
| `BACKUP_RETAIN_WEEKLY`         | Number of weekly snapshots to keep (13 ≈ 3 months).                                         | `13`                |

**Retention schedule:**

| Tier    | Frequency        | Default retention | Coverage     |
|---------|------------------|-------------------|--------------|
| Hourly  | Every hour       | 96 snapshots      | ~4 days      |
| Daily   | Daily at 02:00   | 21 snapshots      | ~3 weeks     |
| Weekly  | Sundays at 03:00 | 13 snapshots      | ~3 months    |

Archives beyond the retention window are automatically pruned after each new backup. The **Clean Up** button on the dashboard applies retention immediately. When a remote destination is configured, remote copies follow the same retention policy.

> **Note:** Backup and restore is currently supported only for SQLite databases.

### Uptime Kuma

| **Variable**                | **Description**                                                |
|-----------------------------|----------------------------------------------------------------|
| `UPTIME_KUMA_URL`           | Uptime Kuma push URL for monitoring the application's health.   |
| `UPTIME_KUMA_PING_INTERVAL` | How often to ping Uptime Kuma in minutes (default: `5`).       |

### UI / Appearance

DocuElevate supports a **dark mode** toggle in the navbar. Users can switch between light and dark themes at any time; their choice is stored in `localStorage` and persists across page reloads in the same browser.

Administrators can set the **site-wide default** colour scheme that is applied when a user has not yet made a personal choice:

| **Variable**               | **Description**                                                                                                                                  | **Default** |
|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|-------------|
| `UI_DEFAULT_COLOR_SCHEME`  | Default colour scheme for all users. Options: `system` (follow OS preference), `light`, `dark`. Users can always override with the navbar toggle. | `system`    |

**How it works:**

1. On page load an inline script checks the user's `localStorage` preference first.
2. If no stored preference exists, the server-supplied `UI_DEFAULT_COLOR_SCHEME` is used.
3. When the value is `system` (the default), the OS-level `prefers-color-scheme` media query is respected.
4. Clicking the 🌙 / ☀️ toggle in the navbar saves the new preference to `localStorage` immediately.

**WCAG AA compliance:** All dark-mode colour pairs have been chosen with a minimum 4.5:1 contrast ratio for normal text and 3:1 for large text.

**Example:**

```dotenv
# Force dark mode for all users by default
UI_DEFAULT_COLOR_SCHEME=dark
```

### Support / Help Center – Zammad Integration

The Help Center page (`/help`) can optionally integrate with a [Zammad](https://zammad.com/) instance to offer live chat and a ticket-creation form directly within DocuElevate.

| **Variable**            | **Description**                                                                                       | **Default** |
|-------------------------|-------------------------------------------------------------------------------------------------------|-------------|
| `ZAMMAD_URL`            | Base URL of your Zammad instance (e.g. `https://zammad.example.com`). Required for chat and form.     | *(unset)*   |
| `ZAMMAD_CHAT_ENABLED`   | Show a Zammad live-chat widget on the Help Center page.                                               | `false`     |
| `ZAMMAD_CHAT_ID`        | Zammad chat topic ID (see *Channels → Chat → Topics* in Zammad admin).                               | `1`         |
| `ZAMMAD_FORM_ENABLED`   | Show a "Submit a Ticket" feedback form on the Help Center page.                                       | `false`     |
| `SUPPORT_EMAIL`         | Support e-mail address displayed on the Help Center page.                                             | *(unset)*   |

**Example:**

```dotenv
ZAMMAD_URL=https://zammad.example.com
ZAMMAD_CHAT_ENABLED=true
ZAMMAD_CHAT_ID=1
ZAMMAD_FORM_ENABLED=true
SUPPORT_EMAIL=support@example.com
```

> **Note:** The live-chat widget requires at least one Zammad agent to be online. If no agent is available, the widget will not appear. Enable Zammad's debug mode (`debug: true`) for troubleshooting.

#### Automatic User Context (Auto-Fill)

When a user is logged in, DocuElevate automatically passes their identity to the Zammad widgets:

- **Ticket form:** The user's **name** and **email** are pre-filled in the form fields. A *DocuElevate User Context* block containing the user's name, email, and username is appended to the ticket body so the support agent can immediately identify the requester.
- **Live chat:** The user's **name** and **email** are passed to the Zammad chat widget constructor. Depending on your Zammad version, the agent may see this information in the chat session details.

No additional configuration is required — the auto-fill uses the authenticated session data (OAuth, local login, or admin credentials). Anonymous visitors see the standard Zammad widgets without pre-filled data.

## Observability – Sentry

DocuElevate integrates with [Sentry](https://sentry.io) for real-time error tracking and performance monitoring.  See [SentrySetup.md](./SentrySetup.md) for a full setup guide.

| Variable | Description | Default |
|---|---|---|
| `SENTRY_DSN` | Sentry DSN URL.  When set, error reporting and performance tracing are enabled automatically.  Leave blank to disable. | *(unset)* |
| `SENTRY_ENVIRONMENT` | Environment label attached to every Sentry event (`development`, `staging`, `production`, …). | `production` |
| `SENTRY_TRACES_SAMPLE_RATE` | Fraction of requests captured for performance tracing (0.0 – 1.0).  `0.0` disables tracing entirely. | `0.1` |
| `SENTRY_PROFILES_SAMPLE_RATE` | Fraction of profiled transactions sent to Sentry (0.0 – 1.0).  Only active when traces > 0. | `0.0` |
| `SENTRY_SEND_DEFAULT_PII` | Attach PII (IP addresses, user agents) to Sentry events.  Disabled by default for GDPR/CCPA compliance. | `false` |

```bash
# Minimal example
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=production

# Optional tuning
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_DEFAULT_PII=false
```

> **Note:** Sentry is completely opt-in — if `SENTRY_DSN` is not set, the SDK is never initialised and no data leaves your infrastructure.

## Duplicate Document Detection

DocuElevate detects and flags documents that share the same content, even if they arrive as separate uploads.

### Exact Duplicate Detection (SHA-256)

When `ENABLE_DEDUPLICATION=True` (the default), each new document is hashed with SHA-256 before processing begins. If the hash matches an existing file record the new document is stored as a duplicate (`is_duplicate=True`, `duplicate_of_id=<original_id>`) and no further processing is performed.

| Variable | Description | Default |
|---|---|---|
| `ENABLE_DEDUPLICATION` | Hash-based exact duplicate detection on ingest. | `True` |
| `SHOW_DEDUPLICATION_STEP` | Show the "Check for Duplicates" step in the processing timeline UI. | `True` |

An immediate duplicate warning is also included in the `/api/ui-upload` JSON response so the frontend can alert the user before the pipeline completes.

### Near-Duplicate Detection (Content Similarity)

Near-duplicate detection catches documents that contain the **same content but carry different SHA-256 hashes** — for example, the same letter scanned twice on different days.

After OCR processes a document, its extracted text is converted to a vector embedding using the configured AI provider. The cosine similarity between two documents' embeddings reflects how semantically similar their content is.

| Variable | Description | Default |
|---|---|---|
| `NEAR_DUPLICATE_THRESHOLD` | Minimum cosine similarity (0–1) for two documents to be considered near-duplicates. `0.85` means ≥ 85 % semantic overlap. | `0.85` |
| `EMBEDDING_MODEL` | Model name for generating text embeddings via the OpenAI-compatible API.  Must be supported by the endpoint configured with `OPENAI_BASE_URL`. | `text-embedding-3-small` |
| `EMBEDDING_MAX_TOKENS` | Maximum tokens to send to the embedding model.  Text is truncated to approximately this many tokens before calling the API.  Set below the model's context window (e.g. 8 000 for an 8 192-token model). | `8000` |

Near-duplicate detection:
- Embeddings are computed **automatically during document ingestion** as a processing step ("Compute Embedding").
- A periodic **backfill task** (every 5 minutes) picks up any files that were processed before the embedding pipeline was enabled.
- The **Similarity dashboard** (`/similarity`) shows all pairs of documents above the threshold, ranked by score.
- The **Duplicates** management page (`/duplicates` → "Near-Duplicate Finder" tab) allows per-file lookup.
- Debug endpoints are available to inspect embedding status and trigger recomputation (see API docs).
- Documents without OCR text cannot be compared and are excluded from results.

A score of **≥ 0.90** reliably identifies the same document scanned twice. A score of **0.70–0.90** suggests partial content overlap. Adjust `NEAR_DUPLICATE_THRESHOLD` to tune sensitivity.

## PDF/A Archival Conversion

DocuElevate can optionally generate **PDF/A** archival copies of both the
original ingested file and the processed file.  PDF/A copies are saved as
parallel variants alongside the standard files—they do **not** replace the
originals.  This provides better legal coverage by producing time-stamped,
self-contained archival documents suitable for long-term storage and
compliance.

The conversion uses **ocrmypdf** (backed by Ghostscript), which is already
bundled in the Docker images.

> **Note:** PDF/A conversion may alter font rendering, especially for OCR text
> overlays produced by Microsoft Azure Document Intelligence.  This is expected
> and is why PDF/A copies are kept as parallel variants rather than
> replacements.

| Variable                      | Description                                                                                                       | Default                    |
|-------------------------------|-------------------------------------------------------------------------------------------------------------------|----------------------------|
| `ENABLE_PDFA_CONVERSION`     | Enable PDF/A archival variant generation for both original and processed files.                                     | `false`                    |
| `PDFA_FORMAT`                | PDF/A format variant: `1` (PDF/A-1b), `2` (PDF/A-2b), `3` (PDF/A-3b).                                             | `2`                        |
| `PDFA_UPLOAD_ORIGINAL`       | Upload the original-file PDF/A variant to all configured storage providers.                                        | `false`                    |
| `PDFA_UPLOAD_PROCESSED`      | Upload the processed-file PDF/A variant to all configured storage providers.                                       | `false`                    |
| `PDFA_UPLOAD_FOLDER`         | Subfolder name appended to each provider's folder for PDF/A uploads.                                               | `pdfa`                     |
| `GOOGLE_DRIVE_PDFA_FOLDER_ID`| Google Drive folder ID for PDF/A uploads (uses folder IDs, not paths). Empty = use default folder.                 | *(empty)*                  |
| `PDFA_TIMESTAMP_ENABLED`     | Enable RFC 3161 timestamping of PDF/A files (creates `.tsr` proof-of-existence files).                             | `false`                    |
| `PDFA_TIMESTAMP_URL`         | URL of the RFC 3161 Timestamp Authority.                                                                           | `https://freetsa.org/tsr`  |

### Storage Layout

When enabled, PDF/A copies are stored under `workdir/pdfa/`:

```
workdir/
├── original/          # Immutable copy of ingested file
├── processed/         # Processed file with embedded metadata
├── pdfa/
│   ├── original/      # PDF/A copy of the ingested file
│   │   └── *.pdf.tsr  # RFC 3161 timestamps (when timestamping enabled)
│   └── processed/     # PDF/A copy of the processed file (with -PDFA suffix)
│       └── *.pdf.tsr  # RFC 3161 timestamps (when timestamping enabled)
└── tmp/               # Temporary processing area
```

### Per-Provider Folder Overrides

When uploading PDF/A files to storage providers, DocuElevate appends the
`PDFA_UPLOAD_FOLDER` value as a subfolder to each provider's configured folder.
For example:

| Provider     | Regular Folder              | PDF/A Upload Folder              |
|--------------|-----------------------------|----------------------------------|
| Dropbox      | `/Documents`                | `/Documents/pdfa`                |
| S3           | `docs/uploads/`             | `docs/uploads/pdfa/`             |
| Nextcloud    | `/Files`                    | `/Files/pdfa`                    |
| OneDrive     | `Documents/Uploads`         | `Documents/Uploads/pdfa`         |
| Google Drive | *(folder ID)*               | `GOOGLE_DRIVE_PDFA_FOLDER_ID`    |

Set `PDFA_UPLOAD_FOLDER` to an empty string to upload PDF/A files into the
same folder as regular uploads.

### RFC 3161 Timestamping

When `PDFA_TIMESTAMP_ENABLED=true`, each PDF/A file is timestamped using
the configured TSA (default: [FreeTSA](https://freetsa.org)).  This creates
a `.tsr` file alongside each PDF/A file, providing cryptographic proof that
the document existed at a specific point in time.

Requires `openssl` on the PATH (included in Docker images).

**Other TSA options:**
- **GlobalSign** – enterprise, eIDAS qualified
- **DigiStamp** – high assurance, legal
- **IdenTrust** – legal, free with certificate purchase

### Configuration Example

```bash
# Enable PDF/A archival copies
ENABLE_PDFA_CONVERSION=true

# Use PDF/A-2b format (default, recommended for most use cases)
PDFA_FORMAT=2

# Upload both original and processed PDF/A to providers
PDFA_UPLOAD_ORIGINAL=true
PDFA_UPLOAD_PROCESSED=true

# PDF/A files go into a 'pdfa' subfolder on each provider
PDFA_UPLOAD_FOLDER=pdfa

# Enable RFC 3161 timestamping via FreeTSA
PDFA_TIMESTAMP_ENABLED=true
PDFA_TIMESTAMP_URL=https://freetsa.org/tsr
```

## Performance & Caching

DocuElevate automatically optimizes database access and uses Redis as a
caching layer for frequently accessed data.

### Database Indexes

On startup the application creates indexes on columns used for filtering,
sorting, and joining in the file listing and status computation queries:

| Table | Column | Purpose |
|---|---|---|
| `files` | `created_at` | Default sort order |
| `files` | `mime_type` | MIME type filter & dropdown |
| `processing_logs` | `file_id` | Log retrieval by file |
| `processing_logs` | `timestamp` | Log ordering |
| `file_processing_steps` | `status` | Status filter sub-queries |

These indexes are created idempotently on every startup so no manual
migration step is required.

### Redis Query Cache

When Redis is available (configured via `REDIS_URL`), DocuElevate caches
selected query results to avoid redundant database round-trips:

| Cache Key | TTL | Description |
|---|---|---|
| `mime_types` | 120 s | Distinct MIME types shown in the file-list filter dropdown |

The cache is **fail-open**: if Redis is unreachable the application falls
back to querying the database directly with no user-visible impact.

## Configuration Examples

### Minimal Configuration

This is the minimal configuration needed to run DocuElevate with local storage only:

```dotenv
DATABASE_URL=sqlite:///./app/database.db
REDIS_URL=redis://redis:6379/0
WORKDIR=/workdir
GOTENBERG_URL=http://gotenberg:3000
```

### Full Configuration with All Services

```dotenv
# Core settings
DATABASE_URL=sqlite:///./app/database.db
REDIS_URL=redis://redis:6379/0
WORKDIR=/workdir
GOTENBERG_URL=http://gotenberg:3000
EXTERNAL_HOSTNAME=docuelevate.example.com
ALLOW_FILE_DELETE=true

# IMAP settings
IMAP1_HOST=mail.example.com
IMAP1_PORT=993
IMAP1_USERNAME=user@example.com
IMAP1_PASSWORD=password
IMAP1_SSL=true
IMAP1_POLL_INTERVAL_MINUTES=5
IMAP1_DELETE_AFTER_PROCESS=false

# AI services
OPENAI_API_KEY=sk-...
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://...

# Authentication
AUTH_ENABLED=true
SESSION_SECRET=a-very-long-and-secure-random-secret-key-string-for-session-encryption
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_secure_password
ADMIN_GROUP_NAME=admin
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
AUTHENTIK_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
OAUTH_PROVIDER_NAME=Authentik SSO

# Multi-user mode (requires AUTH_ENABLED=true)
MULTI_USER_ENABLED=false
DEFAULT_DAILY_UPLOAD_LIMIT=0

# Storage services
PAPERLESS_NGX_API_TOKEN=...
PAPERLESS_HOST=https://paperless.example.com

DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
DROPBOX_FOLDER=/Documents/Uploads

NEXTCLOUD_UPLOAD_URL=https://nc.example.com/remote.php/dav/files/username
NEXTCLOUD_USERNAME=username
NEXTCLOUD_PASSWORD=password
NEXTCLOUD_FOLDER=/Documents/Uploads

# Google Drive
GOOGLE_DRIVE_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}
GOOGLE_DRIVE_FOLDER_ID=1a2b3c4d5e6f7g8h9i0j
GOOGLE_DRIVE_DELEGATE_TO=optional-user@example.com
GOOGLE_DRIVE_USE_OAUTH=true
GOOGLE_DRIVE_CLIENT_ID=your_client_id
GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret
GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token

# WebDAV
WEBDAV_URL=https://webdav.example.com/path
WEBDAV_USERNAME=username
WEBDAV_PASSWORD=password
WEBDAV_FOLDER=/Documents/Uploads
WEBDAV_VERIFY_SSL=True

# FTP
FTP_HOST=ftp.example.com
FTP_PORT=21
FTP_USERNAME=username
FTP_PASSWORD=password
FTP_FOLDER=/Documents/Uploads
FTP_USE_TLS=True
FTP_ALLOW_PLAINTEXT=True

# SFTP
SFTP_HOST=sftp.example.com
SFTP_PORT=22
SFTP_USERNAME=username
SFTP_PASSWORD=password
SFTP_FOLDER=/Documents/Uploads
# SFTP_PRIVATE_KEY=/path/to/key.pem
# SFTP_PRIVATE_KEY_PASSPHRASE=passphrase

# Email (shared SMTP – password reset & verification)
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=docuelevate@example.com
EMAIL_PASSWORD=password
EMAIL_USE_TLS=True
EMAIL_SENDER=DocuElevate System <docuelevate@example.com>

# Email Destination (document delivery – separate from shared email above)
DEST_EMAIL_HOST=smtp.example.com
DEST_EMAIL_PORT=587
DEST_EMAIL_USERNAME=docuelevate@example.com
DEST_EMAIL_PASSWORD=password
DEST_EMAIL_USE_TLS=True
DEST_EMAIL_SENDER=DocuElevate Delivery <docuelevate@example.com>
DEST_EMAIL_DEFAULT_RECIPIENT=recipient@example.com

# Notification Settings
# Configure notification services using Apprise URL format
NOTIFICATION_URLS=discord://webhook_id/webhook_token,mailto://user:pass@gmail.com,tgram://bot_token/chat_id
NOTIFY_ON_TASK_FAILURE=True
NOTIFY_ON_CREDENTIAL_FAILURE=True
NOTIFY_ON_STARTUP=True
NOTIFY_ON_SHUTDOWN=False

# OneDrive (Personal Account)
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=common
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads

# Amazon S3
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
S3_BUCKET_NAME=my-document-bucket
S3_FOLDER_PREFIX=documents/uploads/2023/  # Will place files in this subfolder
S3_STORAGE_CLASS=STANDARD
S3_ACL=private

# Uptime Kuma
UPTIME_KUMA_URL=https://kuma.example.com/api/push/abcde12345?status=up
UPTIME_KUMA_PING_INTERVAL=5

# Backup & Restore
BACKUP_ENABLED=True
BACKUP_DIR=/data/backups
BACKUP_REMOTE_DESTINATION=s3         # or dropbox, google_drive, onedrive, nextcloud, webdav, ftp, sftp, email
BACKUP_REMOTE_FOLDER=backups
BACKUP_RETAIN_HOURLY=96
BACKUP_RETAIN_DAILY=21
BACKUP_RETAIN_WEEKLY=13
```

## Selective Service Configuration

You can choose which document storage services to use by only including the relevant environment variables. For example, if you only want to use Dropbox, include only the Dropbox variables and omit the Paperless NGX and Nextcloud variables.

## System Reset / Factory Reset

DocuElevate provides two mechanisms for resetting the system to a clean state.  Both are **disabled by default** and must be explicitly enabled.

### Automatic Reset on Startup

Set `FACTORY_RESET_ON_STARTUP=true` to wipe all user data (database rows and work-files) every time the application starts.  This is useful for demo, testing, or ephemeral environments where you always want a fresh instance.

```dotenv
FACTORY_RESET_ON_STARTUP=true
```

> **Warning:** This destroys all documents, processing history, audit logs, and backups on every restart.  Application settings and configuration are preserved.

### Admin UI Reset Page

Set `ENABLE_FACTORY_RESET=true` to display the **System Reset** page in the admin navigation menu.  From this page, administrators can:

| Action | Confirmation | Description |
|--------|-------------|-------------|
| **Full Reset** | Type `DELETE` | Wipes all database rows and work-files.  The system returns to its initial state. |
| **Reset & Re-import** | Type `REIMPORT` | Copies original files to a `reimport/` folder inside the workdir, wipes everything, then configures the reimport folder as a watch folder so files are automatically re-ingested with the same processing pipeline, rate limits, and backoff strategy as regular uploads. |

```dotenv
ENABLE_FACTORY_RESET=true
```

### API Endpoints

When `ENABLE_FACTORY_RESET=true`, two admin-only API endpoints are available:

- `POST /api/admin/system-reset/full` — body: `{"confirmation": "DELETE"}`
- `POST /api/admin/system-reset/reimport` — body: `{"confirmation": "REIMPORT"}`
- `GET  /api/admin/system-reset/status` — returns current feature-flag state

### What Gets Deleted

| Deleted | Preserved |
|---------|-----------|
| All document records (`files` table) | Application settings (`application_settings` table) |
| Processing logs and steps | User accounts and profiles |
| Audit logs | Subscription plans |
| Backup records | Pipelines and scheduled jobs |
| Original, processed, and temporary files | The workdir directory itself |
| Watch-folder caches and ingestion state | OAuth and integration configuration |

## Configuration File Location

The `.env` file should be placed at the root of the project directory. When using Docker Compose, you can reference it with the `env_file` directive in your `docker-compose.yml`.
