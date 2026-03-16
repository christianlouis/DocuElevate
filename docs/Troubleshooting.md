# Troubleshooting Guide

This document provides solutions to common problems encountered when using DocuElevate.

> **Tip:** For configuration-specific issues, see also the [Configuration Troubleshooting](ConfigurationTroubleshooting.md) guide.

## Common Issues

### Application Won't Start

#### Symptoms
- Docker containers exit immediately
- Web interface not accessible
- Error logs show startup failures

#### Possible Solutions
1. **Check environment variables**
   ```bash
   docker compose config
   ```
   Ensure all required variables are set properly in your `.env` file.

2. **Verify permissions**
   ```bash
   ls -la /path/to/workdir
   ```
   Make sure the application has write permissions to the working directory.

3. **Check port availability**
   ```bash
   netstat -tuln | grep 8000
   ```
   Ensure the port isn't already in use by another application.

4. **Check Redis connectivity**
   ```bash
   docker compose logs redis
   ```
   Ensure Redis is running — both the API server and Celery worker depend on it.

5. **Check database migrations**
   ```bash
   docker compose exec api alembic upgrade head
   ```
   Ensure the database schema is up-to-date.

### Document Upload Fails

#### Symptoms
- Error messages during upload
- Files appear to upload but aren't processed
- Browser console errors

#### Possible Solutions
1. **Check file size limits**
   - Default maximum file size is 1 GB (`MAX_UPLOAD_SIZE`)
   - Individual file limit: `MAX_SINGLE_FILE_SIZE` (default: same as `MAX_UPLOAD_SIZE`)
   - If using a reverse proxy, adjust `client_max_body_size` (Nginx) or equivalent

2. **Verify storage space**
   ```bash
   df -h
   ```
   Ensure there's sufficient disk space on the workdir volume.

3. **Check worker process**
   ```bash
   docker compose logs worker
   ```
   Verify the Celery worker is running and processing tasks.

4. **Check upload quota**
   If multi-user mode and subscriptions are enabled, verify the user hasn't exceeded their daily upload limit (`DEFAULT_DAILY_UPLOAD_LIMIT`).

### OCR or Text Extraction Issues

#### Symptoms
- Documents upload but text isn't extracted
- Poor quality text extraction
- API errors related to OCR services

#### Possible Solutions
1. **Verify the configured OCR provider**
   Check which provider is set via the `OCR_PROVIDER` environment variable (defaults to Azure Document Intelligence).

2. **Verify API credentials**
   Check the credentials for your configured OCR provider in your `.env` file:
   - **Azure**: `AZURE_DI_KEY` and `AZURE_DI_ENDPOINT`
   - **Tesseract**: No credentials required (local), but ensure `TESSERACT_LANGUAGES` is set
   - **EasyOCR**: No credentials required (local)
   - **Mistral**: `MISTRAL_OCR_API_KEY`
   - **Google Document AI**: `GOOGLE_DOCAI_PROJECT_ID`, `GOOGLE_DOCAI_LOCATION`, `GOOGLE_DOCAI_PROCESSOR_ID`
   - **AWS Textract**: `AWS_TEXTRACT_ACCESS_KEY_ID`, `AWS_TEXTRACT_SECRET_ACCESS_KEY`, `AWS_TEXTRACT_REGION`

3. **Check document quality**
   - Ensure documents are clearly scanned
   - Try preprocessing images to improve quality before upload

4. **Try multi-provider OCR**
   Configure `OCR_PROVIDERS` (comma-separated list) with a merge strategy (`OCR_MERGE_STRATEGY`: `ai_merge`, `longest`, or `primary`) for better results.

### Email Integration Problems

#### Symptoms
- Email attachments aren't being processed
- IMAP connection errors in logs
- Authentication failures

#### Possible Solutions
1. **Verify IMAP settings**
   Check host, port, username, and password for `IMAP1_*` / `IMAP2_*` in your configuration.

2. **Test IMAP connectivity**
   ```bash
   docker compose exec api python -c "import imaplib; m = imaplib.IMAP4_SSL('mail.example.com', 993); print('OK')"
   ```
   Ensure the IMAP server is accessible from the container.

3. **Check for app-specific passwords**
   For Gmail and some providers, you must use app-specific passwords instead of your account password.

4. **Check firewall settings**
   Ensure your server can make outbound connections to the mail server on port 993 (IMAP SSL).

5. **Check attachment filter**
   If only certain attachments are expected, verify `IMAP_ATTACHMENT_FILTER` is set correctly (`documents_only` or `all`).

### Storage Integration Issues

#### Symptoms
- Files aren't appearing in configured storage destinations
- Authentication errors in logs
- API rate limiting errors

#### Possible Solutions
1. **Verify API credentials**
   Double-check all API keys, tokens, and secrets for the relevant service.

2. **Check access permissions**
   Ensure the application has write permissions to the specified folders/buckets.

3. **Refresh tokens**
   For OAuth-based services like Dropbox, Google Drive, and OneDrive, try re-authorizing through the integration setup pages.

4. **Examine detailed logs**
   ```bash
   docker compose logs worker | grep -i "upload_to"
   ```
   Look for specific error messages related to the storage service.

5. **Check integration status**
   Visit the **Integrations** page in the web UI to verify the connection status of each configured storage backend.

## Search Issues

### Symptoms
- Search returns no results or incomplete results
- Search page shows an error

### Possible Solutions
1. **Check Meilisearch is running**
   ```bash
   docker compose logs meilisearch
   ```
   Ensure the Meilisearch container is healthy and accepting connections.

