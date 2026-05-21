# Setting up Evernote Integration

This guide explains how to configure DocuElevate to create Evernote notes for processed documents.

## Overview

The Evernote destination creates one note per processed document. The note contains:

- A visible metadata section populated from DocuElevate's extracted metadata JSON
- The processed PDF attached as an Evernote resource
- Optional tags from `EVERNOTE_DEFAULT_TAGS` plus extracted document tags

## Required Configuration

| Variable | Description |
|----------|-------------|
| `EVERNOTE_ENABLED` | Set to `false` to disable Evernote uploads without removing credentials. Default: `true` |
| `EVERNOTE_AUTH_TOKEN` | Evernote developer token or OAuth access token with note creation permissions |

## Optional Configuration

| Variable | Description |
|----------|-------------|
| `EVERNOTE_SANDBOX` | Use Evernote sandbox API endpoints. Default: `false` |
| `EVERNOTE_NOTEBOOK_GUID` | Target notebook GUID. If omitted, Evernote uses the account default notebook |
| `EVERNOTE_DEFAULT_TAGS` | Comma-separated tags to apply to every created note, for example `docuelevate,archive` |
| `EVERNOTE_INCLUDE_METADATA` | Include extracted metadata in the note body. Default: `true` |

## Example

```dotenv
EVERNOTE_ENABLED=true
EVERNOTE_AUTH_TOKEN=your-evernote-token
EVERNOTE_NOTEBOOK_GUID=optional-notebook-guid
EVERNOTE_DEFAULT_TAGS=docuelevate,processed
EVERNOTE_INCLUDE_METADATA=true
```

## Metadata and Attachments

DocuElevate reads the companion metadata file next to the processed PDF, for example `invoice.pdf` and `invoice.json`. Non-empty metadata fields are rendered into the Evernote note body. Values such as `Unknown`, empty strings, and null values are skipped.

If the metadata contains a `tags` field, those tags are applied to the note together with any tags configured in `EVERNOTE_DEFAULT_TAGS`.

The processed PDF is attached directly to the note using Evernote's resource model, so it appears as a normal Evernote attachment.

## Notes

- Evernote tokens can expire or be revoked. If uploads start failing with authentication errors, generate or refresh the token and update `EVERNOTE_AUTH_TOKEN`.
- If `EVERNOTE_NOTEBOOK_GUID` points to a missing or inaccessible notebook, Evernote will reject the note creation request.
- Evernote enforces account upload quotas and per-note size limits. Large PDFs may fail if they exceed those limits.
