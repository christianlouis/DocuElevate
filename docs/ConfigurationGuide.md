# Configuration Guide

DocuNova is designed to be highly configurable through environment variables. This guide explains all available configuration options and how to use them effectively.

## Environment Variables

Configuration is primarily done through environment variables specified in a `.env` file.

### Core Settings

| **Variable**           | **Description**                                          | **Example**                    |
|------------------------|----------------------------------------------------------|--------------------------------|
| `DATABASE_URL`         | Path/URL to the SQLite database (or other SQL backend). | `sqlite:///./app/database.db`  |
| `REDIS_URL`            | URL for Redis, used by Celery for broker & result store. | `redis://redis:6379/0`         |
| `WORKDIR`              | Working directory for the application.                  | `/workdir`                     |
| `GOTENBERG_URL`        | Gotenberg PDF processing URL.                           | `http://gotenberg:3000`        |
| `EXTERNAL_HOSTNAME`    | The external hostname for the application.             | `docunova.example.com`         |

### IMAP Configuration

DocuNova can monitor multiple IMAP mailboxes for document attachments. Each mailbox uses a numbered prefix (e.g., `IMAP1_`, `IMAP2_`).

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
| `AUTHENTIK_CLIENT_ID`   | Client ID for Authentik OAuth2.                              |
| `AUTHENTIK_CLIENT_SECRET` | Client secret for Authentik OAuth2.                        |
| `AUTHENTIK_CONFIG_URL`  | Configuration URL for Authentik OpenID Connect.             |

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

