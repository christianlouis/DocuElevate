# Kubernetes Deployment Guide

This guide covers deploying DocuElevate on Kubernetes using the provided Helm chart.

> **Quick reference:** For a side-by-side comparison of Docker Compose vs. Kubernetes deployment options, see the [Deployment Guide](DeploymentGuide.md).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Helm Values Reference](#helm-values-reference)
- [Storage Configuration](#storage-configuration)
- [Database Setup](#database-setup)
- [Secrets Management](#secrets-management)
- [Ingress & TLS](#ingress--tls)
- [Scaling & Autoscaling](#scaling--autoscaling)
- [Monitoring & Health Checks](#monitoring--health-checks)
- [Upgrades](#upgrades)
- [Uninstalling](#uninstalling)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| Kubernetes | 1.24 | 1.27+ recommended |
| Helm | 3.10 | |
| Storage Class (RWX) | — | Required for multi-replica; NFS, CephFS, Azure Files, EFS, etc. |
| PostgreSQL | 14+ | Strongly recommended; SQLite not safe for multi-replica |
| cert-manager | 1.12+ | Optional, for automated TLS via Let's Encrypt |

The Helm chart is located in the repository at `helm/docuelevate/`.

---

## Architecture Overview

```
Internet
   │
   ▼
[Ingress Controller]         ← TLS termination, host routing
   │
   ▼
[API Deployment]             ← FastAPI web server (multiple replicas)
   │      │
   │      └── [Shared PVC: /workdir]  ← ReadWriteMany volume
   │                │
   ▼                ▼
[Worker Deployment]          ← Celery background task workers (multiple replicas)
   │
   ├── [Redis Service]       ← Celery broker & result backend
   ├── [Gotenberg Service]   ← Document → PDF conversion
   └── [Meilisearch Service] ← Full-text search index
```

All services communicate over the cluster's internal network.  **Redis and Meilisearch must not be exposed outside the cluster.**

---

## Quick Start

### 1. Add Chart Dependencies

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
helm dependency update ./helm/docuelevate
```

### 2. Create a Values Override File

Create `my-values.yaml` (never commit this file — it contains secrets):

```yaml
env:
  EXTERNAL_HOSTNAME: docuelevate.example.com
  AZURE_ENDPOINT: "https://my-resource.cognitiveservices.azure.com/"
  AUTH_ENABLED: "true"

secrets:
  DATABASE_URL: "postgresql://docuelevate:strongpassword@postgres:5432/docuelevate"
  SESSION_SECRET: "<run: openssl rand -hex 32>"
  OPENAI_API_KEY: "sk-..."
  AZURE_AI_KEY: "..."

ingress:
  enabled: true
  className: nginx
  annotations:
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

### 3. Install the Chart

```bash
helm install docuelevate ./helm/docuelevate \
  --namespace docuelevate \
  --create-namespace \
  -f my-values.yaml
```

### 4. Verify the Deployment

```bash
kubectl get pods -n docuelevate
kubectl get svc -n docuelevate
kubectl get ingress -n docuelevate
```

Wait until all pods report `Running` and `1/1` (or `2/2` for multi-container pods).

---

## Helm Values Reference

The complete list of values is in [`helm/docuelevate/values.yaml`](../helm/docuelevate/values.yaml).  Key sections are summarized below.

### Container Image

```yaml
image:
  repository: ghcr.io/christianlouis/docuelevate
  tag: ""            # Defaults to chart appVersion; pin a specific tag in production
  pullPolicy: IfNotPresent
```

### Non-Secret Configuration (`env`)

```yaml
env:
  WORKDIR: /workdir
  AI_PROVIDER: openai
  OPENAI_MODEL: gpt-4o-mini
  AZURE_REGION: eastus
  AZURE_ENDPOINT: "https://my-resource.cognitiveservices.azure.com/"
  MEILISEARCH_URL: http://docuelevate-meilisearch:7700
  ENABLE_SEARCH: "true"
  AUTH_ENABLED: "true"
  EXTERNAL_HOSTNAME: docuelevate.example.com
  ALLOW_FILE_DELETE: "true"
```

### Secrets (`secrets`)

Secrets are stored in a Kubernetes `Secret` resource and injected as environment variables.

```yaml
secrets:
  DATABASE_URL: "postgresql://user:pass@postgres:5432/docuelevate"
  SESSION_SECRET: "<min-32-char-random-string>"
  OPENAI_API_KEY: "sk-..."
  AZURE_AI_KEY: "..."
  MEILISEARCH_API_KEY: ""      # Leave blank for unauthenticated local Meilisearch
  DROPBOX_APP_KEY: ""          # Optional — only if using Dropbox
  DROPBOX_APP_SECRET: ""
  GOOGLE_DRIVE_CLIENT_ID: ""   # Optional — only if using Google Drive
  GOOGLE_DRIVE_CLIENT_SECRET: ""
```

> **Tip:** In production, manage secrets with an external secret manager.  See [Secrets Management](#secrets-management).

---

## Storage Configuration

### Shared Workdir PVC

Both the API and Worker pods need to access the same `/workdir` volume for document staging.

```yaml
workdir:
  persistence:
    enabled: true
    accessMode: ReadWriteMany   # Required when api.replicaCount > 1 or worker.replicaCount > 1
    size: 50Gi
    storageClass: "nfs-client"  # Must support ReadWriteMany
```

**Single-replica clusters** can use `ReadWriteOnce`:

```yaml
workdir:
  persistence:
    accessMode: ReadWriteOnce
    size: 20Gi
    storageClass: ""   # Use cluster default
```

### Meilisearch Data

Meilisearch data is stored in a separate PVC:

```yaml
meilisearch:
  enabled: true
  persistence:
    enabled: true
    size: 10Gi
    storageClass: ""   # Use cluster default (RWO is fine here)
```

---

## Database Setup

For production, deploy PostgreSQL externally (managed service or a separate Helm release) and set `DATABASE_URL` in `secrets`.

### External PostgreSQL

```yaml
secrets:
  DATABASE_URL: "postgresql://docuelevate:password@my-postgres-host:5432/docuelevate?sslmode=require"
```

### Bundled PostgreSQL (Not Recommended for Production)

If you must use a bundled PostgreSQL instance, add it as a Helm dependency or deploy the Bitnami PostgreSQL chart in the same namespace.  The Helm chart does not bundle PostgreSQL by default.

### Database Migrations

A Kubernetes Job is included in the Helm chart as a pre-install and pre-upgrade hook.  It runs `alembic upgrade head` before any pods are updated:

```yaml
# This is automatic — no additional configuration needed
```

To run migrations manually:

```bash
kubectl run alembic-upgrade \
  --image=ghcr.io/christianlouis/docuelevate:latest \
  --namespace=docuelevate \
  --restart=Never \
  --env-from=secret/docuelevate-secrets \
  -- alembic upgrade head
```

See the [Database Configuration Guide](DatabaseConfiguration.md) for detailed database setup.

---

## Secrets Management

### Option 1: Values File (Basic)

Store secrets in `my-values.yaml` and **never commit it to source control**.  Pass it with `-f my-values.yaml` at install/upgrade time.

### Option 2: External Secrets Operator (Recommended)

Use [External Secrets Operator](https://external-secrets.io/) with HashiCorp Vault, AWS Secrets Manager, or Azure Key Vault:

```yaml
# ExternalSecret resource
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: docuelevate-secrets
  namespace: docuelevate
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: docuelevate-secrets
    creationPolicy: Owner
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key: docuelevate/production
        property: database_url
    - secretKey: SESSION_SECRET
      remoteRef:
        key: docuelevate/production
        property: session_secret
    - secretKey: OPENAI_API_KEY
      remoteRef:
        key: docuelevate/production
        property: openai_api_key
```

Then reference the pre-existing secret in Helm values:

```yaml
existingSecret: docuelevate-secrets   # Use this key if the chart supports it
```

### Option 3: Sealed Secrets

Use [Bitnami Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) to encrypt secrets before committing to Git.

---

## Ingress & TLS

### Nginx Ingress

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "1g"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
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

### Traefik Ingress

```yaml
ingress:
  enabled: true
  className: traefik
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
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

### Manual TLS Secret

If you manage TLS certificates outside cert-manager:

```bash
kubectl create secret tls docuelevate-tls \
  --cert=path/to/fullchain.pem \
  --key=path/to/privkey.pem \
  --namespace=docuelevate
```

---

## Scaling & Autoscaling

### Manual Scaling

```yaml
api:
  replicaCount: 3

worker:
  replicaCount: 4
```

### Horizontal Pod Autoscaler

```yaml
api:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 8
    targetCPUUtilizationPercentage: 70

worker:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 75
```

> **Prerequisite:** The Kubernetes Metrics Server must be installed in your cluster for HPA to function.

### Resource Requests and Limits

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

### External Redis

Disable the bundled Redis and point at an external instance for greater resilience:

```yaml
redis:
  enabled: false

externalRedis:
  url: "redis://my-redis-cluster:6379/0"
```

---

## Monitoring & Health Checks

### Kubernetes Probes

The Helm chart configures liveness and readiness probes on the API pods via `/api/health`.  Default settings:

```yaml
api:
  livenessProbe:
    httpGet:
      path: /api/health
      port: 8000
    initialDelaySeconds: 30
    periodSeconds: 30
  readinessProbe:
    httpGet:
      path: /api/health
      port: 8000
    initialDelaySeconds: 10
    periodSeconds: 10
```

### Prometheus Scraping

Add annotations to expose metrics (if using a Prometheus-compatible exporter):

```yaml
api:
  podAnnotations:
    prometheus.io/scrape: "true"
    prometheus.io/path: "/metrics"
    prometheus.io/port: "8000"
```

### Pod Disruption Budget

Ensure availability during node maintenance:

```bash
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: docuelevate-api-pdb
  namespace: docuelevate
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app.kubernetes.io/component: api
      app.kubernetes.io/instance: docuelevate
EOF
```

---

## Upgrades

```bash
helm upgrade docuelevate ./helm/docuelevate \
  --namespace docuelevate \
  -f my-values.yaml
```

The pre-upgrade hook automatically runs `alembic upgrade head` before new pods are created.  Upgrades are rolling by default — old pods continue to serve traffic until new pods are ready.

**Image tag pinning (recommended):**

```yaml
image:
  tag: "1.5.2"   # Pin a specific version tag instead of using 'latest'
```

---

## Uninstalling

```bash
helm uninstall docuelevate --namespace docuelevate
```

> **Warning:** Persistent Volume Claims are **NOT** deleted automatically.  Remove them manually if you no longer need the data:

```bash
kubectl delete pvc -l app.kubernetes.io/instance=docuelevate -n docuelevate
```

To delete the namespace entirely:

```bash
kubectl delete namespace docuelevate
```

---

## Troubleshooting

### Pods Stuck in `Pending`

```bash
kubectl describe pod <pod-name> -n docuelevate
```

Common causes:
- No available nodes with sufficient CPU/memory — adjust resource requests or add nodes.
- PVC cannot be bound — verify the StorageClass supports the required `accessMode`.
- Image pull failure — check `imagePullSecrets` and network access to the container registry.

### Pods in `CrashLoopBackOff`

```bash
kubectl logs <pod-name> -n docuelevate --previous
```

Common causes:
- `DATABASE_URL` is wrong or the database is unreachable.
- `SESSION_SECRET` is missing or too short.
- Required environment variable not set in `secrets` or `env`.

### Migration Job Fails

```bash
kubectl logs job/docuelevate-migrate -n docuelevate
```

Resolve the database connection issue then re-run the job or run the upgrade again.

### Workdir Volume Mount Errors

Ensure the StorageClass supports `ReadWriteMany` when `api.replicaCount > 1` or `worker.replicaCount > 1`.  Check your storage provisioner documentation.

For more help, see the [Troubleshooting Guide](Troubleshooting.md).
