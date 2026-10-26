# DocuElevate acceptance pack

This directory contains two synthetic PDFs and a read-only runtime verifier.
The fixtures contain no personal, customer, or secret data:

- `native-text-acceptance.pdf` — embedded/native text fixture
- `image-only-scan-acceptance.pdf` — image-only fixture requiring OCR

Create or recreate the PDFs with the existing validation runtime:

```sh
/tmp/docuelevate-validation-20261026.PBJjKu/bin/python \
  outputs/production-improvements-2026-10-26/acceptance/make_synthetic_pdfs.py
```

After an authorized user uploads the fixtures and supplies the resulting
token/file IDs, run read-only verification (GET requests only):

```sh
/tmp/docuelevate-validation-20261026.PBJjKu/bin/python \
  outputs/production-improvements-2026-10-26/acceptance/verify_runtime.py \
  --base-url https://<docuelevate-host> \
  --token '<synthetic-token>' \
  --file-id 6571 --file-id 6583 --file-id 6584 \
  --export-file-id 6571
```

The verifier reports canonical processing step names/statuses, text-quality
presence, token-presence as a boolean, search match and result IDs, processed
PDF retrieval checks, retry support for failed step names, and notification
inbox reachability. It does not print extracted text or notification contents.

The script deliberately does not upload, retry, mark notifications read, or
send a provider diagnostic. Failed IDs `6571`, `6583`, and `6584` are inspected
only; retry support is reported from the existing retryable-step allowlist.

## Code-path scope inspected

- Canonical processing history is read from `GET /api/files/{file_id}` and its
  `logs`/`processing_status` fields.
- Extraction is checked through `GET /api/files/{file_id}/text/processed`, but
  the token is evaluated in memory and only a boolean is printed.
- Search uses `GET /api/search?q=...`; processed-artifact retrieval uses
  `GET /api/files/{file_id}/download?version=processed`.
- Failed-step retry is exposed by the mutating
  `POST /api/files/{file_id}/retry-subtask` endpoint. This pack only reports
  whether observed failed step names are in the existing supported set.
- Notification inbox/target reads are available through
  `GET /api/user-notifications/inbox` and `/targets`. Provider delivery itself
  requires the mutating diagnostic/test endpoint and is therefore explicitly
  reported as unverified here.
