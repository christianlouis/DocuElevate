# IMAP queue compaction

`scripts/compact_imap_queue.py` is an operator-only cleanup for redundant
Celery envelopes already waiting in Redis. It is read-only by default.

Run it from the DocuElevate worker environment with the application database
and broker settings available:

```sh
DocuElevate/.venv/bin/python scripts/compact_imap_queue.py > /tmp/imap-preview.json
```

Inspect the JSON plan and record its `snapshot_digest`. Before applying, stop
the IMAP producer and the main worker and ensure no other producer publishes to
`document_processor` (Beat and manual producers included). Then apply exactly
the reviewed snapshot:

```sh
DocuElevate/.venv/bin/python scripts/compact_imap_queue.py \
  --apply --preview-digest DIGEST \
  --backup /workdir/imap-queue-backups/imap-QUEUE-DIGEST.json
```

The tool only considers the base `document_processor` list and priority lists
0–9. It removes byte-for-byte duplicate
`app.tasks.imap_intake.process_imap_intake(intake_id)` envelopes: completed
intakes may lose all copies; unfinished intakes retain at least one copy.
Malformed messages, other tasks, and envelopes with different headers,
dispatch tokens, arguments, or kwargs are retained. It never touches mail,
attachments, database rows, or in-flight deliveries.

The backup is written and fsynced with mode `0600` before the Redis transaction.
Redis `WATCH` plus a digest check aborts if the queue changed; there is no
automatic retry. After a successful transaction the tool verifies exact list
contents and order. A failed apply leaves the backup for investigation; do not
retry until the queue is re-previewed.
