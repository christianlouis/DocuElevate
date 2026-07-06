# Pipeline Template Library

Pipeline templates are portable starter kits for processing profiles. They are
JSON documents that can be validated before import, shared between
installations, and exported from an existing profile.

## Format

The current format version is `1.0`.

```json
{
  "format_version": "1.0",
  "key": "invoice_intake_pack",
  "name": "Invoice intake pack",
  "description": "Classify invoices, extract accounting metadata, index for search, and deliver.",
  "category": "invoices",
  "compatibility": {
    "min_app_version": "0.173.0",
    "required_providers": []
  },
  "pipeline": {
    "is_active": true,
    "is_default": false
  },
  "steps": [
    {
      "step_type": "ocr",
      "label": "OCR invoice",
      "config": {
        "ocr_language": "auto"
      },
      "enabled": true
    }
  ]
}
```

## Fields

| Field | Required | Description |
| --- | --- | --- |
| `format_version` | Yes | Template schema version. DocuElevate currently accepts `1.0`. |
| `key` | Yes | Stable template identifier. Built-ins use lowercase snake case. |
| `name` | Yes | Human-readable profile name used by default during import. |
| `description` | No | Imported as the profile description unless overridden. |
| `category` | Yes | One of `contracts`, `invoices`, `receipts`, `research`, or `standard`. |
| `compatibility.min_app_version` | Yes | Minimum DocuElevate version that understands the template. |
| `compatibility.required_providers` | Yes | Provider keys an operator should configure before using the template. |
| `pipeline.is_active` | No | Imported profile active flag. Defaults to `true`. |
| `pipeline.is_default` | No | Imported profile default flag. Defaults to `false`. |
| `steps` | Yes | Ordered non-empty list of profile steps. |

Each step requires a `step_type` from `GET /api/pipelines/step-types`. Optional
`label`, `config`, and `enabled` fields customize the imported profile step.

## Built-In Templates

DocuElevate ships five starter templates:

- `standard_document_archive`
- `invoice_intake_pack`
- `contract_review_pack`
- `receipt_capture_pack`
- `research_archive_pack`

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/pipelines/templates` | List built-in templates. |
| `GET` | `/api/pipelines/templates/{template_key}` | Fetch one built-in template. |
| `POST` | `/api/pipelines/templates/validate` | Validate a template without importing it. |
| `POST` | `/api/pipelines/templates/import` | Import a template as a user-owned profile. |
| `GET` | `/api/pipelines/{pipeline_id}/template` | Export an accessible profile as a template. |

## Validation Rules

Validation checks:

- supported `format_version`
- known template category
- non-empty `key` and `name`
- compatible `min_app_version`
- `required_providers` is a list of strings
- at least one step
- every step uses a known `step_type`
- step `config` values are JSON objects

Use validation before import when accepting templates from another installation
or a repository.
