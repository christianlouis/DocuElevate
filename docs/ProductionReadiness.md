# Production Readiness Guide

This guide bridges the gap between a working local installation and a hardened, production-ready DocuElevate deployment.  Work through the checklist below — every item should be addressed before exposing DocuElevate to real users or sensitive documents.

## Table of Contents

- [Quick Checklist](#quick-checklist)
- [1. Database](#1-database)
- [2. Persistent Storage](#2-persistent-storage)
- [3. Security Hardening](#3-security-hardening)
- [4. TLS / HTTPS](#4-tls--https)
- [5. Authentication](#5-authentication)
- [6. Scaling Workers](#6-scaling-workers)
- [7. Monitoring & Alerting](#7-monitoring--alerting)
- [8. Backup Strategy](#8-backup-strategy)
- [9. Updates & Maintenance](#9-updates--maintenance)
- [10. Helm / Kubernetes Specifics](#10-helm--kubernetes-specifics)

---

## Quick Checklist

Use this checklist to track readiness before going live.

- [ ] **Database** — PostgreSQL configured; SQLite is not used in production
- [ ] **Migrations** — `alembic upgrade head` runs cleanly on every deploy
- [ ] **Persistent storage** — workdir volume is mounted on durable, backed-up storage
- [ ] **TLS** — All traffic served over HTTPS; HTTP redirects to HTTPS
- [ ] **Session secret** — `SESSION_SECRET` is a random 32-byte (64-hex-char) value, not a placeholder
- [ ] **Admin password** — Strong password set; default placeholder removed
- [ ] **Auth enabled** — `AUTH_ENABLED=true`
- [ ] **Security headers** — Configured at the reverse proxy or via `SECURITY_HEADERS_ENABLED=true`
- [ ] **Rate limiting** — `RATE_LIMITING_ENABLED=true` (default)
- [ ] **Redis** — Running and accessible only from internal network
- [ ] **Meilisearch** — Running and accessible only from internal network
- [ ] **Worker replicas** — At least 2 workers configured for redundancy
- [ ] **Monitoring** — `/api/health` polled by uptime checker
- [ ] **Backups** — Automated backup of database, workdir, and Meilisearch data
- [ ] **Log retention** — Logs shipped to a persistent store or aggregator
- [ ] **Secrets management** — API keys not committed to source control

---

## 1. Database

### SQLite → PostgreSQL Migration

SQLite is the default database and is suitable only for **development or single-node, low-traffic setups**.  For any multi-replica deployment or meaningful production load, use PostgreSQL.

```bash
DATABASE_URL=postgresql://docuelevate:strongpassword@postgres-host:5432/docuelevate
```

See the [Database Configuration Guide](DatabaseConfiguration.md) for detailed setup instructions, migration steps, and optimization tips.

### Alembic Migrations

Always run database migrations on every deploy **before** new application code starts serving traffic:

```bash
alembic upgrade head
```

- **Docker Compose**: Add a one-shot `migrate` service that runs before `api` and `worker`:

  ```yaml
  migrate:
    image: ghcr.io/christianlouis/docuelevate:latest
    command: alembic upgrade head
    env_file: .env
    depends_on:
      - redis
  ```

- **Helm / Kubernetes**: The Helm chart includes a pre-install/pre-upgrade Job hook that runs `alembic upgrade head` automatically before pods are updated.

---

## 2. Persistent Storage

The `WORKDIR` directory (`/workdir` by default) is where documents are staged during processing.  **This must be backed by persistent, durable storage.**

### Docker Compose

Map a named volume or a host path:

```yaml
services:
  api:
    volumes:
      - docuelevate_workdir:/workdir
  worker:
    volumes:
      - docuelevate_workdir:/workdir   # Same volume — both services share it

volumes:
  docuelevate_workdir:
    driver: local
```

For production, replace `driver: local` with an NFS or other network-backed volume driver so data survives host failures.

### Kubernetes

Use a `ReadWriteMany` (RWX) PersistentVolumeClaim when running multiple replicas:

```yaml
workdir:
  persistence:
    enabled: true
    accessMode: ReadWriteMany   # Required for multi-replica
    size: 50Gi
    storageClass: "nfs-client"  # Or your cluster's RWX storage class
```

Single-replica clusters can use `ReadWriteOnce`.

---

## 3. Security Hardening

### Session Secret

Generate a strong, unique secret and set it as `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# or
openssl rand -hex 32
```

This value **must be at least 32 characters** and must not be a known placeholder.  Rotating it invalidates all active sessions.

### HTTP Security Headers

DocuElevate's built-in security headers are **disabled by default** because most production deployments sit behind a reverse proxy that already adds them.

**Option A** — Let your reverse proxy add headers (recommended):

- See the Nginx and Traefik examples in the [Deployment Guide](DeploymentGuide.md#security-headers).

**Option B** — Enable built-in headers (only if no reverse proxy):

```bash
SECURITY_HEADERS_ENABLED=true
```

Recommended headers to configure at the proxy level:

| Header | Recommended Value |
|--------|-------------------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | See CSP notes below |

#### Content-Security-Policy Notes

DocuElevate's frontend uses Tailwind CSS loaded from CDN in development mode.  In production, ensure your CSP allows loading scripts and styles from your configured static file origin.  A starting point:

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
```

Audit and tighten this policy for your specific deployment.

### Rate Limiting

Rate limiting is enabled by default and requires Redis.  Verify it is active:

```bash
RATE_LIMITING_ENABLED=true   # default — ensure not overridden to false
REDIS_URL=redis://redis:6379/0
```

See the [Configuration Guide — Rate Limiting](ConfigurationGuide.md#rate-limiting) for per-endpoint tuning.

### Secrets Management

- **Never commit `.env` files** containing real secrets to source control.
- For Kubernetes, use an external secret manager (HashiCorp Vault, External Secrets Operator, Sealed Secrets) and reference secrets by name in Helm values rather than embedding them.
- Rotate API keys, the session secret, and database credentials on a regular schedule. See the [Credential Rotation Guide](CredentialRotationGuide.md).

### File Upload Limits

Set appropriate upload size limits to prevent resource exhaustion:

```bash
MAX_UPLOAD_SIZE=104857600       # 100 MB — adjust for your use case
MAX_REQUEST_BODY_SIZE=1048576   # 1 MB for non-file requests (default)
```

---

## 4. TLS / HTTPS

**All production traffic must be served over HTTPS.**

### Docker Compose with Traefik

```yaml
services:
  api:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.docuelevate.rule=Host(`docuelevate.example.com`)"
      - "traefik.http.routers.docuelevate.entrypoints=websecure"
      - "traefik.http.routers.docuelevate.tls.certresolver=letsencrypt"
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name docuelevate.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name docuelevate.example.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

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

### Kubernetes (Helm)

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "1g"
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

---

## 5. Authentication

Enable authentication and choose an auth method appropriate for your organization.

```bash
AUTH_ENABLED=true
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-password>
SESSION_SECRET=<min-32-char-random-string>
```

For SSO/OIDC (Authentik, Keycloak, Auth0, etc.) see the [Authentication Setup Guide](AuthenticationSetup.md).

**Best practices:**

- Use OIDC/SSO for team deployments to centralize access control.
- Enforce strong password policies or delegate password management to your identity provider.
- Set an appropriate session timeout (handled by the identity provider for OIDC, or by session middleware for basic auth).

---

## 6. Scaling Workers

### Docker Compose

Use the `deploy.replicas` setting (requires Docker Swarm mode) or simply run multiple workers:

```yaml
worker:
  deploy:
    replicas: 3
```

Or scale after deployment:

```bash
docker-compose up -d --scale worker=3
```

Each worker processes tasks from the Celery queue independently.  Ensure the shared `workdir` volume is accessible from all worker containers.

### Kubernetes (Helm)

```yaml
worker:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 75
```

### Worker Queue Tuning

Celery workers process three queues with different priorities:

| Queue | Purpose |
|-------|---------|
| `document_processor` | Main document processing tasks (OCR, conversion) |
| `default` | Metadata extraction, storage uploads |
| `celery` | Built-in Celery management tasks |

To dedicate workers to specific queues in high-volume deployments:

```bash
# High-priority worker — document processing only
celery -A app.celery_worker worker -Q document_processor --concurrency=4

# General worker — everything else
celery -A app.celery_worker worker -Q default,celery --concurrency=2
```

---

## 7. Monitoring & Alerting

### Health Check Endpoint

DocuElevate exposes `/api/health` for readiness probing.  Configure your uptime monitor to poll this endpoint:

```bash
curl http://docuelevate.example.com/api/health
# Expected: {"status": "ok", ...}
```

Set `UPTIME_KUMA_URL` to your Uptime Kuma push URL for heartbeat monitoring:

```bash
UPTIME_KUMA_URL=https://uptime.example.com/api/push/abc123
```

### Prometheus / Grafana

Scrape the `/api/health` endpoint or add a custom Prometheus exporter.  Useful metrics to track:

- Number of documents processed per hour
- Queue length (via Redis `LLEN` on Celery queues)
- Worker concurrency and CPU utilization
- API request latency (p50, p95, p99)

### Log Aggregation

- **Docker Compose**: Use the `logging` driver to ship to Loki, Fluentd, or CloudWatch:

  ```yaml
  services:
    api:
      logging:
        driver: "json-file"
        options:
          max-size: "50m"
          max-file: "5"
  ```

- **Kubernetes**: Logs are written to stdout/stderr and can be captured by your cluster's log aggregator (Fluentd, Vector, Promtail).

---

## 8. Backup Strategy

Back up all three data stores regularly:

### Database

**PostgreSQL:**

```bash
pg_dump -h postgres-host -U docuelevate docuelevate > backup_$(date +%Y%m%d).sql
```

Automate with a cron job or your cloud provider's managed backup feature.

**SQLite** (development only):

```bash
cp app/database.db backup_$(date +%Y%m%d).db
```

### Workdir Volume

The `WORKDIR` directory contains original uploads and processed documents.  Use your volume provider's snapshot feature or rsync to a secondary location:

```bash
rsync -av /workdir/ /backup/workdir/
```

### Meilisearch Data

Meilisearch stores its index in the directory specified by `MEILI_DB_PATH` (default `/meili_data`).  Snapshot it regularly or use [Meilisearch's dump feature](https://www.meilisearch.com/docs/reference/api/dumps):

```bash
curl -X POST http://localhost:7700/dumps \
  -H "Authorization: Bearer $MEILISEARCH_API_KEY"
```

### Configuration / Secrets

Back up your `.env` file or Helm values file to a **secure, encrypted** store (e.g., a password manager or secrets vault).  Do not commit it to source control.

---

## 9. Updates & Maintenance

### Docker Compose

```bash
git pull
docker-compose pull
docker-compose down && docker-compose up -d
```

The `alembic upgrade head` command is run automatically if you include the `migrate` service (see [Database](#1-database)).

### Helm / Kubernetes

```bash
helm upgrade docuelevate ./helm/docuelevate \
  --namespace docuelevate \
  -f my-values.yaml
```

The Helm chart's pre-upgrade hook runs `alembic upgrade head` before new pods start.

### Keep Dependencies Updated

```bash
pip install --upgrade -r requirements.txt
safety check   # Scan for known CVEs
```

Enable [GitHub Dependabot](https://docs.github.com/en/code-security/dependabot) or similar automated dependency update tooling.

---

## 10. Helm / Kubernetes Specifics

For a dedicated Kubernetes deployment guide, including architecture diagrams, PVC configuration, HPA, and ingress examples, see:

- [Deployment Guide — Kubernetes / Helm](DeploymentGuide.md#kubernetes--helm-deployment)

**Additional production recommendations for Kubernetes:**

- **Pod Disruption Budgets (PDB)**: Ensure at least one API pod is always available during node maintenance.

  ```yaml
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: docuelevate-api-pdb
  spec:
    minAvailable: 1
    selector:
      matchLabels:
        app.kubernetes.io/component: api
  ```

- **Resource Requests & Limits**: Set CPU/memory requests and limits on all containers to ensure the scheduler can place pods correctly.

  ```yaml
  api:
    resources:
      requests:
        cpu: "250m"
        memory: "512Mi"
      limits:
        cpu: "1000m"
        memory: "2Gi"
  worker:
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "2000m"
        memory: "4Gi"
  ```

- **Network Policies**: Restrict traffic so that Redis and Meilisearch are reachable only from DocuElevate pods, not from the internet or other namespaces.

- **Image Pull Policy**: Use `IfNotPresent` in production with pinned image tags (not `latest`) for reproducible deployments.

- **Liveness & Readiness Probes**: Already configured in the Helm chart via `/api/health`.  Verify they are tuned to your startup time.
