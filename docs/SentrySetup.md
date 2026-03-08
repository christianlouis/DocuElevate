# Sentry Integration

DocuElevate ships with first-class support for [Sentry](https://sentry.io) — an open-source observability platform that provides real-time error tracking and performance monitoring.

When a **Sentry DSN** is configured, every unhandled exception in the FastAPI web process and Celery worker is automatically captured and sent to your Sentry project.  Performance transactions (request traces, database queries, background task durations) are also recorded, giving you end-to-end visibility into your deployment.

---

## Quick Start

1. **Create a Sentry project** at <https://sentry.io> (or your self-hosted Sentry instance).  Choose the **Python** platform.
2. Copy the **DSN** from *Project → Settings → Client Keys (DSN)*.  It looks like:
   ```
   https://<public_key>@o<org_id>.ingest.sentry.io/<project_id>
   ```
3. Set the DSN in your environment:
   ```bash
   SENTRY_DSN=https://<public_key>@o<org_id>.ingest.sentry.io/<project_id>
   ```
4. Restart DocuElevate.  Sentry initialises automatically on startup — you will see a log line confirming activation.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SENTRY_DSN` | *(empty)* | Sentry DSN URL.  **Required** to enable Sentry.  Leave unset to disable. |
| `SENTRY_ENVIRONMENT` | `production` | Environment label shown in the Sentry dashboard (`development`, `staging`, `production`, …). |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Fraction of requests captured for performance tracing (0.0 – 1.0).  `0.0` disables tracing entirely. |
| `SENTRY_PROFILES_SAMPLE_RATE` | `0.0` | Fraction of profiled transactions sent to Sentry (0.0 – 1.0).  Only active when traces > 0. |
| `SENTRY_SEND_DEFAULT_PII` | `false` | Attach PII (IP addresses, user agents) to events.  Disable for GDPR / CCPA compliance. |

All variables can alternatively be managed through the **Settings → Observability** section of the DocuElevate admin UI.

---

## Environment-Specific Configuration

### Development

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=1.0   # Capture every request during development
SENTRY_PROFILES_SAMPLE_RATE=1.0
SENTRY_SEND_DEFAULT_PII=true    # OK in dev; disable in production
```

### Staging

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=staging
SENTRY_TRACES_SAMPLE_RATE=0.5
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_DEFAULT_PII=false
```

### Production

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1   # 10 % sampling keeps quota low
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_DEFAULT_PII=false   # Default — required for GDPR compliance
```

---

## Docker Compose

Add the variables to your `docker-compose.yaml` service definitions or to a separate `.env` file that Docker Compose reads automatically:

```yaml
services:
  api:
    environment:
      SENTRY_DSN: "https://<key>@o<org>.ingest.sentry.io/<project>"
      SENTRY_ENVIRONMENT: "production"
      SENTRY_TRACES_SAMPLE_RATE: "0.1"

  worker:
    environment:
      SENTRY_DSN: "https://<key>@o<org>.ingest.sentry.io/<project>"
      SENTRY_ENVIRONMENT: "production"
      SENTRY_TRACES_SAMPLE_RATE: "0.1"
```

---

## Kubernetes

Store the DSN as a Kubernetes Secret:

```bash
kubectl create secret generic docuelevate-sentry \
  --from-literal=SENTRY_DSN="https://<key>@o<org>.ingest.sentry.io/<project>"
```

Then reference it in your Deployment manifest:

```yaml
envFrom:
  - secretRef:
      name: docuelevate-sentry
env:
  - name: SENTRY_ENVIRONMENT
    value: production
  - name: SENTRY_TRACES_SAMPLE_RATE
    value: "0.1"
```

---

## What Is Monitored

### FastAPI (web server)

- **Unhandled exceptions** — every 5xx error is automatically captured with the full stack trace and request context.
- **Performance transactions** — each HTTP request becomes a Sentry transaction, showing time spent in route handlers, middleware, and database calls.
- **Database queries** — individual SQL queries are recorded as child spans via the `SqlalchemyIntegration`.

### Celery (background worker)

- **Task failures** — any exception raised inside a Celery task is captured, including the task name, ID, and arguments.
- **Task performance** — each task execution is a Sentry transaction, letting you identify slow or failing pipelines.
- **Beat task monitoring** — the `CeleryIntegration(monitor_beat_tasks=True)` option tracks whether scheduled tasks run on time (requires [Sentry Crons](https://docs.sentry.io/product/crons/)).

### Logging integration

Log messages at `ERROR` level and above are automatically forwarded to Sentry as events.  Messages at `INFO` level are recorded as breadcrumbs (contextual trail leading up to an error).

---

## Disabling Sentry

Simply leave `SENTRY_DSN` unset (or set it to an empty string).  The SDK is never initialised and no data is sent.

---

## SDK Version

DocuElevate uses [`sentry-sdk`](https://pypi.org/project/sentry-sdk/) `>=2.20.0,<3.0.0` with the `fastapi`, `celery`, and `sqlalchemy` extras.

---

## Troubleshooting

### No events appear in Sentry

1. Verify the DSN is correct and the Sentry project is active.
2. Check the application logs for the `Sentry initialised` message at startup.  If it is absent, the DSN is not being read — confirm the environment variable name is `SENTRY_DSN`.
3. Test with `SENTRY_TRACES_SAMPLE_RATE=1.0` so that every request is sent.

### `sentry-sdk` import error

```
sentry-sdk is not installed.
```

Run `pip install 'sentry-sdk[fastapi,celery,sqlalchemy]'` inside your container, or rebuild the Docker image.

### PII / GDPR concerns

By default `SENTRY_SEND_DEFAULT_PII=false`, which prevents IP addresses and user agents from being attached to events.  Review Sentry's [data management documentation](https://docs.sentry.io/product/data-management-settings/) and your organisation's privacy policy before enabling PII.

### High Sentry quota usage

Lower `SENTRY_TRACES_SAMPLE_RATE` (e.g. `0.05` for 5 %) or set it to `0.0` to disable performance tracing entirely.

---

## Best Practices

- Use **separate Sentry projects** (or at least separate environments) for development, staging, and production so that noise from non-production environments does not pollute your production alerts.
- Configure **alert rules** in Sentry to notify your team (via email, Slack, PagerDuty, etc.) when error rates spike.
- Use **release tracking**: DocuElevate automatically sets `release` to the current `VERSION` string, enabling you to correlate errors with specific releases.
- Set up **performance baselines** using Sentry's Performance dashboard so that you can detect regressions after deployments.
- Review the [Sentry Python documentation](https://docs.sentry.io/platforms/python/) for advanced configuration options such as custom tags, user context, and scrubbing sensitive data.

---

## Related Documentation

- [Configuration Guide](./ConfigurationGuide.md) — full list of environment variables
- [Deployment Guide](./DeploymentGuide.md) — Docker and Kubernetes deployment
- [Troubleshooting](./Troubleshooting.md) — general troubleshooting
