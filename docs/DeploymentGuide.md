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
