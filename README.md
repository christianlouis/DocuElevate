# Document Processing System

## Overview

This project automates the handling, extraction, and processing of documents using a variety of services, including:

- **OpenAI** for metadata extraction and text refinement.  
- **Dropbox** and **Nextcloud** for file storage and uploads.  
- **Paperless NGX** for document indexing and management.  
- **Azure Document Intelligence** (optional) for OCR on PDFs (replacing Textract).  
- **Gotenberg** for file-to-PDF conversions.  
- **AWS S3** (currently implemented but may be removed in the future).  

It is designed for flexibility and configurability through environment variables, making it easily customizable for different workflows. The system can fetch documents from multiple IMAP mailboxes, process them (OCR, metadata extraction, PDF conversion), and store them in the desired destinations.

## Features

- **Document Upload & Storage**:  
  - Manual uploads (via API) to S3, or direct uploads to Dropbox/Nextcloud/Paperless.  
- **OCR Processing (Azure)**:  
  - Extract text from scanned PDFs using Azure Document Intelligence.  
- **Metadata Extraction (OpenAI)**:  
  - Use GPT to classify, label, or otherwise enrich the text with structured metadata.  
- **PDF Conversion (Gotenberg)**:  
  - Convert non-PDF attachments (e.g., Word docs, images) into PDFs.  
- **Document Management (Paperless NGX)**:  
  - Store processed documents and metadata in a Paperless NGX instance.  
- **IMAP Integration**:  
  - Fetch documents from multiple mailboxes (including Gmail) and automatically enqueue them for processing.

## Environment Variables

The `.env` file drives all configuration. This table breaks down key variables—some are optional, depending on which services you actually use.

### Core Settings

| **Variable**           | **Description**                                          | **Example**                    |
|------------------------|----------------------------------------------------------|--------------------------------|
| `DATABASE_URL`         | Path/URL to the SQLite database (or other SQL backend). | `sqlite:///./app/database.db`  |
| `REDIS_URL`            | URL for Redis, used by Celery for broker & result store. | `redis://redis:6379/0`         |
| `WORKDIR`              | Working directory for the application.                  | `/workdir`                     |
| `GOTENBERG_URL`        | Gotenberg PDF processing URL.                           | `http://gotenberg:3000`        |

### IMAP Configuration (Multiple Mailboxes)

| **Variable**                  | **Description**                                              | **Example**       |
|-------------------------------|--------------------------------------------------------------|-------------------|
| `IMAP1_HOST`                  | Hostname for first IMAP server.                             | `mail.example.com`|
| `IMAP1_PORT`                  | Port number (usually `993`).                                | `993`             |
| `IMAP1_USERNAME`              | IMAP login (first mailbox).                                 | `user@example.com`|
| `IMAP1_PASSWORD`              | IMAP password (first mailbox).                              | `*******`         |
| `IMAP1_SSL`                   | Use SSL (`true`/`false`).                                   | `true`            |
| `IMAP1_POLL_INTERVAL_MINUTES` | Frequency in minutes to poll for new mail.                  | `5`               |
| `IMAP1_DELETE_AFTER_PROCESS`  | Delete emails after processing (`true`/`false`).            | `false`           |
| `IMAP2_HOST`                  | Hostname for second IMAP server (optional).                 | `imap.gmail.com`  |
| `IMAP2_PORT`                  | Port number for second mailbox.                             | `993`             |
| `IMAP2_USERNAME`              | IMAP login for second mailbox.                              | `you@gmail.com`   |
| `IMAP2_PASSWORD`              | IMAP password for second mailbox.                           | `*******`         |
| `IMAP2_SSL`                   | Use SSL for second mailbox (`true`/`false`).                | `true`            |
| `IMAP2_POLL_INTERVAL_MINUTES` | Frequency in minutes to poll second mailbox.                | `10`              |
| `IMAP2_DELETE_AFTER_PROCESS`  | Delete emails after processing (`true`/`false`) for mailbox.| `false`           |

### OpenAI & Azure Document Intelligence

