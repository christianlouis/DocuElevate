# IMAP backlog recovery

Polling covers the selected mailbox regardless of message age or read state.
Gmail uses All Mail; other providers use INBOX. UIDVALIDITY and a durable UID
ledger identify messages. The historical cursor advances only past messages
that have a durable ledger entry. Historical work, recent arrivals and retries
share the polling budget so one class cannot monopolize it.

## Operating modes

The durable discovery/download pipeline is opt-in. The application default is
`IMAP_PIPELINE_ENABLED=false`; the production deployment enables it only after
the schema migration and its consumers are ready. In enabled mode, the
existing `imap_polling` worker performs metadata-only discovery and records
candidate IDs in PostgreSQL. A publisher sends those durable candidates to
Redis in two lanes: `imap_download_new` (one reserved worker) and
`imap_download_backlog` (two workers). The lanes use the existing secrets and
shared `/workdir` staging; they do not change normal document, OCR, AI, or
upload concurrency/rate limits.

Metadata scanning is not gated on the document-processing queue. Redis is a
dispatch mechanism, not the source of truth: an empty queue can mean that a
worker has claimed work or that the scanner is between publication steps.
Measure the PostgreSQL ledger and lane consumers together. The configured
pipeline uses metadata batches of 750, download batches of 25, 900-second
leases, and a 7,200-message/hour scan target. The acceptance floor is 6,000
messages/hour; the target is an operational goal, not a throttle or guarantee.

With the flag disabled or unset, the legacy path remains active. It requests
BODYSTRUCTURE for up to 200 messages and then attempts up to 50 payloads per
poll through the ordinary intake flow. Its historical payload admission keeps
the existing unfinished-intake, waiting-document-job, and workdir safeguards.
Do not compare legacy payload-attempt counts with enabled-pipeline metadata
scan counts: they measure different phases.

## Bounded work

- Socket and Celery limits bound a stuck connection. Polling has a finite
  deadline and each account receives a bounded share.
- In the enabled pipeline, BODYSTRUCTURE classification is conservative: only
  a complete, nameless plain-text/HTML structure is proven to need no payload.
  Unknown, malformed or attachment-bearing structures become candidates. A
  candidate is not proof that an accepted attachment exists.
- In the legacy mode, the bounded BODYSTRUCTURE and payload limits are the
  200-message and 50-attempt limits described above.
- Failed mail attempts back off instead of consuming every poll. Attachments
  are staged durably before publication; the same message/part/content identity
  reuses its reservation.
- In legacy mode, historical full-payload admission pauses at 500 unfinished
  IMAP intakes, 2,000 waiting document jobs, or less than 5 GiB free in the
  workdir. Unknown capacity fails closed. In enabled mode, metadata scanning
  has no document/OCR queue gate; retain the 5 GiB workdir safety threshold for
  download staging. A deferred historical message gets no ledger entry and
  cannot be skipped by the cursor.
- Historical attachments and their child tasks use priority 6. New mail keeps
  priority 0. Historical IMAP work does not age into the urgent queue.

## Restart and retry behavior

The IMAP intake acknowledges its broker delivery after processing and rejects
delivery on worker loss. A unique claim token fences completion/error writes
from an older claim. Queue reconciliation checks both waiting and unacknowledged
Redis deliveries before replacing an expired dispatch. If the bounded broker
inventory cannot be obtained, that replacement waits for a later poll.

Transient conversion failures retry with durable delays from five minutes to
one hour. Unsupported/corrupt inputs remain staged and visibly failed with
`suppress_automatic_retry` in intake metadata. Operators must inspect and repair
the cause before clearing that flag; a restart alone does not clear it.

This is not an exactly-once guarantee for every downstream OCR, AI or delivery
stage. Those tasks retain their existing acknowledgement and retry behavior.
Use graceful worker termination and allow active work to finish. Do not enable
global late acknowledgement or add concurrent document workers without checking
each stage's idempotency and shared temporary files.

## Existing queue amplification

Deploy the corrected consumer and publishers before assessing new dispatch
growth. Old duplicate envelopes may remain. The separately documented
[queue compactor](imap-queue-compaction.md) requires an exact preview, a durable
backup and quiescent producers/consumers. It preserves unknown tasks and every
unique unfinished intake. It does not remove source mail, files or documents.
The [backlog reprioritizer](document-backlog-priority.md) can then move reviewed
legacy work to priority 6 while protecting current scan intakes. It also requires
quiescence, an exact preview, persistent backup and independent readback.

For acceptance, compare schema revision, ledger/cursor growth, per-lane
`scanned`, `ready`, `claimed`, `downloading`, `retry_wait`, `completed`, and
downloaded counts, active consumers for both download queues, and unfinished
intakes across a graceful restart. Use the same account, mailbox, and
UIDVALIDITY epoch for both snapshots; reject any duplicate-intake increase.
Verify that a current scan reaches the fresh lane and the document pipeline.
A candidate is merely durable metadata classification; `downloaded` means an
accepted attachment was staged and handed off. It does not mean OCR, AI, or
destination processing has finished.

Historical candidates may remain pending by design. Acceptance measures stable
scan throughput and durable download handoff, not a zero backlog gauge. Do not
infer a one-week completion estimate from the scanner ETA alone; measure the
download rate separately.

Run the IMAP task/durable/intake/BODYSTRUCTURE, conversion, priority and compactor
tests together. Run both `ruff check` and `ruff format --check` with the same
interpreter environment; CI also enforces typed helpers under `app.utils`.
