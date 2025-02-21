# Document Processing System

## Overview

This project automates the handling, extraction, and processing of documents using a combination of services such as OpenAI, Dropbox, Nextcloud, and Paperless NGX. The system extracts metadata, processes document contents, and stores the results efficiently. It is designed for flexibility and configurability through environment variables, making it easily customizable for different workflows.

## Features

- **Document Upload & Storage**: Upload and manage documents via Dropbox and Nextcloud.
- **OCR Processing**: Extract text from scanned documents.
- **Metadata Extraction**: Automatically extract key information using OpenAI's API.
- **Document Management**: Store processed documents and metadata in Paperless NGX for easy retrieval.
- **IMAP Integration**: Fetch documents from multiple IMAP email accounts for processing.

## Environment Variables

The project is configured via the `.env` file, where credentials and settings for different services are defined. Below is a breakdown of key configuration variables:

### General Configuration

| **Variable** | **Description** | **How to Obtain** |
|-------------|----------------|-------------------|
| `DATABASE_URL` | Path to the SQLite database. | Example: `sqlite:///./app/database.db` |
| `REDIS_URL` | URL for Redis connection. | Example: `redis://redis:6379/0` |
| `WORKDIR` | Working directory for the application. | Example: `/workdir` |
| `NEXTCLOUD_UPLOAD_URL` | Nextcloud WebDAV upload URL. | Example: `https://nextcloud.example.com/remote.php/dav/files/<USERNAME>` |
| `NEXTCLOUD_FOLDER` | Folder in Nextcloud for file uploads. | Example: `/Documents/Uploads` |
| `PAPERLESS_NGX_URL` | Paperless NGX API endpoint. | Example: `https://paperless.example.com/api/documents/post_document/` |
| `PAPERLESS_HOST` | Root URL for Paperless NGX. | Example: `https://paperless.example.com` |

### Tokens/API Credentials

| **Variable** | **Description** | **How to Obtain** |
|-------------|----------------|-------------------|
| `OPENAI_API_KEY` | API key for OpenAI services. | Get from [OpenAI platform](https://platform.openai.com/account/api-keys). |
| `PAPERLESS_NGX_API_TOKEN` | API token for Paperless NGX. | Obtain from your Paperless NGX instance. |
| `DROPBOX_APP_KEY` | Dropbox API key. | Generate from the [Dropbox Developer Console](https://www.dropbox.com/developers/apps/create). |
| `DROPBOX_APP_SECRET` | Dropbox API secret. | Available in the Dropbox Developer Console. |
| `DROPBOX_REFRESH_TOKEN` | Dropbox OAuth refresh token. | Obtain by following Dropbox's OAuth flow. |

### User Credentials

| **Variable** | **Description** |
|-------------|----------------|
| `ADMIN_USERNAME` | Admin username for system access. |
| `ADMIN_PASSWORD` | Admin password for system access. |
| `NEXTCLOUD_USERNAME` | Username for Nextcloud authentication. |
| `NEXTCLOUD_PASSWORD` | Password for Nextcloud authentication. |

### IMAP Configuration

| **Variable** | **Description** |
|-------------|----------------|
| `IMAP1_USERNAME` | IMAP username for the first email account. |
| `IMAP1_PASSWORD` | IMAP password for the first email account. |
| `IMAP1_HOST` | Hostname of the first IMAP server. |
| `IMAP1_PORT` | IMAP server port (typically `993`). |
| `IMAP1_SSL` | Enable SSL (`true` or `false`). |
| `IMAP1_POLL_INTERVAL_MINUTES` | Polling interval for IMAP server. |
| `IMAP1_DELETE_AFTER_PROCESS` | Delete emails after processing (`true` or `false`). |

### Additional Services

| **Variable** | **Description** |
|-------------|----------------|
| `GOTENBERG_URL` | URL for Gotenberg PDF processing. |

## Running as a Docker Container

This project includes a `docker-compose.yml` file that allows for easy deployment using Docker. The following services are defined:

- **API Service**: Runs the document processing API using `uvicorn`.
- **Worker Service**: Runs the Celery worker for handling document processing tasks.
- **Redis**: Used as a message broker for Celery.
- **Gotenberg**: Provides PDF processing capabilities.

### Running the Application with Docker Compose

1. **Ensure Docker and Docker Compose are installed**.
2. **Clone the repository and navigate to the directory**:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```
3. **Create and configure the `.env` file**.
4. **Start the services**:
   ```bash
   docker-compose up -d
   ```
5. The API will be available at `http://localhost:8000`.

### Services in `docker-compose.yml`

```yaml
services:
  api:
    image: christianlouis/document-processor:latest
    container_name: document_api
    working_dir: /workdir
    command: ["sh", "-c", "cd /app && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
    environment:
      - PYTHONPATH=/app
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - worker
    volumes:
      - /var/docparse/workdir:/workdir

  worker:
    image: christianlouis/document-processor:latest
    container_name: document_worker
    working_dir: /workdir
    command: ["celery", "-A", "app.celery_worker", "worker", "-B", "--loglevel=info", "-Q", "document_processor,default,celery"]
    env_file:
      - .env
    environment:
      - PYTHONPATH=/app
    depends_on:
      - redis
      - gotenberg
    volumes:
      - /var/docparse/workdir:/workdir

  gotenberg:
    image: gotenberg/gotenberg:latest
    container_name: gotenberg

  redis:
    image: redis:alpine
    container_name: document_redis
    restart: always
```

## To-Do List

- Refactor AWS-related code to Azure.
- Remove unnecessary environment variables.
- Make upload targets configurable.
- Remove S3 upload functionality.

