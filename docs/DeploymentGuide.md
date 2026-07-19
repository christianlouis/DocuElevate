# Deployment Guide

This guide covers all supported deployment methods for DocuElevate.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Compose Deployment](#docker-compose-deployment) *(recommended for single-server)*
- [Kubernetes / Helm Deployment](#kubernetes--helm-deployment) *(recommended for production scale-out)*
- [Terraform Deployment](#terraform-deployment) *(declarative Kubernetes deployment)*
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
  - Dropbox, Google Drive, OneDrive, SharePoint, S3, or other storage APIs
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

### Step 2: Optionally provide operator-owned app credentials

The included Compose stack does **not** require a `.env` file. On first start it
creates a stable session secret and PostgreSQL password in a private Docker
volume. PostgreSQL, Redis, Gotenberg, Meilisearch and Qdrant are wired
automatically. The browser setup journey stores user choices and encrypted user
credentials in PostgreSQL, so workers pick up changes without editing every
container environment or restarting the stack.

Create `.env` only for credentials owned by the deployment operator, such as an
OAuth application client ID/secret or an AI-provider key that should be shared
by this installation:

```dotenv
# Optional examples — do not copy end-user OAuth tokens here.
OPENAI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Fresh installations store documents in the private `workdir-data` Docker named
volume. This avoids host-specific paths and makes a disposable Canary safe to
create and remove. Existing operators who intentionally want a host directory
can opt in without changing the Compose file:

```dotenv
DOCUELEVATE_WORKDIR=/srv/docuelevate/workdir
```

The containers themselves keep `/workdir` as their working directory, so a
legacy relative SQLite `DATABASE_URL` also continues to resolve against the
persisted document path during an upgrade.

Run a parallel disposable Canary on another local port without changing the
Compose file or colliding with an existing DocuElevate installation:

```bash
COMPOSE_PROJECT_NAME=docuelevate-canary-preprod \
DOCUELEVATE_PORT=8180 \
docker-compose up -d --build
```

The browser journey is then available at `http://localhost:8180`, and generated
callback/base URLs use the same port automatically. Remove the complete Canary,
including its generated bootstrap secret and all named data volumes, with:

```bash
COMPOSE_PROJECT_NAME=docuelevate-canary-preprod \
docker-compose down --volumes --remove-orphans
```

See the [Configuration Guide](ConfigurationGuide.md) for all optional settings.

### Step 3: Run with Docker Compose

```bash
docker-compose up -d
```

This starts:

| Service | Purpose |
|---------|---------|
| `api` | FastAPI web server (port 8000) |
| `worker` | Celery background task worker; handles document, research, and search-index queues by default |
| `beat` | Single Celery scheduler instance |
| `postgres` | Persistent application and user configuration database |
| `redis` | Ephemeral task broker for Celery |
| `gotenberg` | PDF conversion (LibreOffice headless) |
| `meilisearch` | Persistent full-text search index |
| `qdrant` | Persistent vector index for semantic retrieval |

The default stack deliberately uses one worker process for all queues so that a
fresh installation remains reliable on modest Docker hosts. For a larger or
busier installation, start the optional dedicated research and search workers:

```bash
docker-compose --profile scale up -d
```

The `scale` profile adds `knowledge-research-worker` and
`search-index-worker`; the default worker remains a safe fallback consumer for
both queues.

### Step 4: Verify the Installation

Access the web interface at `http://localhost:8000` and complete the deployment
wizard. Then create normal user accounts and follow the per-user onboarding
journey. Multi-user isolation is enabled by default and unowned documents are
not visible to ordinary users.

For automated or AI-operated installations, use the versioned
[Agentic setup](AgenticSetup.md) manifest. Its `plan` and `apply` commands use
the same database validation and encryption contract as the browser journey.

The API readiness endpoint is
`http://localhost:8000/api/diagnostic/healthz/ready`; optional API documentation
is available at `http://localhost:8000/docs` when enabled.

---

## Kubernetes / Helm Deployment

The Helm chart at `helm/docuelevate/` packages all components into a single, configurable release.  It supports:

- Multiple replicas for the API and Worker
- Horizontal Pod Autoscaling (HPA)
- Bundled or external Redis
- Persistent volumes for workdir and Meilisearch data
- Alembic database migration Job (pre-install/upgrade hook)
- TLS Ingress via any controller (nginx, Traefik, etc.)
- An optional, idempotent agentic setup Job after migrations
- Existing Kubernetes Secrets managed by 1Password / External Secrets

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

## Terraform Deployment

The reference Terraform configuration deploys this Helm chart and optionally
applies the same versioned setup manifest used by an automation agent. It does
not accept raw secrets: runtime and initial-setup credentials are referenced by
existing Kubernetes Secret names so they do not enter Terraform state.

See the [Terraform deployment guide](TerraformDeployment.md) and the runnable
[`examples/terraform/kubernetes`](https://github.com/christianlouis/DocuElevate/tree/main/examples/terraform/kubernetes) module.

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

DocuElevate is designed for horizontal scaling.  Both API and worker pods are stateless and can be scaled independently.

### Docker Compose

Scale workers (task processing) and API pods (request handling) independently:

```bash
docker compose up -d --scale worker=3 --scale api=2
```

> **Note:** The `beat` service (Celery Beat scheduler) must always run as exactly **one** instance.  Do not scale it.  It publishes periodic tasks to the Redis broker; workers pick them up.

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

The Helm chart deploys a separate **beat** pod (always 1 replica, `Recreate` strategy) so that scheduled tasks are never duplicated when workers scale.

---

## Monitoring

- **Docker Compose**: `docker-compose logs -f`, `docker stats`
- **Kubernetes**: `kubectl logs -l app.kubernetes.io/component=api -f`
- **Prometheus / Grafana**: Scrape the `/api/diagnostic/healthz/ready` endpoint for readiness; add custom metrics as needed.
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
