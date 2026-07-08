# Workflow Template Examples

These examples pair the built-in pipeline templates with representative sample
metadata and integration starter payloads. Use them when validating imports,
writing demos, or building customer-specific workflow kits.

## Built-In Template Samples

| Template | Category | Sample data |
| --- | --- | --- |
| `standard_document_archive` | `standard` | [`standard-document.sample.json`](standard-document.sample.json) |
| `invoice_intake_pack` | `invoices` | [`invoice.sample.json`](invoice.sample.json) |
| `contract_review_pack` | `contracts` | [`contract.sample.json`](contract.sample.json) |
| `receipt_capture_pack` | `receipts` | [`receipt.sample.json`](receipt.sample.json) |
| `research_archive_pack` | `research` | [`research.sample.json`](research.sample.json) |

Each sample uses ordinary metadata fields that can be passed to routing-rule
dry runs or used as fixture data when testing template imports.

## Integration Starters

The starter payloads below are intentionally configuration-only. Replace URLs,
recipients, secrets, and tokens with environment-managed values in your
deployment.

| Integration | Example |
| --- | --- |
| Email forwarding | [`email-forwarding.example.json`](email-forwarding.example.json) |
| Webhook receiver | [`webhook-receiver.example.json`](webhook-receiver.example.json) |

Slack and Teams notifications can be configured through the same webhook
receiver pattern by using the incoming-webhook URL from the target workspace and
subscribing to the relevant DocuElevate document events.
