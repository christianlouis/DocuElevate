# Deployment Guide

This guide provides instructions for deploying DocuElevate in various environments.

## Prerequisites

- Docker and Docker Compose
- Access to required external services (if configured):
  - OpenAI API
  - Azure Document Intelligence
  - Dropbox API
  - Nextcloud instance
  - Paperless NGX instance
  - SMTP server (for email notifications)
  - IMAP server(s) (for email attachment processing)
  - Notification services (Discord, Telegram, etc. for system alerts)

## Docker Deployment

Docker is the recommended deployment method for DocuElevate.

### Step 1: Clone the Repository

```bash
git clone https://github.com/christianlouis/document-processor.git
cd document-processor
```

### Step 2: Configure Environment Variables

Create a `.env` file based on the example:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration settings. See the [Configuration Guide](ConfigurationGuide.md) for details.

### Step 3: Run with Docker Compose

```bash
docker-compose up -d
```

This will start:
- The DocuElevate API server
- A worker for background tasks
- Redis for message broker and result storage
- Gotenberg for PDF processing

### Step 4: Verify the Installation

Access the web interface at `http://localhost:8000` and the API documentation at `http://localhost:8000/docs`.

## Production Considerations

### Security Headers

DocuElevate includes built-in support for HTTP security headers to improve browser-side security. **These headers are disabled by default** since most deployments use a reverse proxy (Traefik, Nginx, etc.) that already adds these headers.

#### Supported Security Headers

- **Strict-Transport-Security (HSTS)**: Forces browsers to use HTTPS for all future requests
- **Content-Security-Policy (CSP)**: Controls which resources browsers are allowed to load
- **X-Frame-Options**: Prevents the page from being loaded in frames (clickjacking protection)
- **X-Content-Type-Options**: Prevents browsers from MIME-sniffing responses

#### Reverse Proxy Deployment (Traefik, Nginx, etc.) - DEFAULT

**Most deployments use a reverse proxy**, which is why security headers are disabled by default in DocuElevate. The reverse proxy should add these headers.

```bash
# In .env file (or omit - this is the default)
SECURITY_HEADERS_ENABLED=false
```

##### Traefik Configuration Example

Traefik can add security headers using middleware. Create a `docker-compose.yaml` with Traefik labels:

```yaml
services:
  api:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.docuelevate.rule=Host(`docuelevate.example.com`)"
      - "traefik.http.routers.docuelevate.entrypoints=websecure"
      - "traefik.http.routers.docuelevate.tls=true"
      - "traefik.http.routers.docuelevate.tls.certresolver=letsencrypt"
      # Security headers middleware
      - "traefik.http.routers.docuelevate.middlewares=security-headers@docker"
      - "traefik.http.middlewares.security-headers.headers.stsSeconds=31536000"
      - "traefik.http.middlewares.security-headers.headers.stsIncludeSubdomains=true"
      - "traefik.http.middlewares.security-headers.headers.contentSecurityPolicy=default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
      - "traefik.http.middlewares.security-headers.headers.customFrameOptionsValue=DENY"
      - "traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true"
```

Then set `SECURITY_HEADERS_ENABLED=false` in your `.env` file.

##### Nginx Configuration Example

Add security headers to your Nginx configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name docuelevate.example.com;

    # SSL configuration
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then keep `SECURITY_HEADERS_ENABLED=false` in your `.env` file (or omit it, as this is the default).

#### Direct Deployment (No Reverse Proxy)

If you're running DocuElevate **directly without a reverse proxy**, enable security headers:

```bash
# In .env file
SECURITY_HEADERS_ENABLED=true
```

You can also configure individual headers:

```bash
SECURITY_HEADER_HSTS_ENABLED=true
SECURITY_HEADER_CSP_ENABLED=true
SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED=true
SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS_ENABLED=true
```

**Note**: HSTS only works when serving content over HTTPS. If using HTTP for development, you can disable it:

```bash
SECURITY_HEADER_HSTS_ENABLED=false
```

#### Customizing Security Headers

If you enable security headers, you can customize individual header values in your `.env` file:

```bash
# Customize HSTS (e.g., shorter duration for testing)
SECURITY_HEADER_HSTS_VALUE="max-age=300"

# Customize CSP (e.g., allow specific external domains)
SECURITY_HEADER_CSP_VALUE="default-src 'self'; script-src 'self' https://cdn.example.com; style-src 'self' 'unsafe-inline';"

# Allow framing from same origin
SECURITY_HEADER_X_FRAME_OPTIONS_VALUE="SAMEORIGIN"
```

#### Security Considerations

1. **HSTS and HTTPS**: HSTS only works over HTTPS. Ensure you have a valid SSL certificate before enabling HSTS.
2. **CSP Testing**: The default CSP policy allows inline scripts and styles for compatibility. Test thoroughly before tightening.
3. **Content-Security-Policy**: The default policy allows `'unsafe-inline'` for scripts and styles for compatibility with Tailwind CSS and inline JavaScript. For stricter security, consider using nonces or hashes.
4. **X-Frame-Options**: Set to `DENY` by default. Change to `SAMEORIGIN` if you need to embed DocuElevate in iframes on the same domain.

See the [Configuration Guide](ConfigurationGuide.md) for all security header options.

### Reverse Proxy Setup

For production use, we recommend setting up a reverse proxy (like Nginx or Traefik) to handle HTTPS and domain routing:

```nginx
server {
    listen 80;
    server_name docuelevate.example.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Persistent Storage

The Docker setup uses volumes for persistent storage. For production, consider:

```yaml
volumes:
  - /path/to/persistent/storage:/workdir
```

### Security

1. **Always use HTTPS** in production
2. Enable authentication by setting `AUTH_ENABLED=true`
3. Use strong passwords for all services
4. Limit access to the Docker host
5. Regularly update the application and dependencies

## Scaling

For high-volume deployments:

1. Increase worker processes by adding more worker containers:

```yaml
worker:
  image: christianlouis/document-processor:latest
  deploy:
    replicas: 3
```

2. Consider using dedicated Redis and database servers
3. Monitor system performance and adjust resources as needed

## Monitoring

Monitor your DocuElevate deployment using:

- Docker's built-in logging: `docker-compose logs -f`
- Container metrics: `docker stats`
- External monitoring tools like Prometheus and Grafana

## Backup Procedures

Regularly back up the following:

1. The `/workdir` directory containing all processed documents
2. The database file (if using SQLite) or database contents (if using another DBMS)
3. The `.env` configuration file

## Updates

To update DocuElevate to a newer version:

```bash
# Pull the latest changes
git pull

# Pull the latest Docker images
docker-compose pull

# Restart the services
docker-compose down
docker-compose up -d
```

## Troubleshooting

See the [Troubleshooting](Troubleshooting.md) guide for common deployment issues and solutions.
