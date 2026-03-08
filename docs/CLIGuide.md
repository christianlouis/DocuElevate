# DocuElevate CLI Guide

The `docuelevate` command-line tool lets you interact with your DocuElevate instance
from a terminal, shell script, or CI/CD pipeline.  It is ideal for:

- Batch uploads from a script or cron job
- Downloading processed documents programmatically
- Searching documents in automation workflows
- Rotating API tokens safely without touching the web UI

---

## Installation

The CLI is included in the standard DocuElevate package.  After installing the
Python package (e.g. inside the Docker image or a virtualenv), the `docuelevate`
command is available:

```bash
pip install docuelevate          # or: pip install -e . inside the repo
docuelevate --help
```

---

## Authentication

All commands require an API token.  Create one at `/api-tokens` in the web UI,
or with the `docuelevate token create` command itself.

Provide the token in either of two ways:

| Method | Example |
|--------|---------|
| `--token` flag | `docuelevate --token de_xxxxx list` |
| Environment variable | `export DOCUELEVATE_API_TOKEN=de_xxxxx` |

The environment variable is recommended for scripts so that secrets never appear
in shell history or process listings.

---

## Configuration

| Option / Variable | Default | Description |
|-------------------|---------|-------------|
| `--url` / `DOCUELEVATE_URL` | `http://localhost:8000` | Base URL of the DocuElevate instance |
| `--token` / `DOCUELEVATE_API_TOKEN` | _(none)_ | API token for authentication |
| `--format` | `table` | Output format: `table` (human-readable) or `json` (pipe-friendly) |
| `--timeout` / `DOCUELEVATE_TIMEOUT` | `60` | HTTP request timeout in seconds |

Setting both `DOCUELEVATE_URL` and `DOCUELEVATE_API_TOKEN` in your environment
removes the need for flags on every invocation:

```bash
export DOCUELEVATE_URL=https://docs.example.com
export DOCUELEVATE_API_TOKEN=de_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
docuelevate list
```

---

## Commands

### `list` — List documents

```
docuelevate [OPTIONS] list [OPTIONS]
```

Returns a paginated list of documents stored in DocuElevate.

| Option | Default | Description |
|--------|---------|-------------|
| `--page` | `1` | Page number |
| `--per-page` | `25` | Items per page (max 200) |
| `--search` | — | Filter by filename substring |
| `--mime-type` | — | Filter by MIME type (e.g. `application/pdf`) |
| `--status` | — | Filter by status: `pending`, `processing`, `completed`, `failed` |
| `--sort-by` | `created_at` | Sort field |
| `--sort-order` | `desc` | Sort direction: `asc` or `desc` |

**Examples:**

```bash
# Human-readable table
docuelevate list

# Only completed PDFs
docuelevate list --status completed --mime-type application/pdf

# Pipe filenames to another command
docuelevate --format json list | jq -r '.[].filename'

# Search by filename
docuelevate list --search invoice
```

---

### `upload` — Upload files

```
docuelevate [OPTIONS] upload [OPTIONS] FILES...
```

Uploads one or more local files to DocuElevate for processing.  Multiple file
paths (or shell globs) can be provided for batch uploads.

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size` | `5` | Maximum uploads before reporting progress |

**Examples:**

```bash
# Upload a single file
docuelevate upload report.pdf

