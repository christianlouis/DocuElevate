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
