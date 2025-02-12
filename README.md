# Document Processing System

## Overview

This project is designed to automate the process of handling, extracting, and processing documents. It integrates various services, such as AWS Textract, OpenAI, Dropbox, Nextcloud, and Paperless NGX, to extract metadata, process document contents, and store the results. The system is flexible and configurable via environment variables, allowing easy customization for different workflows.

## Features

- **Document Upload & Storage**: Upload documents to S3 and manage them with Dropbox and Nextcloud.
- **OCR Processing**: Use AWS Textract to extract text from scanned documents.
- **Metadata Extraction**: Automatically extract key information using OpenAI's API.
- **Document Management**: Store processed documents and metadata in Paperless NGX for easy retrieval.
- **IMAP Integration**: Fetch documents from multiple IMAP email accounts for processing.

## Environment Variables

The project is configured through the `.env` file, where you define credentials and settings such as:

- AWS access keys for Textract
- Dropbox and Nextcloud credentials
- Paperless NGX API token
- IMAP settings for fetching documents


# `.env` Configuration Explanation

This section provides details about each configuration option in the `.env` file. It also explains how to retrieve the necessary credentials and information for each setting.

| **Variable**                          | **Description** | **How to Obtain** |
|---------------------------------------|-----------------|-------------------|
| `DATABASE_URL`                        | Path to the SQLite database. | This is typically set to a local path where your database file will be stored. Example: `sqlite:///./app/database.db` |
| `REDIS_URL`                           | URL for connecting to Redis. | Set the URL for your Redis instance (e.g., `redis://localhost:6379/0`). Install Redis locally or use a cloud service like Redis Labs. |
| `WORKDIR`                             | Working directory for the application. | Choose a directory where your application will read and write files, such as `/workdir`. |
| `AWS_REGION`                          | AWS region for services like Textract and S3. | Set this to your AWS region (e.g., `eu-central-1`). You can find your region in the AWS Management Console. |
| `S3_BUCKET_NAME`                      | Name of your S3 bucket. | Create an S3 bucket in your AWS account and use its name (e.g., `my-bucket-name`). |
| `NEXTCLOUD_UPLOAD_URL`                | URL for uploading files to Nextcloud. | Format the URL for Nextcloud's WebDAV endpoint. Example: `https://nextcloud.example.com/remote.php/dav/files/<USERNAME>` |
| `NEXTCLOUD_FOLDER`                    | Folder in Nextcloud where files are uploaded. | Choose the folder path where documents will be uploaded (e.g., `/Documents/Uploads`). |
| `PAPERLESS_NGX_URL`                   | URL for Paperless NGX API endpoint for document uploads. | Obtain this from your Paperless NGX instance (e.g., `https://paperless.example.com/api/documents/post_document/`). |
| `PAPERLESS_HOST`                      | Host URL for Paperless NGX. | Set this to the root URL of your Paperless NGX instance (e.g., `https://paperless.example.com`). |
| **Tokens/API Credentials**            | **Tokens and keys for third-party services** | **How to Obtain** |
| `AWS_ACCESS_KEY_ID`                   | AWS Access Key ID for authentication with AWS services. | Create a new access key from the AWS IAM console under **Access Management** → **Users**. |
| `AWS_SECRET_ACCESS_KEY`               | AWS Secret Access Key for AWS authentication. | This is generated alongside the access key ID in the AWS IAM console. Keep this secure. |
| `OPENAI_API_KEY`                      | API key for accessing OpenAI services. | Get this from the [OpenAI platform](https://platform.openai.com/account/api-keys). |
| `PAPERLESS_NGX_API_TOKEN`             | API token for Paperless NGX. | Obtain this from your Paperless NGX instance or generate a new token from its settings. |
| `DROPBOX_APP_KEY`                     | Dropbox App Key for Dropbox API. | Generate this in the [Dropbox Developer Console](https://www.dropbox.com/developers/apps/create). |
| `DROPBOX_APP_SECRET`                  | Dropbox App Secret for Dropbox API. | This can be found in the Dropbox Developer Console after creating your app. |
| `DROPBOX_REFRESH_TOKEN`               | Dropbox Refresh Token for accessing Dropbox. | You can get this by going through the OAuth process using Dropbox's CLI or API. Check the [OAuth guide](https://www.dropbox.com/developers/reference/oauth-guide). |
| **User Credentials**                  | **Authentication for various services** | **How to Obtain** |
| `ADMIN_USERNAME`                       | Username for admin access to the application. | This is typically chosen by you and set for managing your application. |
| `ADMIN_PASSWORD`                       | Password for admin access. | Set this to a strong password for admin authentication. |
| `NEXTCLOUD_USERNAME`                   | Username for accessing Nextcloud. | Your Nextcloud username (e.g., `username@example.com`). |
| `NEXTCLOUD_PASSWORD`                   | Password for accessing Nextcloud. | The password associated with your Nextcloud account. |
| `IMAP1_USERNAME`                       | IMAP username for the first email account. | The email address associated with the first IMAP account. |
| `IMAP1_PASSWORD`                       | IMAP password for the first email account. | The password for the above IMAP account. |
| `IMAP2_USERNAME`                       | IMAP username for the second email account. | The email address associated with the second IMAP account. |
| `IMAP2_PASSWORD`                       | IMAP password for the second email account. | The password for the second IMAP account. |
| **IMAP Settings**                      | **IMAP configuration for email fetching** | **How to Obtain** |
| `IMAP1_HOST`                           | Hostname of the first IMAP server. | The hostname for the first email provider (e.g., `mail.example.com` or `imap.gmail.com`). |
| `IMAP1_PORT`                           | Port for the first IMAP server. | Typically `993` for SSL/TLS. |
| `IMAP1_SSL`                            | Enable SSL for the first IMAP connection. | Set to `true` to enable SSL. |
| `IMAP1_POLL_INTERVAL_MINUTES`          | How often to poll the first IMAP server (in minutes). | Set to `5` or adjust as needed. |
| `IMAP1_DELETE_AFTER_PROCESS`           | Delete emails after processing in the first IMAP account. | Set to `false` to leave emails or `true` to delete after processing. |
| `IMAP2_HOST`                           | Hostname of the second IMAP server. | The hostname for the second email provider (e.g., `imap.gmail.com`). |
| `IMAP2_PORT`                           | Port for the second IMAP server. | Typically `993` for SSL/TLS. |
| `IMAP2_SSL`                            | Enable SSL for the second IMAP connection. | Set to `true` to enable SSL. |
| `IMAP2_POLL_INTERVAL_MINUTES`          | How often to poll the second IMAP server (in minutes). | Set to `10` or adjust as needed. |
| `IMAP2_DELETE_AFTER_PROCESS`           | Delete emails after processing in the second IMAP account. | Set to `false` to leave emails or `true` to delete after processing. |


## Setup

1. **Clone the repository**:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the environment**:  
   - Create a `.env` file based on the provided example and fill in the required fields (AWS, Dropbox, IMAP, etc.).

4. **Run the application**:
   ```bash
   python app.py
   ```

## Notes

- The system requires access to AWS Textract, Dropbox, Nextcloud, and Paperless NGX for full functionality.
- Ensure you have proper permissions set up for these services (IAM roles, API tokens, etc.).
