# Scheduled Jobs

DocuElevate includes an admin-managed **Scheduled Jobs** system that runs
recurring maintenance and processing tasks automatically via Celery Beat.

All jobs are visible and configurable through the admin UI at
**Admin → Scheduled Jobs** (`/admin/scheduled-jobs`).

---

## Overview

Scheduled jobs replace the need to run manual batch operations. Each job:

- Runs automatically on its configured cron or interval schedule.
- Can be **enabled** or **disabled** without restarting the worker.
- Can be triggered **immediately** with the *Run Now* button.
- Reports its last-run time, status (`success`, `failed`, `running`), and
  a short detail message back to the UI.

> **Note:** Schedule changes (cron expressions, interval values, enable/disable
> toggles) are persisted to the database immediately. However, Celery Beat
> reads the schedule only at worker startup — so changes take effect after
> **restarting the Celery worker**.
> The *Run Now* button dispatches a job immediately and does **not** require
> a restart.

---

## Built-in Jobs

### 1. Process New Documents

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.process_new_documents` |
| **Default schedule** | Every hour (cron `0 */1 * * *`) |
| **Purpose** | Scans for documents that have been uploaded but never processed, then queues them through the full pipeline. |

A document is considered *new* when it has no `FileProcessingStep` rows
matching the core pipeline steps.  Only files whose `local_filename` still
exists on disk are queued; others are skipped and counted.

---

### 2. Reprocess Failed Documents

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.reprocess_failed_documents` |
| **Default schedule** | Every 6 hours (cron `30 */6 * * *`) |
| **Purpose** | Finds documents whose last processing step has status `failure` and re-queues them. Skips files that are currently in-progress. |

---

### 3. Clean Up Temporary Files

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.cleanup_temp_files` |
| **Default schedule** | Daily at 03:30 UTC (cron `30 3 * * *`) |
| **Purpose** | Removes stale files from `workdir/tmp`. Only files older than 24 hours that are not referenced by any active processing job are deleted. |

---

### 4. Expire Stale Shared Links

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.expire_shared_links` |
| **Default schedule** | Daily at 01:00 UTC (cron `0 1 * * *`) |
| **Purpose** | Marks shared document links as inactive when their `expires_at` timestamp has passed. |

Access is already blocked at request time, but this task keeps the management
UI counts and statuses accurate.

---

### 5. Prune Old Processing Logs

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.prune_processing_logs` |
| **Default schedule** | Weekly on Sunday at 04:00 UTC (cron `0 4 * * 0`) |
| **Purpose** | Deletes `processing_logs` and `settings_audit_log` rows older than 30 days to prevent unbounded table growth. |

---

### 6. Prune Old Notifications

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.prune_old_notifications` |
| **Default schedule** | Weekly on Sunday at 04:30 UTC (cron `30 4 * * 0`) |
| **Purpose** | Deletes *read* `in_app_notifications` rows older than 30 days. Unread notifications are never deleted. |

---

### 7. Backfill Missing AI Metadata

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.backfill_missing_metadata` |
| **Default schedule** | Every 6 hours (cron `0 */6 * * *`) |
| **Purpose** | Re-triggers AI metadata extraction for documents that have OCR text but no `ai_metadata`. Processes up to 50 documents per run. |

This is particularly useful when:
- An AI provider (OpenAI / Azure) was configured after documents were already
  ingested.
- A previous metadata extraction attempt failed.

---

### 8. Sync Search Index

| Field | Value |
|---|---|
| **Task** | `app.tasks.batch_tasks.sync_search_index` |
| **Default schedule** | Hourly (cron `15 */1 * * *`) |
| **Purpose** | Indexes documents in Meilisearch that have OCR text or AI metadata but are not yet present in the search index. Processes up to 100 documents per run. |

This is useful after:
- Enabling Meilisearch for the first time on an existing installation.
- Recovering from a Meilisearch index wipe or migration.

---

## Managing Schedules

### Editing a schedule

1. Navigate to **Admin → Scheduled Jobs**.
2. Click **Edit Schedule** on the job card.
3. Choose **Cron** or **Interval** and fill in the fields.
4. Click **Save Changes**.

**Restart the worker** for the new schedule to take effect:

```bash
# Docker Compose
docker compose restart worker

# Kubernetes
kubectl rollout restart deployment/docuelevate-worker
```

### Cron format

Cron expressions follow the standard 5-field format:

```
minute  hour  day-of-month  month  day-of-week
```

Examples:

| Expression | Meaning |
|---|---|
| `0 * * * *` | Every hour on the hour |
| `0 2 * * *` | Daily at 02:00 UTC |
| `30 4 * * 0` | Every Sunday at 04:30 UTC |
| `*/15 * * * *` | Every 15 minutes |

### Interval format

For interval schedules, provide the number of **seconds**:

| Seconds | Meaning |
|---|---|
| `60` | Every minute |
| `3600` | Every hour |
| `86400` | Every day |

The minimum interval is **60 seconds**.

---

## Enabling / Disabling a job

Click the toggle on the job card to enable or disable the job.  The change
is saved immediately, but the updated schedule only takes effect after the
worker restarts.

Disabling a job does **not** cancel an in-flight execution — it only prevents
Celery Beat from scheduling new executions.

---

## Run Now

Click **Run Now** on any job card to dispatch it immediately, regardless of
its schedule or enabled status.  The task is sent to the `default` Celery
queue and will be picked up by the next available worker.

The UI shows a spinner while the dispatch request is in-flight and displays
the Celery task ID on success.  Refresh the page after a few seconds to see
the updated last-run status.

---

## Adding custom jobs

Custom batch jobs can be added by:

1. Creating a new Celery task in `app/tasks/` (or any existing tasks module).
2. Adding a row to `DEFAULT_JOBS` in `app/api/scheduled_jobs.py`.
3. Running the app — the new job will be seeded automatically on startup.

The task function should call `_update_job_status(job_name, status, detail)`
at the end of its execution so the admin UI reflects the outcome.

---

## Architecture notes

- **Seeding**: Default jobs are seeded into the `scheduled_jobs` database
  table when the FastAPI application starts up (via the lifespan handler in
  `app/main.py`).  Seeding is idempotent — re-running does not create
  duplicate rows.
- **Beat integration**: `app/celery_worker.py` calls `_load_db_scheduled_jobs()`
  at import time to extend `celery.conf.beat_schedule` with enabled DB jobs.
  Static hardcoded entries always take precedence over DB entries with the
  same key.
- **Status tracking**: Each task calls `_update_job_status()` in
  `app/tasks/batch_tasks.py` to persist `last_run_at`, `last_run_status`, and
  `last_run_detail` back to the `scheduled_jobs` table.
