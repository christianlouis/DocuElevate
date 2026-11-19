# IMAP queue compaction

`scripts/compact_imap_queue.py` is an operator-only cleanup for redundant
Celery envelopes already waiting in Redis. It is read-only by default.

Run it from the DocuElevate worker environment with the application database
and broker settings available:

```sh
DocuElevate/.venv/bin/python scripts/compact_imap_queue.py > /tmp/imap-preview.json
```

Inspect the JSON plan and record its `preview_digest`. Before applying, stop
the IMAP producer and the main worker and ensure no other producer publishes to
`document_processor` (Beat and manual producers included). Then apply exactly
the reviewed snapshot:

```sh
DocuElevate/.venv/bin/python scripts/compact_imap_queue.py \
  --apply --preview-digest DIGEST \
  --backup /workdir/imap-queue-backups/imap-QUEUE-DIGEST.json
```

The tool only considers the base `document_processor` list and priority lists
0–9. It removes known `app.tasks.imap_intake.process_imap_intake(intake_id)`
envelopes with empty kwargs. Transport-generated Celery IDs (`id`, `root_id`,
`parent_id`, `origin`, `correlation_id`, and `delivery_tag`) are ignored when comparing
envelopes. Dispatch tokens, retries, timing, routing, options, arguments, and
kwargs remain significant. Completed intakes may lose even a singleton
obsolete envelope; unfinished intakes retain at least one equivalent copy.
Malformed messages, other tasks, and envelopes with different execution
options are retained. It never touches mail, attachments, database rows, or
in-flight deliveries.

The preview digest covers both the raw queue and the durable state of every
candidate intake. During apply those intake rows are locked and reread before
the Redis transaction, preventing a completed-to-reset transition from being
silently acted on. The backup is written and fsynced with mode `0600` before
the Redis transaction, and an existing backup path is rejected rather than
overwritten. Redis `WATCH` plus a digest check aborts if the queue changed; no
automatic retry is performed. After a successful transaction the tool verifies
exact list contents and order. A failed apply leaves the backup for
investigation; do not retry until the queue is re-previewed.