2. **Verify Meilisearch URL**
   Check `MEILISEARCH_URL` in your `.env` file (default: `http://meilisearch:7700`).

3. **Rebuild the search index**
   If documents are missing from search results, reprocessing them will re-index their content.

## Pipeline & Routing Issues

### Symptoms
- Documents are not processed according to pipeline steps
- Routing rules don't match expected documents

### Possible Solutions
1. **Verify pipeline assignment**
   On the file detail page, check which pipeline (if any) is assigned. The system pipeline applies to all documents by default.

2. **Test routing rules**
   Use the **Evaluate** button on the Routing Rules page to test whether a rule matches a specific document.

3. **Check step ordering**
   Pipeline steps execute in order — ensure OCR comes before metadata extraction if the AI step depends on extracted text.

## Database Issues

### Symptoms
- Application errors related to database connections
- Missing or corrupt data
- Slow performance

### Possible Solutions
1. **Check database connection string**
   Verify the `DATABASE_URL` variable in your `.env` file.

2. **Inspect database integrity**
   For SQLite:
   ```bash
   sqlite3 database.db "PRAGMA integrity_check;"
   ```
   For PostgreSQL (recommended for production):
   ```bash
   docker compose exec api python -c "from app.database import engine; print(engine.url)"
   ```

3. **Perform database migrations**
   ```bash
   docker compose exec api alembic upgrade head
   ```
   Ensure the database schema is up-to-date.

4. **Consider PostgreSQL for production**
   SQLite is suitable for small deployments, but PostgreSQL is recommended for multi-user production environments. See the [Database Configuration Guide](DatabaseConfiguration.md).

## Authentication Problems

### Symptoms
- Unable to log in
- Redirect loops during authentication
- OAuth errors

### Possible Solutions
1. **Verify OAuth/OIDC configuration**
   Check client ID, client secret, and configuration URL for your identity provider.

2. **Check callback URLs**
   Ensure the redirect URIs are correctly configured in your OAuth provider. The callback URL is typically `https://your-domain/auth/callback`.

3. **Clear browser cookies and cache**
   Authentication issues can sometimes be resolved by clearing browser data.

4. **Check social login credentials**
   If using social login (Google, Microsoft, Apple, Dropbox), verify the corresponding `SOCIAL_AUTH_*` environment variables.

5. **Verify `EXTERNAL_HOSTNAME`**
   The `EXTERNAL_HOSTNAME` setting must match the domain users access DocuElevate from — OAuth redirect URLs depend on it.

## Mobile App Issues

### Symptoms
- Can't connect to DocuElevate from the mobile app
- Push notifications not received
- Login fails

### Possible Solutions
1. **Verify the server URL**
   Ensure the mobile app is configured with the correct DocuElevate server URL (including `https://`).

2. **Check API token**
   Generate a fresh API token from the web UI (Profile → API Tokens) and enter it in the mobile app settings.

3. **Check network connectivity**
   The mobile device must be able to reach your DocuElevate server. If using a private network, ensure VPN is connected.

4. **Push notifications**
   Push notifications require a valid Expo push token. Check the app settings and ensure notifications are enabled at the OS level.

See the [Mobile App Guide](MobileApp.md) for detailed setup instructions.

## CLI Issues

### Symptoms
- CLI commands fail with connection errors
- Authentication rejected

### Possible Solutions
1. **Verify URL and token**
   ```bash
   docuelevate --url https://your-instance --token de_xxx list
   ```
   Ensure the URL is correct (include the scheme) and the API token is valid.

2. **Check environment variables**
   The CLI reads `DOCUELEVATE_URL` and `DOCUELEVATE_API_TOKEN` from the environment. Verify they are exported.

3. **Test API directly**
   ```bash
   curl -H "Authorization: Bearer de_xxx" https://your-instance/api/files
   ```
   If this fails, the issue is with the server, not the CLI.

See the [CLI Guide](CLIGuide.md) for detailed usage.

## Performance Issues

### Symptoms
- Slow document processing
- High memory usage
- Queue backing up

### Possible Solutions
1. **Check worker concurrency**
   The Celery worker processes tasks in parallel. If the queue is backing up, consider scaling workers or adjusting concurrency.

2. **Enable batch throttling**
   Set `PROCESSALL_THROTTLE_THRESHOLD` and `PROCESSALL_THROTTLE_DELAY` to prevent overwhelming external APIs.

3. **Monitor the queue**
   Visit the **Admin → Queue** page to see pending, active, and failed tasks.

4. **Use PostgreSQL**
   SQLite can become a bottleneck under load. Migrate to PostgreSQL for better concurrent performance. See the [Database Configuration Guide](DatabaseConfiguration.md).

5. **Check Redis memory**
   ```bash
   docker compose exec redis redis-cli info memory
   ```
   Ensure Redis has sufficient memory for the task queue and cache.

## Getting Additional Help

If you continue to experience issues after trying these solutions:

1. **Check the logs** for detailed error messages:
   ```bash
   docker compose logs --tail=200
   ```

2. **Check the status page** at `/status` in the web UI for an overview of all service connections.

3. **Open an issue** on the [GitHub repository](https://github.com/christianlouis/DocuElevate/issues) with:
   - A description of the problem
   - Relevant log output
   - Your DocuElevate version (shown on the About page or in the `VERSION` file)

4. **Consult additional documentation**:
   - [Configuration Guide](ConfigurationGuide.md) — All environment variables
   - [Configuration Troubleshooting](ConfigurationTroubleshooting.md) — Configuration-specific issues
   - [Deployment Guide](DeploymentGuide.md) — Infrastructure and deployment
