# Deployment Guide

This guide covers all supported deployment methods for DocuElevate.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Compose Deployment](#docker-compose-deployment) *(recommended for single-server)*
- [Kubernetes / Helm Deployment](#kubernetes--helm-deployment) *(recommended for production scale-out)*
- [Production Considerations](#production-considerations)
- [Scaling](#scaling)
- [Backup Procedures](#backup-procedures)
- [Updates](#updates)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Docker and Docker Compose **or** a Kubernetes cluster with Helm 3
- Access to required external services (if configured):
  - AI provider API key (OpenAI, Anthropic, Gemini, or other configured provider)
  - Azure Document Intelligence
  - Dropbox, Google Drive, OneDrive, S3, or other storage APIs
  - SMTP / IMAP server (for email processing)
  - Notification services (Discord, Telegram, etc.)

---

## Docker Compose Deployment

Docker Compose is the quickest way to run DocuElevate on a single server.

### Step 1: Clone the Repository

```bash
git clone https://github.com/christianlouis/DocuElevate.git
cd DocuElevate
```

### Step 2: Configure Environment Variables

```bash
cp .env.demo .env
```

Edit `.env` with your settings. See the [Configuration Guide](ConfigurationGuide.md) for all options.

### Step 3: Run with Docker Compose

```bash
docker-compose up -d
```

This starts:

| Service | Purpose |
|---------|---------|
| `api` | FastAPI web server (port 8000) |
| `worker` | Celery background task worker |
| `redis` | Message broker for Celery |
| `gotenberg` | PDF conversion (LibreOffice headless) |
| `meilisearch` | Full-text search engine (port 7700) |

### Step 4: Verify the Installation

Access the web interface at `http://localhost:8000` and the API docs at `http://localhost:8000/docs`.

---

## Kubernetes / Helm Deployment

The Helm chart at `helm/docuelevate/` packages all components into a single, configurable release.  It supports:

- Multiple replicas for the API and Worker
- Horizontal Pod Autoscaling (HPA)
- Bundled or external Redis
- Persistent volumes for workdir and Meilisearch data
- Alembic database migration Job (pre-install/upgrade hook)
- TLS Ingress via any controller (nginx, Traefik, etc.)

### Prerequisites

- Kubernetes 1.24+
- Helm 3.10+
- A storage class that supports **ReadWriteMany** (e.g. NFS, CephFS, Azure Files, EFS) for the shared workdir PVC when running multiple replicas.  Single-replica clusters can use `ReadWriteOnce`.
- A PostgreSQL database (strongly recommended over SQLite for multi-replica).

### Quick Start

```bash
# 1. Add the Bitnami chart repository (needed for bundled Redis)
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# 2. Update chart dependencies
helm dependency update ./helm/docuelevate

# 3. Install with a minimal values override
helm install docuelevate ./helm/docuelevate \
  --namespace docuelevate --create-namespace \
  --set secrets.DATABASE_URL="postgresql://user:pass@postgres:5432/docuelevate" \
  --set secrets.SESSION_SECRET="$(openssl rand -hex 32)" \
  --set secrets.OPENAI_API_KEY="sk-..." \
  --set secrets.AZURE_AI_KEY="..." \
  --set env.AZURE_ENDPOINT="https://my-resource.cognitiveservices.azure.com/" \
  --set env.EXTERNAL_HOSTNAME="docuelevate.example.com"
```

### Values Reference

The full list of configurable values is in [`helm/docuelevate/values.yaml`](../helm/docuelevate/values.yaml).  Key sections:

#### Container Image

```yaml
image:
  repository: ghcr.io/christianlouis/docuelevate
  tag: ""          # defaults to chart appVersion
  pullPolicy: IfNotPresent
```

#### Non-Secret Config (`env`)

```yaml
env:
  WORKDIR: /workdir
  AI_PROVIDER: openai
  OPENAI_MODEL: gpt-4o-mini
  AZURE_REGION: eastus
  AZURE_ENDPOINT: "https://my-resource.cognitiveservices.azure.com/"
  MEILISEARCH_URL: http://docuelevate-meilisearch:7700  # auto-resolved from service name
  ENABLE_SEARCH: "true"
  AUTH_ENABLED: "true"
  EXTERNAL_HOSTNAME: docuelevate.example.com
```

#### Secrets (`secrets`)

All secrets are stored in a Kubernetes `Secret` and injected as environment variables.

```yaml
secrets:
  DATABASE_URL: "postgresql://user:pass@postgres:5432/docuelevate"
  SESSION_SECRET: "<min-32-char-random-string>"
  OPENAI_API_KEY: "sk-..."
  AZURE_AI_KEY: "..."
  MEILISEARCH_API_KEY: ""   # leave blank for unauthenticated dev Meilisearch
  # Storage provider secrets ...
```

> **Tip:** In production use an external secret manager (Vault, ESO, Sealed Secrets) and reference the secret by name instead of embedding values in values.yaml.

#### Replicas & Autoscaling

```yaml
api:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8
    targetCPUUtilizationPercentage: 70

worker:
  replicaCount: 2
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 75
```

#### Shared Workdir PVC

```yaml
workdir:
  persistence:
    enabled: true
    accessMode: ReadWriteMany   # RWX required for multi-replica
    size: 20Gi
    storageClass: "nfs-client"  # or leave blank for cluster default
```

#### Ingress (nginx example)

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1g"
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: docuelevate.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: docuelevate-tls
      hosts:
        - docuelevate.example.com
```

#### External Redis

```yaml
redis:
  enabled: false          # disable bundled Redis

externalRedis:
  url: "redis://my-redis-host:6379/0"
```

#### Meilisearch

The bundled Meilisearch deployment is a single-replica, persistent StatefulSet-equivalent.  For production, consider [Meilisearch Cloud](https://www.meilisearch.com/cloud) and point `env.MEILISEARCH_URL` at it.

```yaml
meilisearch:
  enabled: true
  persistence:
    enabled: true
    size: 10Gi
```

### Upgrading

```bash
helm upgrade docuelevate ./helm/docuelevate \
  --namespace docuelevate \
  -f my-values.yaml
```

The pre-upgrade hook runs `alembic upgrade head` automatically before the new pods start.

### Uninstalling

```bash
helm uninstall docuelevate --namespace docuelevate
# PVCs are NOT deleted automatically — remove manually if desired:
kubectl delete pvc -l app.kubernetes.io/instance=docuelevate -n docuelevate
```

### Kubernetes Architecture Diagram

```
Internet
   │
   ▼
[Ingress / LoadBalancer]
   │
   ▼
[API Deployment] ─────── [Worker Deployment]
   │        │                │        │
   │        └── shared PVC ──┘        │
   │              (workdir)            │
   ▼                                  ▼
[Redis Service]              [Gotenberg Service]
   │
[Meilisearch Service]
```

---

## Production Considerations

### Database

SQLite is fine for development but **not recommended for multi-replica production** deployments because it cannot be shared safely across pods.  Use PostgreSQL:

```
DATABASE_URL=postgresql://docuelevate:secret@postgres-host:5432/docuelevate
```

### Security Headers

DocuElevate's built-in security headers are **disabled by default** since most deployments use a reverse proxy that already adds them.

```bash
# Enable only if running without a reverse proxy
SECURITY_HEADERS_ENABLED=true
```

#### Traefik (Docker Compose) example

```yaml
services:
  api:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.docuelevate.rule=Host(`docuelevate.example.com`)"
      - "traefik.http.routers.docuelevate.entrypoints=websecure"
      - "traefik.http.routers.docuelevate.tls.certresolver=letsencrypt"
      - "traefik.http.routers.docuelevate.middlewares=security-headers@docker"
      - "traefik.http.middlewares.security-headers.headers.stsSeconds=31536000"
      - "traefik.http.middlewares.security-headers.headers.stsIncludeSubdomains=true"
      - "traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true"
      - "traefik.http.middlewares.security-headers.headers.customFrameOptionsValue=DENY"
```

#### Nginx example

```nginx
server {
    listen 443 ssl http2;
    server_name docuelevate.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 1g;
    }
}
```

### Storage

```yaml
# Docker Compose
volumes:
  - /path/to/persistent/storage:/workdir

# Helm — use a RWX storage class for multi-replica
workdir:
  persistence:
    size: 20Gi
    accessMode: ReadWriteMany
    storageClass: "nfs-client"
```

### General Security Checklist

1. **Always use HTTPS** in production
2. Set `AUTH_ENABLED=true` and use a strong `SESSION_SECRET`
3. Rotate API keys and secrets regularly — see the [Credential Rotation Guide](CredentialRotationGuide.md)
4. Limit network access to Redis and Meilisearch (both should be internal-only)
5. Regularly update the container image to pick up dependency patches

---

## Scaling

### Docker Compose

Add more worker containers:

```yaml
worker:
  deploy:
    replicas: 3
```

### Kubernetes / Helm

Enable HPA:

```yaml
api:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8

worker:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
```

---

## Monitoring

- **Docker Compose**: `docker-compose logs -f`, `docker stats`
- **Kubernetes**: `kubectl logs -l app.kubernetes.io/component=api -f`
- **Prometheus / Grafana**: Scrape the `/api/health` endpoint for readiness; add custom metrics as needed.
- **Uptime Kuma**: Set `UPTIME_KUMA_URL` to your push URL for heartbeat monitoring.

---

## Backup Procedures

Regularly back up:

1. The `/workdir` volume (all processed documents and originals)
2. The database (PostgreSQL `pg_dump` or SQLite file)
3. The Meilisearch data directory (`/meili_data`)
4. Your `.env` / Helm values file (store securely, it contains secrets)

---

## Updates

### Docker Compose

```bash
git pull
docker-compose pull
docker-compose down && docker-compose up -d
```

### Helm

```bash
helm repo update          # if using a hosted chart repository
helm upgrade docuelevate ./helm/docuelevate --namespace docuelevate -f my-values.yaml
```

The migration Job runs automatically on every `helm upgrade`.

---

## Troubleshooting

See the [Troubleshooting Guide](Troubleshooting.md) for common issues and solutions.
