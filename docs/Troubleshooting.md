# Troubleshooting Guide

This document provides solutions to common problems encountered when using DocuElevate.

## Common Issues

### Application Won't Start

#### Symptoms
- Docker containers exit immediately
- Web interface not accessible
- Error logs show startup failures

#### Possible Solutions
1. **Check environment variables**
   ```bash
   docker-compose config
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

### Document Upload Fails

#### Symptoms
- Error messages during upload
- Files appear to upload but aren't processed
- Browser console errors

#### Possible Solutions
1. **Check file size limits**
   - Default maximum file size is 100MB
   - Adjust `client_max_body_size` in your reverse proxy configuration

2. **Verify storage space**
   ```bash
   df -h
   ```
   Ensure there's sufficient disk space available.

3. **Check worker process**
   ```bash
   docker-compose logs worker
   ```
   Verify the Celery worker is running and processing tasks.

### OCR or Text Extraction Issues

#### Symptoms
- Documents upload but text isn't extracted
- Poor quality text extraction
- API errors related to Azure services

#### Possible Solutions
1. **Verify API credentials**
   Check the Azure Document Intelligence API key and endpoint in your `.env` file.

2. **Check document quality**
   - Ensure documents are clearly scanned
   - Try preprocessing images to improve quality before upload

3. **Test API connectivity**
   ```bash
   curl -X GET -H "Ocp-Apim-Subscription-Key: YOUR_KEY" "YOUR_ENDPOINT"
   ```
   Ensure the API is accessible from your server.

### Email Integration Problems

#### Symptoms
- Email attachments aren't being processed
- IMAP connection errors in logs
- Authentication failures

#### Possible Solutions
1. **Verify IMAP settings**
   Check host, port, username, and password in your configuration.

2. **Test IMAP connectivity**
   ```bash
   telnet mail.example.com 993
   ```
   Ensure the IMAP server is accessible.

3. **Enable less secure apps**
   For Gmail and some providers, you may need to enable access for less secure apps or use app-specific passwords.

4. **Check firewall settings**
   Ensure your server can make outbound connections to the mail server.

### Storage Integration Issues

#### Symptoms
- Files aren't appearing in Dropbox/Nextcloud/Paperless
- Authentication errors in logs
- API rate limiting errors

#### Possible Solutions
1. **Verify API credentials**
   Double-check all API keys, tokens, and secrets.

2. **Check access permissions**
   Ensure the application has write permissions to the specified folders.

3. **Refresh tokens**
   For OAuth-based services like Dropbox, try generating new refresh tokens.

4. **Examine detailed logs**
   ```bash
   docker-compose logs worker | grep -i dropbox
   ```
   Look for specific error messages related to the service.

## Database Issues

#### Symptoms
- Application errors related to database connections
- Missing or corrupt data
- Slow performance

#### Possible Solutions
1. **Check database connection string**
   Verify the `DATABASE_URL` variable in your `.env` file.

2. **Inspect database integrity**
   ```bash
   sqlite3 database.db "PRAGMA integrity_check;"
   ```
   (For SQLite databases)

3. **Perform database migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   ```
   Ensure the database schema is up-to-date.

## Authentication Problems

#### Symptoms
- Unable to log in
- Redirect loops during authentication
- OAuth errors

#### Possible Solutions
1. **Verify Authentik configuration**
   Check client ID, client secret, and configuration URL.

2. **Check callback URLs**
   Ensure the redirect URIs are correctly configured in your OAuth provider.

3. **Clear browser cookies and cache**
   Authentication issues can sometimes be resolved by clearing browser data.

## Getting Additional Help

If you continue to experience issues after trying these solutions:

1. **Check the logs** for detailed error messages
   ```bash
   docker-compose logs --tail=100
   ```

2. **Open an issue** on the [GitHub repository](https://github.com/christianlouis/document-processor/issues)

3. **Contact the developer** via the information provided on the About page
