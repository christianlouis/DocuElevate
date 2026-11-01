# Durable browser imports

Large imports use a separate admission protocol under `/api/uploads`. Uploading
and processing have different completion states: HTTP **202 with `file_id` means
that the server has persisted the original and its database/outbox record**.
OCR, metadata extraction and delivery happen afterwards.

## Browser queue

`upload-bulk.js` streams a selection through bounded preflight windows. A Web
Worker reads each file in 1 MiB chunks, calculates SHA-256 and probes common magic
headers. Matching content within the selection shares an upload. A scoped server
preflight can also identify existing documents before bytes are transmitted.
The server independently verifies hashes and allowed content.

The root-scoped `/upload-queue-sw.js` stores queue metadata in IndexedDB. A
MessageChannel acknowledges committed transactions. Per-tab, renewable leases
coordinate transfers between tabs. No document bodies are copied into IndexedDB.
Queue metadata is partitioned by the authenticated upload owner.

After a reload, server records are reconciled by batch/client ID. Accepted files
are not uploaded again. For pending files, **select the original files again**;
name, length and modification time reconnect them to the saved client IDs, and
content is hashed again before transfer. Browsers do not preserve ordinary file
input access across reloads. Closing the browser pauses unaccepted transfers;
server-side processing continues. A Service Worker is event-driven, not a
permanent background process. Browser storage can still be cleared by the user
or browser; the persistent-storage request is best effort. See the
[Service Worker lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
and [persistent storage](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist).

The websocket carries capacity/status hints, not file contents. REST capacity
checks and paginated snapshots provide reconciliation after disconnection.
Capacity zero pauses transmission. Retries retain the original client ID so a
lost 202 response does not create a second document.

## Processing and provider budgets

Run the database migration before enabling this release. API and processing
workers must share durable `WORKDIR` storage; an ephemeral pod filesystem cannot
provide the acceptance guarantee. Preserve that volume in backup/recovery plans.
Run the Celery beat outbox recovery task as well as the workers. Redis priority
queues and worker prefetch of one let mail and small imports overtake bulk work
between pipeline tasks. Bulk provenance is carried through descendant tasks;
old documents receive higher priority when subsequent tasks are published.
The outbox dispatcher runs every five seconds and publishes at most ten items
per run. Admission caps outstanding work at 1,000 documents and the smaller of
10 GiB or ten times the configured per-file upload limit. These bounds limit
backlog growth independently of the provider budgets.

The transactional outbox provides at-least-once publication. A crash after
publishing a Celery task but before recording publication can execute processing
again for the same file ID; a deterministic task ID does not deduplicate Celery
execution. Upload replay prevents extra file records, but does not establish
exactly-once downstream processing.

Admission reservations are released when the existing pipeline records its
terminal delivery-handoff step, or an exhausted/non-retryable failure. A durable
one-time release marker prevents overlapping recovery jobs from releasing the
same reservation twice. Completion here does not certify
that every external destination has finished delivery; destination tasks retain
their existing retry and status handling.

Provider admission is shared in Redis, with separate request, estimated-token,
OCR-page and in-flight budgets per provider/model/credential fingerprint:

| Environment setting | Purpose |
| --- | --- |
| `PROVIDER_LIMITS_ENABLED` | Enable distributed upstream admission (default false) |
| `PROVIDER_LIMITS_RPM` | Requests in a rolling minute; zero disables this dimension |
| `PROVIDER_LIMITS_TPM` | Estimated tokens in a rolling minute |
| `PROVIDER_LIMITS_PAGES_PER_MINUTE` | Azure OCR document pages in a rolling minute |
| `PROVIDER_LIMITS_CONCURRENCY` | Calls in flight |
| `PROVIDER_LIMITS_LEASE_SECONDS` | Crash recovery timeout; must exceed maximum call duration |
| `PROVIDER_LIMITS_OVERRIDES` | JSON budgets by provider or `provider/model` |
| `PROVIDER_LIMITS_MAX_RETRIES` | Retry allowance for quota waits (default 20) |

Example: `PROVIDER_LIMITS_OVERRIDES={"openai":{"rpm":30,"concurrency":2},"azure_ocr":{"pages_per_minute":60,"concurrency":1}}`.
Use actual account/model quotas and leave headroom for applications outside this
installation. These settings do not discover provider quotas automatically.
Token counts are estimates, not provider billing measurements; shared quotas
across several models or external consumers need budgets divided accordingly.
A call releases concurrency when finished, but retains its minute usage. 429
cooldowns retain the longest observed `Retry-After`; Redis failure fails closed
when limits are enabled. SDK retries are disabled under admission control.

Monitor accepted-to-completed latency, admission rejections, disk free space,
outbox age/publish failures, provider 429s and worker throughput separately.
More parallel HTTP uploads cannot improve throughput when an upstream provider
is the bottleneck.

## Validation

Python tests cover acceptance/replay, outbox recovery and priority propagation.
`node --test frontend/static/js/upload-bulk.test.js` exercises real queue helpers
and SHA-256, including input larger than a worker chunk. Redis Lua integration
tests use `PROVIDER_LIMITS_TEST_REDIS_URL` (default localhost database 15); use a
dedicated disposable instance. Never point tests at production Redis.
