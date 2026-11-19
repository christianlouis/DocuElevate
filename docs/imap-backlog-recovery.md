# IMAP backlog recovery

Polling covers the selected mailbox regardless of message age or read state.
Gmail uses All Mail; other providers use INBOX. UIDVALIDITY and a durable UID
ledger identify messages. The historical cursor advances only past messages
that have a durable ledger entry. Historical work, recent arrivals and retries
share the polling budget so one class cannot monopolize it.

## Bounded work

- Socket and Celery limits bound a stuck connection. Polling has a finite
  deadline and each account receives a bounded share.
- A poll requests BODYSTRUCTURE for up to 200 candidate messages. Only proven,
  unnamed plain-text/HTML messages can complete without downloading their body.
  Unknown, malformed or attachment-bearing structures use the ordinary
  BODY.PEEK path, limited to 50 payload attempts. Labels and deletion still
  apply only after accepting attachments; proven text-only messages need neither.
- Failed mail attempts back off instead of consuming every poll. Attachments
  are staged durably before publication; the same message/part/content identity
  reuses its reservation.
- Historical full-payload admission pauses at 500 unfinished IMAP intakes,
  2,000 waiting document jobs, or less than 5 GiB free in the workdir. Unknown
  capacity fails closed. Recent mail, durable retries and proven metadata-only
  messages remain eligible. A deferred historical message gets no ledger entry
  and cannot be skipped by the cursor. Capacity is checked once per poll.
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

For acceptance, compare ledger/cursor growth, ready-queue counts and unfinished
intakes across a graceful restart, and verify a current scan reaches the
document pipeline. A completed mail ledger entry means its attachments were
durably handed off, not that all OCR/AI/destination processing has finished.

Run the IMAP task/durable/intake/BODYSTRUCTURE, conversion, priority and compactor
tests together. Run both `ruff check` and `ruff format --check` with the same
interpreter environment; CI also enforces typed helpers under `app.utils`.
