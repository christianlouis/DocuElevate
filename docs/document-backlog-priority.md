# Reprioritizing an existing document backlog

`scripts/reprioritize_document_backlog.py` is an operator tool for moving
eligible jobs from the normal `document_processor` Redis list to Celery's
priority-6 list. It changes only task envelopes; it never reads or modifies
documents, mail, or database rows.

The default mode is a bounded, read-only preview. It reads both lists in full
within the configured limits (100,000 messages and 256 MiB by default), emits
counts, hashes, and a preview digest, and never prints raw messages. Only the
explicit registered-task allowlist is eligible. Malformed, unknown,
unregistered, and protected messages stay byte-for-byte in their original
list and position. Existing priority-6 entries remain first in the Redis list;
the moved jobs are appended so Redis's right-pop consumer sees the older moved
jobs before the existing priority-6 backlog.

Run from an environment with the production Celery broker configuration:

```sh
python scripts/reprioritize_document_backlog.py \
  --protect-intake 2275 \
  --protect-intake 2276
```

Review the digest and counts. Stop the IMAP producer, document worker,
maintenance producers, and any other producer/consumer that can touch these
lists. Then apply the unchanged preview with a new persistent backup path and
repeat every protection flag:

```sh
python scripts/reprioritize_document_backlog.py \
  --protect-intake 2275 \
  --protect-intake 2276 \
  --apply \
  --preview-digest <digest-from-preview> \
  --backup /workdir/queue-backups/reprioritize-2026-11-20.json
```

The backup is exact raw queue content, mode `0600`, written and fsynced before
the Redis transaction. The apply path uses Redis `WATCH`/`MULTI` and fails
closed if either list changed after the preview. It performs a post-apply
order and byte-multiset readback. A failed CAS leaves the queue untouched;
rerun a preview rather than retrying with the old digest. Do not reuse a backup
path: an existing path is rejected.

This is an operator migration step, not a replacement for the producer's
priority marker. New IMAP backlog publishers should continue to set
`imap_backlog=true` and priority `6` at enqueue time.
