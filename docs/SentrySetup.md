# Sentry Integration

DocuElevate ships with first-class support for [Sentry](https://sentry.io) — an open-source observability platform that provides real-time error tracking and performance monitoring.

When a **Sentry DSN** is configured, every unhandled exception in the FastAPI web process and Celery worker is automatically captured and sent to your Sentry project.  The **Sentry Browser SDK** is also injected into every rendered page, capturing client-side JavaScript errors, browser performance transactions, and (optionally) session replays.  Together these give you full-stack, end-to-end visibility into your deployment.

---

## Quick Start

1. **Create a Sentry project** at <https://sentry.io> (or your self-hosted Sentry instance).  Choose the **Python** platform (the same project and DSN are used for both the server and browser SDKs).
2. Copy the **DSN** from *Project → Settings → Client Keys (DSN)*.  It looks like:
   ```
   https://<public_key>@o<org_id>.ingest.sentry.io/<project_id>
   ```
3. Set the DSN in your environment **or** via the **Settings → Observability** section of the DocuElevate admin UI:
   ```bash
   SENTRY_DSN=https://<public_key>@o<org_id>.ingest.sentry.io/<project_id>
   ```
4. Restart DocuElevate.  Sentry initialises automatically on startup — you will see a log line confirming activation.  The Sentry Browser SDK `<script>` tag is automatically injected into every rendered page.

---

## Environment Variables

### Server-side (Python SDK)

| Variable | Default | Description |
|---|---|---|
| `SENTRY_DSN` | *(empty)* | Sentry DSN URL.  **Required** to enable Sentry.  Leave unset to disable. |
| `SENTRY_ENVIRONMENT` | `production` | Environment label shown in the Sentry dashboard (`development`, `staging`, `production`, …). |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | Fraction of requests captured for performance tracing (0.0 – 1.0).  `0.0` disables tracing entirely. |
| `SENTRY_PROFILES_SAMPLE_RATE` | `0.0` | Fraction of profiled transactions sent to Sentry (0.0 – 1.0).  Only active when traces > 0. |
| `SENTRY_SEND_DEFAULT_PII` | `false` | Attach PII (IP addresses, user agents) to events.  Disable for GDPR / CCPA compliance. |

### Browser SDK (JavaScript)

The Sentry Browser SDK is loaded automatically on every rendered page when `SENTRY_DSN` is set.  The DSN is a *public* key in Sentry's security model and is intentionally embedded in client-side code.

| Variable | Default | Description |
|---|---|---|
| `SENTRY_JS_TRACES_SAMPLE_RATE` | `0.0` | Fraction of browser page-loads captured for client-side performance tracing (0.0 – 1.0). |
| `SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE` | `0.0` | Fraction of sessions recorded by [Sentry Session Replay](https://docs.sentry.io/product/session-replay/) (0.0 – 1.0). |
| `SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE` | `0.1` | Fraction of error sessions captured with session replay context (0.0 – 1.0). |

All variables can alternatively be managed through the **Settings → Observability** section of the DocuElevate admin UI.  Settings stored in the database are applied before Sentry initialises on every startup, so changes made via the UI take effect after a restart without requiring any changes to environment variables or `.env` files.

---

## Environment-Specific Configuration

### Development

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=1.0            # Capture every request during development
SENTRY_PROFILES_SAMPLE_RATE=1.0
SENTRY_SEND_DEFAULT_PII=true             # OK in dev; disable in production

SENTRY_JS_TRACES_SAMPLE_RATE=1.0         # Capture every browser navigation
SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE=1.0 # Record every session
SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE=1.0
```

### Staging

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=staging
SENTRY_TRACES_SAMPLE_RATE=0.5
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_DEFAULT_PII=false

SENTRY_JS_TRACES_SAMPLE_RATE=0.5
SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE=0.1
SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE=1.0
```

### Production

```bash
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1            # 10 % sampling keeps quota low
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_DEFAULT_PII=false            # Default — required for GDPR compliance

SENTRY_JS_TRACES_SAMPLE_RATE=0.1
SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE=0.0 # Disabled; rely on error-triggered replay
SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE=0.1
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
      SENTRY_JS_TRACES_SAMPLE_RATE: "0.1"
      SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE: "0.1"

  worker:
    environment:
      SENTRY_DSN: "https://<key>@o<org>.ingest.sentry.io/<project>"
      SENTRY_ENVIRONMENT: "production"
      SENTRY_TRACES_SAMPLE_RATE: "0.1"
```

> The `worker` service only needs server-side variables — the Browser SDK runs in the user's browser and is configured via the `api` service.

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
  - name: SENTRY_JS_TRACES_SAMPLE_RATE
    value: "0.1"
  - name: SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE
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

### Browser (JavaScript SDK)

- **Client-side errors** — unhandled JavaScript exceptions and Promise rejections are captured automatically with browser context (URL, user agent, breadcrumbs).
- **Browser performance** — page load, navigation, and resource timing data is captured as Sentry transactions when `SENTRY_JS_TRACES_SAMPLE_RATE > 0`.
- **Session Replay** — screen recordings of user sessions (or just sessions containing errors) can be captured when the relevant replay sample rates are set above `0.0`.  Replay data helps reproduce and diagnose hard-to-find UI bugs.

---

## Disabling Sentry

Simply leave `SENTRY_DSN` unset (or set it to an empty string).  Neither the Python SDK nor the Browser SDK `<script>` tag is loaded, and no data is sent.

---

## SDK Version

- **Server:** DocuElevate uses [`sentry-sdk`](https://pypi.org/project/sentry-sdk/) `>=2.20.0,<3.0.0` with the `fastapi`, `celery`, and `sqlalchemy` extras.
- **Browser:** The `bundle.tracing.replay.min.js` bundle from the Sentry Browser SDK **v10** is loaded from the official Sentry CDN (`browser.sentry-cdn.com`).  The version pin is in `frontend/templates/base.html`.

---

## Troubleshooting

### No events appear in Sentry

1. Verify the DSN is correct and the Sentry project is active.
2. Check the application logs for the `Sentry initialised` message at startup.  If it is absent, the DSN is not being read — confirm the environment variable name is `SENTRY_DSN`, or check the **Settings → Observability** section of the admin UI if you configured it there.
3. Test with `SENTRY_TRACES_SAMPLE_RATE=1.0` so that every request is sent.

### No browser errors in Sentry

1. Confirm `SENTRY_DSN` is set — the Browser SDK `<script>` tag is only injected when the DSN is non-empty.
2. Open browser DevTools → Network and verify that the Sentry CDN bundle (`bundle.tracing.replay.min.js`) loads successfully (HTTP 200).
3. Open DevTools → Console and run `window.Sentry` — it should be an object if the SDK loaded correctly.
4. Check that `SENTRY_JS_TRACES_SAMPLE_RATE` and replay rates are set to values > 0 if you expect performance / replay data (they default to `0.0`).

### `sentry-sdk` import error

```
sentry-sdk is not installed.
```

Run `pip install 'sentry-sdk[fastapi,celery,sqlalchemy]'` inside your container, or rebuild the Docker image.

### PII / GDPR concerns

By default `SENTRY_SEND_DEFAULT_PII=false`, which prevents IP addresses and user agents from being attached to server-side events.  Session Replay data may capture user interactions — review [Sentry's privacy documentation](https://docs.sentry.io/product/session-replay/privacy/) and your organisation's privacy policy before enabling replay.

### High Sentry quota usage

- Lower `SENTRY_TRACES_SAMPLE_RATE` (e.g. `0.05` for 5 %) or set it to `0.0` to disable server-side performance tracing.
- Set `SENTRY_JS_TRACES_SAMPLE_RATE=0.0` to disable browser performance tracing.
- Set `SENTRY_JS_REPLAY_SESSION_SAMPLE_RATE=0.0` and `SENTRY_JS_REPLAY_ON_ERROR_SAMPLE_RATE=0.0` to disable Session Replay entirely.

---

## Best Practices

- Use **separate Sentry projects** (or at least separate environments) for development, staging, and production so that noise from non-production environments does not pollute your production alerts.
- Configure **alert rules** in Sentry to notify your team (via email, Slack, PagerDuty, etc.) when error rates spike.
- Use **release tracking**: DocuElevate automatically sets `release` to the current `VERSION` string, enabling you to correlate errors with specific releases.
- Set up **performance baselines** using Sentry's Performance dashboard so that you can detect regressions after deployments.
- Review the [Sentry Python documentation](https://docs.sentry.io/platforms/python/) for advanced configuration options such as custom tags, user context, and scrubbing sensitive data.
- Review the [Sentry Browser SDK documentation](https://docs.sentry.io/platforms/javascript/) for advanced browser SDK configuration.

---

## Related Documentation

- [Configuration Guide](./ConfigurationGuide.md) — full list of environment variables
- [Deployment Guide](./DeploymentGuide.md) — Docker and Kubernetes deployment
- [Troubleshooting](./Troubleshooting.md) — general troubleshooting
