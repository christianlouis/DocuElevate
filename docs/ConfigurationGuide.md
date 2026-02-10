# Configuration Guide

DocuElevate is designed to be highly configurable through environment variables. This guide explains all available configuration options and how to use them effectively.

## Environment Variables

Configuration is primarily done through environment variables specified in a `.env` file.

### Core Settings

| **Variable**           | **Description**                                          | **Example**                    |
|------------------------|----------------------------------------------------------|--------------------------------|
| `DATABASE_URL`         | Path/URL to the SQLite database (or other SQL backend). | `sqlite:///./app/database.db`  |
| `REDIS_URL`            | URL for Redis, used by Celery for broker & result store. | `redis://redis:6379/0`         |
| `WORKDIR`              | Working directory for the application.                  | `/workdir`                     |
| `GOTENBERG_URL`        | Gotenberg PDF processing URL.                           | `http://gotenberg:3000`        |
| `EXTERNAL_HOSTNAME`    | The external hostname for the application.             | `docuelevate.example.com`      |
| `ALLOW_FILE_DELETE`    | Enable file deletion in the web interface (`true`/`false`). | `true`                      |

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

### File Upload Size Limits

**Security Feature**: Control file upload sizes to prevent resource exhaustion attacks. See [SECURITY_AUDIT.md](../SECURITY_AUDIT.md#5-file-upload-size-limits) for security details.

| **Variable**              | **Description**                                                                                              | **Default**   |
|---------------------------|--------------------------------------------------------------------------------------------------------------|---------------|
| `MAX_UPLOAD_SIZE`         | Maximum file upload size in bytes. Files exceeding this limit are rejected.                                | `1073741824` (1GB) |
| `MAX_SINGLE_FILE_SIZE`    | Optional: Maximum size for a single file chunk in bytes. Files exceeding this are split into smaller parts. | `None` (no splitting) |

**Configuration Examples:**

```bash
# Default: Allow up to 1GB uploads, no splitting
MAX_UPLOAD_SIZE=1073741824

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
  - Uses PyPDF2 to properly parse PDF structure
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

### IMAP Configuration

DocuElevate can monitor multiple IMAP mailboxes for document attachments. Each mailbox uses a numbered prefix (e.g., `IMAP1_`, `IMAP2_`).

| **Variable**                  | **Description**                                              | **Example**       |
|-------------------------------|--------------------------------------------------------------|-------------------|
| `IMAP1_HOST`                  | Hostname for first IMAP server.                             | `mail.example.com`|
| `IMAP1_PORT`                  | Port number (usually `993`).                                | `993`             |
| `IMAP1_USERNAME`              | IMAP login (first mailbox).                                 | `user@example.com`|
| `IMAP1_PASSWORD`              | IMAP password (first mailbox).                              | `*******`         |
| `IMAP1_SSL`                   | Use SSL (`true`/`false`).                                   | `true`            |
| `IMAP1_POLL_INTERVAL_MINUTES` | Frequency in minutes to poll for new mail.                  | `5`               |

### Authentication

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `AUTH_ENABLED`          | Enable or disable authentication (`true`/`false`).           |
| `SESSION_SECRET`        | Secret key used to encrypt sessions and cookies (at least 32 chars). |
| `ADMIN_USERNAME`        | Username for basic authentication (when not using OIDC).     |
| `ADMIN_PASSWORD`        | Password for basic authentication (when not using OIDC).     |
| `AUTHENTIK_CLIENT_ID`   | Client ID for Authentik OAuth2/OIDC authentication.          |
| `AUTHENTIK_CLIENT_SECRET` | Client secret for Authentik OAuth2/OIDC authentication.    |
| `AUTHENTIK_CONFIG_URL`  | Configuration URL for Authentik OpenID Connect.             |
| `OAUTH_PROVIDER_NAME`   | Display name for the OAuth provider button.                  |

### Security Headers

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

### OpenAI & Azure Document Intelligence

| **Variable**                     | **Description**                          | **How to Obtain**                                                        |
|---------------------------------|------------------------------------------|--------------------------------------------------------------------------|
| `OPENAI_API_KEY`                | OpenAI API key for GPT metadata extraction. | [OpenAI API keys](https://platform.openai.com/account/api-keys)             |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Azure Document Intelligence API key for OCR. | [Azure Portal](https://portal.azure.com/) |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Endpoint URL for Azure Doc Intelligence API. | [Azure Portal](https://portal.azure.com/) |

### Paperless NGX

| **Variable**                  | **Description**                                     |
|-------------------------------|-----------------------------------------------------|
| `PAPERLESS_NGX_API_TOKEN`     | API token for Paperless NGX.                       |
| `PAPERLESS_HOST`              | Root URL for Paperless NGX (e.g. `https://paperless.example.com`). |

### Dropbox

| **Variable**            | **Description**                                  | 
|-------------------------|--------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key.                             |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret.                          |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox.                |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads.         |

For detailed setup instructions, see the [Dropbox Setup Guide](DropboxSetup.md).

### Nextcloud

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `NEXTCLOUD_UPLOAD_URL`  | Nextcloud WebDAV URL (e.g. `https://nc.example.com/remote.php/dav/files/<USERNAME>`). |
| `NEXTCLOUD_USERNAME`    | Nextcloud login username.                                    |
| `NEXTCLOUD_PASSWORD`    | Nextcloud login password.                                    |
| `NEXTCLOUD_FOLDER`      | Destination folder in Nextcloud (e.g. `"/Documents/Uploads"`). |

### Google Drive

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
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
| `WEBDAV_URL`            | WebDAV server URL (e.g. `https://webdav.example.com/path`).   |
| `WEBDAV_USERNAME`       | WebDAV authentication username.                               |
| `WEBDAV_PASSWORD`       | WebDAV authentication password.                               |
| `WEBDAV_FOLDER`         | Destination folder on WebDAV server (e.g. `"/Documents/Uploads"`). |
| `WEBDAV_VERIFY_SSL`     | Whether to verify SSL certificates (default: `True`).         |

### FTP

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
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
| `SFTP_HOST`                  | SFTP server hostname or IP address.                    |
| `SFTP_PORT`                  | SFTP port (default: `22`).                             |
| `SFTP_USERNAME`              | SFTP authentication username.                          |
| `SFTP_PASSWORD`              | SFTP authentication password (if not using private key). |
| `SFTP_FOLDER`                | Destination folder on SFTP server.                     |
| `SFTP_PRIVATE_KEY`           | Path to private key file for authentication (optional). |
| `SFTP_PRIVATE_KEY_PASSPHRASE`| Passphrase for private key if required (optional).     |

### Email

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `EMAIL_HOST`               | SMTP server hostname.                                     |
| `EMAIL_PORT`               | SMTP port (default: `587`).                               |
| `EMAIL_USERNAME`           | SMTP authentication username.                             |
| `EMAIL_PASSWORD`           | SMTP authentication password.                             |
| `EMAIL_USE_TLS`            | Whether to use TLS (default: `True`).                     |
| `EMAIL_SENDER`             | From address (e.g., `"DocuElevate <docuelevate@example.com>"`). |
| `EMAIL_DEFAULT_RECIPIENT`  | Default recipient email if none specified in the task.    |

### OneDrive / Microsoft Graph

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `ONEDRIVE_CLIENT_ID`            | Azure AD application client ID                        |
| `ONEDRIVE_CLIENT_SECRET`        | Azure AD application client secret                    |
| `ONEDRIVE_TENANT_ID`            | Azure AD tenant ID: use "common" for personal accounts or your tenant ID for corporate accounts |
| `ONEDRIVE_REFRESH_TOKEN`        | OAuth 2.0 refresh token (required for personal accounts) |
| `ONEDRIVE_FOLDER_PATH`          | Folder path in OneDrive for storing documents         |

For detailed setup instructions, see the [OneDrive Setup Guide](OneDriveSetup.md).

### Amazon S3

| **Variable**                    | **Description**                                       |
|---------------------------------|-------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`             | AWS IAM access key ID                                 |
| `AWS_SECRET_ACCESS_KEY`         | AWS IAM secret access key                             |
| `AWS_REGION`                    | AWS region where your S3 bucket is located (default: `us-east-1`) |
| `S3_BUCKET_NAME`                | Name of your S3 bucket                                |
| `S3_FOLDER_PREFIX`              | Optional prefix/folder path for uploaded files        |
| `S3_STORAGE_CLASS`              | Storage class for uploaded objects (default: `STANDARD`) |
| `S3_ACL`                        | Access control for uploaded files (default: `private`) |

For detailed setup instructions, see the [Amazon S3 Setup Guide](AmazonS3Setup.md).

### Notification System

| **Variable**                | **Description**                                           |
|----------------------------|----------------------------------------------------------|
| `NOTIFICATION_URLS`        | Comma-separated list of Apprise notification URLs         |
| `NOTIFY_ON_TASK_FAILURE`   | Send notifications on task failures (`True`/`False`)     |
| `NOTIFY_ON_CREDENTIAL_FAILURE` | Send notifications on credential failures (`True`/`False`) |
| `NOTIFY_ON_STARTUP`        | Send notification when system starts (`True`/`False`)    |
| `NOTIFY_ON_SHUTDOWN`       | Send notification when system shuts down (`True`/`False`)|

For detailed setup instructions, see the [Notifications Setup Guide](NotificationsSetup.md).

### Uptime Kuma

| **Variable**                | **Description**                                                |
|-----------------------------|----------------------------------------------------------------|
| `UPTIME_KUMA_URL`           | Uptime Kuma push URL for monitoring the application's health.   |
| `UPTIME_KUMA_PING_INTERVAL` | How often to ping Uptime Kuma in minutes (default: `5`).       |

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
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
AUTHENTIK_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration
OAUTH_PROVIDER_NAME=Authentik SSO

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

# Email
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=docuelevate@example.com
EMAIL_PASSWORD=password
EMAIL_USE_TLS=True
EMAIL_SENDER=DocuElevate System <docuelevate@example.com>
EMAIL_DEFAULT_RECIPIENT=recipient@example.com

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
```

## Selective Service Configuration

You can choose which document storage services to use by only including the relevant environment variables. For example, if you only want to use Dropbox, include only the Dropbox variables and omit the Paperless NGX and Nextcloud variables.

## Configuration File Location

The `.env` file should be placed at the root of the project directory. When using Docker Compose, you can reference it with the `env_file` directive in your `docker-compose.yml`.