# Batch upload — all PDFs in a folder
docuelevate upload /scans/*.pdf

# Upload multiple files explicitly
docuelevate upload invoice.pdf contract.pdf receipt.png

# JSON output to capture task IDs
docuelevate --format json upload *.pdf | jq '.[].task_id'
```

---

### `download` — Download a file

```
docuelevate [OPTIONS] download [OPTIONS] FILE_ID
```

Downloads a processed (or original) file by its numeric ID.

| Option | Default | Description |
|--------|---------|-------------|
| `-o` / `--output` | _(server filename)_ | Destination file path |
| `--version` | `processed` | `processed` or `original` |

**Examples:**

```bash
# Download processed version of file #42
docuelevate download 42

# Save to a specific path
docuelevate download 42 -o /tmp/invoice.pdf

# Download the original (unprocessed) upload
docuelevate download 42 --version original -o original.pdf
```

---

### `search` — Full-text search

```
docuelevate [OPTIONS] search [OPTIONS] QUERY
```

Searches across document text, filenames, tags, and metadata using Meilisearch.

| Option | Default | Description |
|--------|---------|-------------|
| `--mime-type` | — | Filter by MIME type |
| `--document-type` | — | Filter by document type (e.g. `Invoice`) |
| `--tags` | — | Filter by tag |
| `--language` | — | Filter by language code (e.g. `en`, `de`) |
| `--page` | `1` | Page number |
| `--per-page` | `20` | Results per page (max 100) |

**Examples:**

```bash
# Simple search
docuelevate search "amazon invoice"

# With filters
docuelevate search "contract" --document-type Contract --language en

# Pipe file IDs to the download command
docuelevate --format json search "Q1 report" | jq -r '.[].file_id'
```

---

### `token` — Manage API tokens

The `token` sub-group provides commands to create, list, and revoke personal API
tokens — enabling **token rotation** without logging into the web UI.

#### `token create`

```
docuelevate token create NAME
```

Creates a new token.  The full token value is printed exactly once — store it
securely.

```bash
# Create a new token
docuelevate --token de_existing token create "CI Pipeline"

# Capture the new token value in a script
NEW_TOKEN=$(docuelevate --format json --token de_existing token create "Rotation" \
            | jq -r '.token')
```

#### `token list`

```
docuelevate token list
```

Lists all your tokens (active and revoked).

```bash
docuelevate token list

# JSON for scripting
docuelevate --format json token list | jq '.[] | select(.is_active) | .id'
```

#### `token revoke`

```
docuelevate token revoke [--yes] TOKEN_ID
```

Revokes a token by its numeric ID.  The token is immediately invalidated.

| Option | Description |
|--------|-------------|
| `--yes` / `-y` | Skip confirmation prompt |

```bash
# Interactive confirmation
docuelevate token revoke 3

# Non-interactive (for scripts)
docuelevate token revoke 3 --yes
```

---

## Token Rotation

Rotate an API token safely without any downtime:

```bash
# 1. Create the replacement token
NEW_TOKEN=$(docuelevate --format json --token "$OLD_TOKEN" \
            token create "Rotated $(date +%Y-%m-%d)" | jq -r '.token')

# 2. Update consumers to use NEW_TOKEN, then revoke the old one
OLD_ID=$(docuelevate --format json --token "$OLD_TOKEN" token list \
         | jq '.[] | select(.is_active and (.token_prefix == "de_old_prefix")) | .id')
docuelevate --token "$NEW_TOKEN" token revoke --yes "$OLD_ID"
```

---

## Output Formats

### Table (default)

Human-readable, suitable for terminal use:

```
ID  FILENAME           SIZE   STATUS     CREATED_AT
--  -----------------  -----  ---------  -------------------
42  invoice_2026.pdf   98304  completed  2026-03-01T10:30:00
43  contract.pdf       51200  pending    2026-03-01T11:00:00
```

### JSON (`--format json`)

Machine-readable, pipe-friendly, suitable for `jq`, shell scripts, and CI:

```json
[
  {
    "id": 42,
    "filename": "invoice_2026.pdf",
    "size": 98304,
    "status": "completed",
    "created_at": "2026-03-01T10:30:00"
  }
]
```

---

## Pipe-Friendly Examples

```bash
# Download all completed PDFs in a folder
docuelevate --format json list --status completed --mime-type application/pdf \
  | jq -r '.[].id' \
  | xargs -I {} docuelevate download {} -o /backup/{}.pdf

# Count documents by status
docuelevate --format json list --per-page 200 \
  | jq 'group_by(.status) | map({status: .[0].status, count: length})'

# Search and get filenames
docuelevate --format json search "2026 invoice" \
  | jq -r '.[].filename'

# Batch upload all new files and capture task IDs
find /inbox -name "*.pdf" | xargs docuelevate upload \
  && echo "All uploaded"
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | One or more uploads failed (partial failure) |
| `2` | Invalid options or arguments |
| other | Fatal error (network, API, authentication) |

---

## Environment Variables Reference

| Variable | Description |
|----------|-------------|
| `DOCUELEVATE_URL` | Base URL of the DocuElevate instance |
| `DOCUELEVATE_API_TOKEN` | Personal API token (`de_…`) |
| `DOCUELEVATE_TIMEOUT` | HTTP request timeout in seconds (default: 60) |

---

## See Also

- [API Documentation](./API.md) — full REST API reference
- [User Guide](./UserGuide.md) — web UI guide including API token management
- [Configuration Guide](./ConfigurationGuide.md) — server-side configuration