| **Variable**            | **Description**                                  | **How to Obtain**                                      |
|-------------------------|--------------------------------------------------|---------------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key.                             | [Dropbox Developer Console](#setting-up-dropbox-integration) |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret.                          | [Dropbox Developer Console](#setting-up-dropbox-integration) |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox.                | Follow steps in [Dropbox Setup](#setting-up-dropbox-integration) |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads.         | e.g. `"/Documents/Uploads"` (leading slash optional)    |

### Nextcloud

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `NEXTCLOUD_UPLOAD_URL`  | Nextcloud WebDAV URL (e.g. `https://nc.example.com/remote.php/dav/files/<USERNAME>`). |
| `NEXTCLOUD_USERNAME`    | Nextcloud login username.                                    |
| `NEXTCLOUD_PASSWORD`    | Nextcloud login password.                                    |
| `NEXTCLOUD_FOLDER`      | Destination folder in Nextcloud (e.g. `"/Documents/Uploads"`). |

### Google Drive

| **Variable**                    | **Description**                                       | **How to Obtain**                                    |
|---------------------------------|-------------------------------------------------------|------------------------------------------------------|
| `GOOGLE_DRIVE_CREDENTIALS_JSON` | JSON string containing service account credentials    | [Google Cloud Console](#setting-up-google-drive-api) |
| `GOOGLE_DRIVE_FOLDER_ID`        | Google Drive folder ID for file uploads               | See [folder ID instructions](#get-google-drive-folder-id) |
| `GOOGLE_DRIVE_DELEGATE_TO`      | Email address to delegate permissions (optional)      | User email in your Google Workspace                  |

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
| `EMAIL_SENDER`             | From address (e.g., `"DocuNova <docunova@example.com>"`). |
| `EMAIL_DEFAULT_RECIPIENT`  | Default recipient email if none specified in the task.    |

### OneDrive / Microsoft Graph

| **Variable**                    | **Description**                                       | **How to Obtain**                                    |
|---------------------------------|-------------------------------------------------------|------------------------------------------------------|
| `ONEDRIVE_CLIENT_ID`            | Azure AD application client ID                        | [Microsoft Azure Portal](#setting-up-onedrive-integration) |
| `ONEDRIVE_CLIENT_SECRET`        | Azure AD application client secret                    | [Microsoft Azure Portal](#setting-up-onedrive-integration) |
| `ONEDRIVE_TENANT_ID`            | Azure AD tenant ID: use "common" for personal accounts or your tenant ID for corporate accounts | [Microsoft Azure Portal](#setting-up-onedrive-integration) |
| `ONEDRIVE_REFRESH_TOKEN`        | OAuth 2.0 refresh token (required for personal accounts) | Follow steps in [Personal OneDrive Setup](#personal-onedrive-setup) |
| `ONEDRIVE_FOLDER_PATH`          | Folder path in OneDrive for storing documents         | e.g. `/Documents/Uploads` or `Documents/Uploads`     |

## Setting up OneDrive Integration

There are two main types of Microsoft accounts that can be used with OneDrive integration:

1. **Personal Microsoft Accounts** - These include accounts with @outlook.com, @hotmail.com, @live.com domains, or personal Microsoft accounts linked to other email addresses (like Gmail)
2. **Work/School Microsoft Accounts** - These are accounts managed by an organization through Microsoft 365 or Azure Active Directory

The setup process differs slightly based on which account type you're using.

### Common Setup Steps (All Account Types)

1. **Register an application in Azure Active Directory**:
   - Go to the [Azure Portal](https://portal.azure.com/)
   - Navigate to "Azure Active Directory" > "App registrations"
   - Click "New registration"
   - Enter a name for your application (e.g., "DocuNova")
   - For "Supported account types", select the appropriate option:
     - For personal accounts: "Accounts in any organizational directory and personal Microsoft accounts"
     - For corporate accounts only: "Accounts in this organizational directory only"
   - For Redirect URI, select "Web" and enter a URL you can access (e.g., `http://localhost:8000/auth/callback`)
   - Click "Register"

2. **Get Application (client) ID**:
   - After registration, note the "Application (client) ID" from the overview page
   - Set this value as `ONEDRIVE_CLIENT_ID`

3. **Create a client secret**:
   - In your application page, go to "Certificates & secrets"
   - Under "Client secrets," click "New client secret"
   - Add a description and select an expiration period
   - Click "Add" and immediately copy the secret value (it will only be shown once)
   - Set this value as `ONEDRIVE_CLIENT_SECRET`

### For Personal Microsoft Accounts

If you're using a personal Microsoft account (@outlook.com, @hotmail.com, or personal accounts linked to other emails):

1. **Set Tenant ID to "common"**:
   - Set `ONEDRIVE_TENANT_ID=common` in your configuration

2. **Configure API permissions**:
   - In your application page, go to "API permissions"
   - Click "Add a permission"
   - Select "Microsoft Graph" > "Delegated permissions"
   - Search for and add the following permissions:
     - `Files.ReadWrite` (Allows the app to read and write files that the user has access to)
     - `offline_access` (Needed for refresh tokens)
   - Click "Add permissions"

3. **Generate a Refresh Token**:
   - Use the following URL (replace CLIENT_ID and REDIRECT_URI with your values):
   ```
   https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=YOUR_REDIRECT_URI&response_mode=query&scope=offline_access%20Files.ReadWrite
   ```
   - Open this URL in your browser
   - Sign in with your personal Microsoft account
   - After authentication, you'll be redirected to your redirect URI with a code parameter in the URL
   - Copy the code value from the URL (everything after "code=")

4. **Exchange Code for Refresh Token**:
   - Use the following command to exchange the code for tokens:
   ```bash
   curl -X POST https://login.microsoftonline.com/common/oauth2/v2.0/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_id=YOUR_CLIENT_ID&scope=offline_access Files.ReadWrite&code=YOUR_AUTH_CODE&redirect_uri=YOUR_REDIRECT_URI&grant_type=authorization_code&client_secret=YOUR_CLIENT_SECRET"
   ```
   - From the response JSON, copy the `refresh_token` value
   - Set this as `ONEDRIVE_REFRESH_TOKEN` in your configuration

### For Corporate Microsoft Accounts

If you're using a work/school account provided by your organization:

1. **Get your Tenant ID**:
   - In the Azure Portal, find your "Tenant ID" (also called "Directory ID")
   - It will be in the Azure Active Directory overview or properties section
   - Set this value as `ONEDRIVE_TENANT_ID` in your configuration

2. **Configuration based on use case**:

   **Option A: Access your own OneDrive (Interactive Login)**
   
   This option requires a refresh token just like personal accounts:
   - Follow the same steps as for personal accounts, but use your work email to sign in
   - Make sure to set `ONEDRIVE_TENANT_ID` to your organization's tenant ID instead of "common"
   - Set the refresh token you receive as `ONEDRIVE_REFRESH_TOKEN`

   **Option B: Access OneDrive as a system service (App-only access)**
   
   This option is for service accounts or automated systems with no user interaction:
   - In API permissions, add "Application permissions" instead of "Delegated permissions"
   - Add `Files.ReadWrite.All` permission under "Application permissions"
   - Click "Grant admin consent" (requires admin privileges)
   - In this case, `ONEDRIVE_REFRESH_TOKEN` is not needed as the app will use client credentials flow
   - Note: This approach can only access specific shared folders or sites, not personal OneDrives

### Troubleshooting OAuth Login Issues

If you encounter errors during authentication:

1. **Check account permissions**: 
   - Ensure your Microsoft account has the necessary permissions to grant access
   - For corporate accounts, check if your admin has restricted third-party app access

2. **Permission errors**: 
   - Verify the app registration has the correct API permissions
   - For corporate accounts, ensure an admin has consented to the permissions

3. **Refresh token expired**: 
   - If uploads stop working, you may need to generate a new refresh token
   - Repeat the process to get a new authorization code and refresh token

### Configuration Examples

**Personal Microsoft Account:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=common
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```

**Corporate Account with Interactive Login:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=87654321-4321-4321-4321-210987654321
ONEDRIVE_REFRESH_TOKEN=your_refresh_token
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```

**Corporate Account with App-Only Access:**
```dotenv
ONEDRIVE_CLIENT_ID=12345678-1234-1234-1234-123456789012
ONEDRIVE_CLIENT_SECRET=your_client_secret
ONEDRIVE_TENANT_ID=87654321-4321-4321-4321-210987654321
# No refresh token needed for app-only access
ONEDRIVE_FOLDER_PATH=Documents/Uploads
```

### Amazon S3

| **Variable**                    | **Description**                                       | **How to Obtain**                                    |
|---------------------------------|-------------------------------------------------------|------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`             | AWS IAM access key ID                                 | [AWS IAM Console](#setting-up-amazon-s3-integration) |
| `AWS_SECRET_ACCESS_KEY`         | AWS IAM secret access key                             | [AWS IAM Console](#setting-up-amazon-s3-integration) |
| `AWS_REGION`                    | AWS region where your S3 bucket is located (default: `us-east-1`) | [AWS S3 Console](https://s3.console.aws.amazon.com/) |
| `S3_BUCKET_NAME`                | Name of your S3 bucket                                | [AWS S3 Console](https://s3.console.aws.amazon.com/) |
| `S3_FOLDER_PREFIX`              | Optional prefix/folder path for uploaded files        | e.g. `documents/` or `uploads/2023/` (include trailing slash) |
| `S3_STORAGE_CLASS`              | Storage class for uploaded objects (default: `STANDARD`) | [S3 Storage Classes](https://aws.amazon.com/s3/storage-classes/) |
| `S3_ACL`                        | Access control for uploaded files (default: `private`) | `private`, `public-read`, etc. |

## Configuration Examples

### Minimal Configuration

This is the minimal configuration needed to run DocuNova with local storage only:

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
EXTERNAL_HOSTNAME=docunova.example.com

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
AUTHENTIK_CLIENT_ID=...
AUTHENTIK_CLIENT_SECRET=...
AUTHENTIK_CONFIG_URL=https://auth.example.com/.well-known/openid-configuration

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
EMAIL_USERNAME=docunova@example.com
EMAIL_PASSWORD=password
EMAIL_USE_TLS=True
EMAIL_SENDER=DocuNova System <docunova@example.com>
EMAIL_DEFAULT_RECIPIENT=recipient@example.com

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
```

## Setting up Google Drive API

To use the Google Drive integration, follow these steps:

1. **Create a Google Cloud Project**:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Navigate to "APIs & Services" > "Library"
   - Search for and enable the "Google Drive API"

2. **Create Service Account**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "Service Account"
   - Fill in the service account details and click "Create"
   - Add appropriate roles (e.g., "Editor" for full access)
   - Click "Continue" and then "Done"

3. **Generate Service Account Key**:
   - Find your service account in the list and click on it
   - Go to the "Keys" tab
   - Click "Add Key" > "Create New Key"
   - Choose JSON format and click "Create"
   - The key file will be downloaded automatically

4. **Configure DocuNova**:
   - Open the downloaded JSON key file
   - Set the entire JSON content as the `GOOGLE_DRIVE_CREDENTIALS_JSON` environment variable
   - For security, ensure the JSON is properly escaped if your deployment method requires it

### Get Google Drive Folder ID

To find your Google Drive folder ID:

1. Navigate to the desired folder in Google Drive web interface
2. The URL will look like: `https://drive.google.com/drive/folders/1a2b3c4d5e6f7g8h9i0j`
3. The string after "folders/" is your folder ID (in this example: `1a2b3c4d5e6f7g8h9i0j`)
4. Set this value as `GOOGLE_DRIVE_FOLDER_ID` in your configuration

### Domain-Wide Delegation (Optional)

If you need the service account to access files on behalf of users in your Google Workspace:

1. In your [Google Workspace Admin Console](https://admin.google.com/), go to:
   - Security > API Controls > Domain-wide Delegation
2. Click "Add new" and provide:
   - Client ID: your service account's client ID (found in the JSON credentials file)
   - OAuth Scopes: `https://www.googleapis.com/auth/drive`
3. Set `GOOGLE_DRIVE_DELEGATE_TO` to the email address of the user to impersonate

This setup is only relevant for Google Workspace environments where you need the service account to access user-specific files.

## Setting up Dropbox Integration

To use the Dropbox integration, you'll need to create a Dropbox app and generate OAuth2 credentials:

1. **Create a Dropbox App**:
   - Go to the [Dropbox Developer Apps Console](https://www.dropbox.com/developers/apps)
   - Click "Create app"
   - Select "Scoped access" for API
   - Choose "Full Dropbox" access (or "App folder" for more restricted access)
   - Give your app a name (e.g., "DocuNova")
   - Click "Create app"

2. **Configure App Permissions**:
   - In your app's settings page, go to the "Permissions" tab
   - Enable the following permissions:
     - `files.content.write` (to upload files)
     - `files.content.read` (if you need to read file content)
   - Click "Submit" to save changes

3. **Get App Key and Secret**:
   - On your app's settings page, find the "App key" and "App secret"
   - Set these as `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET` in your configuration

4. **Generate a Refresh Token**:
   - Go to the "OAuth 2" tab in your app settings
   - Add a redirect URI: `http://localhost` (this is for the authorization flow)
   - Generate an authorization URL with these instructions:
   
   ```
   https://www.dropbox.com/oauth2/authorize?client_id=YOUR_APP_KEY&response_type=code&token_access_type=offline
   ```
   
   - Replace `YOUR_APP_KEY` with your app key
   - Open this URL in your browser
   - Authorize the app when prompted
   - You'll be redirected to `localhost` with a code parameter in the URL
   - Copy this code parameter

5. **Exchange the Code for a Refresh Token**:
   - Use this curl command to exchange the code for tokens:
   
   ```bash
   curl -X POST https://api.dropboxapi.com/oauth2/token \
     -d code=YOUR_AUTH_CODE \
     -d grant_type=authorization_code \
     -d client_id=YOUR_APP_KEY \
     -d client_secret=YOUR_APP_SECRET \
     -d redirect_uri=http://localhost
   ```
   
   - From the response, copy the `refresh_token` value

6. **Configure DocuNova**:
   - Set `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, and `DROPBOX_REFRESH_TOKEN` with your values
   - Set `DROPBOX_FOLDER` to the path where files should be uploaded

The system will use the refresh token to automatically generate short-lived access tokens when needed, so you shouldn't need to worry about token expiration.

## Setting up Amazon S3 Integration

To use the Amazon S3 integration, you'll need an AWS account and an S3 bucket:

1. **Create an S3 bucket**:
   - Go to the [Amazon S3 Console](https://s3.console.aws.amazon.com/)
   - Click "Create bucket"
   - Enter a globally unique name for your bucket
   - Select your preferred AWS region
   - Configure other settings as needed (block public access is recommended)
   - Click "Create bucket"

2. **Create an IAM User with S3 Access**:
   - Go to the [AWS IAM Console](https://console.aws.amazon.com/iam/)
   - Navigate to "Users" and click "Add users"
   - Enter a name (e.g., "docunova-s3-access")
   - For access type, select "Programmatic access"
   - Click "Next: Permissions"
   - Choose "Attach existing policies directly" and search for "AmazonS3FullAccess"
   - For more security, you can create a custom policy limiting access to just your bucket
   - Click through to review and create the user
   - On the final page, you'll see the Access Key ID and Secret Access Key
   - Save these credentials securely as they won't be shown again

3. **Configure DocuNova**:
   - Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to the credentials from step 2
   - Set `AWS_REGION` to the region where your bucket was created (e.g., "us-east-1")
   - Set `S3_BUCKET_NAME` to your bucket name
   - Set `S3_FOLDER_PREFIX` to organize files in specific subfolder paths (e.g., "invoices/" or "documents/2023/")
   - Optionally customize `S3_STORAGE_CLASS` and `S3_ACL` for your storage needs

4. **Optional: Create a Custom IAM Policy** (for better security):
   - In IAM console, go to "Policies" and click "Create policy"
   - Use the JSON editor and paste a policy like this (replace `your-bucket-name`):
     ```json
     {
         "Version": "2012-10-17",
         "Statement": [
             {
                 "Effect": "Allow",
                 "Action": [
                     "s3:PutObject",
                     "s3:GetObject",
                     "s3:ListBucket"
                 ],
                 "Resource": [
                     "arn:aws:s3:::your-bucket-name",
                     "arn:aws:s3:::your-bucket-name/*"
                 ]
             }
         ]
     }
     ```
   - After creating the policy, attach it to your user instead of the broader AmazonS3FullAccess

## Selective Service Configuration

You can choose which document storage services to use by only including the relevant environment variables. For example, if you only want to use Dropbox, include only the Dropbox variables and omit the Paperless NGX and Nextcloud variables.

## Configuration File Location

The `.env` file should be placed at the root of the project directory. When using Docker Compose, you can reference it with the `env_file` directive in your `docker-compose.yml`.