| **Variable**          | **Description**                                                    | **How to Obtain**                                                                                              |
|-----------------------|--------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `OPENAI_API_KEY`      | API key for OpenAI services (used for metadata extraction/refinement). | [OpenAI platform](https://platform.openai.com/account/api-keys)                                                |
| `AZURE_AI_KEY`        | Azure Document Intelligence key (for OCR).                        | [Azure Portal](https://portal.azure.com/)                                                                        |
| `AZURE_REGION`        | Azure region of your Document Intelligence instance.              | e.g. `eastus`, `westeurope`                                                                                     |
| `AZURE_ENDPOINT`      | Endpoint URL for Document Intelligence.                           | e.g. `https://<yourendpoint>.cognitiveservices.azure.com/`                                                      |

### Paperless NGX

| **Variable**                  | **Description**                                     |
|-------------------------------|-----------------------------------------------------|
| `PAPERLESS_NGX_API_TOKEN`     | API token for Paperless NGX.                       |
| `PAPERLESS_HOST`              | Root URL for Paperless NGX (e.g. `https://paperless.example.com`). |

### Dropbox

| **Variable**            | **Description**                                  | **How to Obtain**                                                                 |
|-------------------------|--------------------------------------------------|------------------------------------------------------------------------------------|
| `DROPBOX_APP_KEY`       | Dropbox API app key.                             | [Dropbox Developer Console](https://www.dropbox.com/developers/apps/create)        |
| `DROPBOX_APP_SECRET`    | Dropbox API app secret.                          | [Dropbox Developer Console](https://www.dropbox.com/developers/apps/create)        |
| `DROPBOX_REFRESH_TOKEN` | OAuth2 refresh token for Dropbox.                | Follow Dropbox OAuth flow to retrieve                                              |
| `DROPBOX_FOLDER`        | Default folder path for Dropbox uploads.         | e.g. `"/Documents/Uploads"`                                                        |

### Nextcloud

| **Variable**            | **Description**                                               |
|-------------------------|---------------------------------------------------------------|
| `NEXTCLOUD_UPLOAD_URL`  | Nextcloud WebDAV URL (e.g. `https://nc.example.com/remote.php/dav/files/<USERNAME>`). |
| `NEXTCLOUD_USERNAME`    | Nextcloud login username.                                    |
| `NEXTCLOUD_PASSWORD`    | Nextcloud login password.                                    |
| `NEXTCLOUD_FOLDER`      | Destination folder in Nextcloud (e.g. `"/Documents/Uploads"`). |

### AWS S3

| **Variable**           | **Description**                                               |
|------------------------|---------------------------------------------------------------|
| `AWS_ACCESS_KEY_ID`    | AWS Access Key (used for S3 upload).                          |
| `AWS_SECRET_ACCESS_KEY`| AWS Secret Key (used for S3 upload).                          |
| `AWS_REGION`           | AWS region for S3.                                           |
| `S3_BUCKET_NAME`       | Default S3 bucket name if using S3 upload.                    |

### General Admin Credentials

| **Variable**       | **Description**                             |
|--------------------|---------------------------------------------|
| `ADMIN_USERNAME`   | Admin username for system access.           |
| `ADMIN_PASSWORD`   | Admin password for system access.           |

## Running as a Docker Container

This project uses Celery (with Redis) for asynchronous task management and Gotenberg for PDF conversion. The `docker-compose.yml` file defines these services:

- **API Service**: Runs the FastAPI application via `uvicorn`.
- **Worker Service**: Runs the Celery worker for processing tasks (PDF conversions, OCR, etc.).
- **Redis**: Provides the message broker & result backend for Celery.
- **Gotenberg**: Offers PDF conversion capabilities.

### Running the Application with Docker Compose

1. **Install Docker and Docker Compose** on your system.  
2. **Clone the repository** and navigate into it:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```
3. **Create and configure the `.env` file**:
   - Fill in the variables from the tables above.  
   - (At minimum, you need `DATABASE_URL`, `REDIS_URL`, `WORKDIR`, plus whichever service creds you plan to use.)
4. **Launch the services**:
   ```bash
   docker-compose up -d
   ```
5. The API will be available at **`http://localhost:8000`**.

### Services in `docker-compose.yml`

Below is the default structure (simplified):

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

- **Refactor AWS-related code** to rely on Azure or remove if no longer needed.  
- **Remove unnecessary environment variables** once final service usage is determined.  
- **Make upload targets configurable** (e.g., easily choose only Dropbox, Nextcloud, or Paperless).  
- **Potentially remove or consolidate S3 upload code** if Azure is the preferred cloud option.  

---

**Questions or Issues?**  
- Feel free to open an issue or pull request.  
- For local testing or development, use `docker-compose up` and watch the logs via `docker-compose logs -f`.  
- Ensure your `.env` aligns with the environment variables listed above. If you see unexpected errors, check for typos or missing values.