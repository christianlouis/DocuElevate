# Notion destination

DocuElevate can create one page per document in a Notion data source. The
connection stores the per-user Notion internal integration token encrypted in
the normal integration credential store; it is never written to logs.

## Setup

Create or open the target Notion database and give the internal integration
access through Notion's **Connections** menu. In the Integrations form, enter exactly one
parent identifier: the data source UUID, or the database UUID. A database URL
contains a database identifier, not necessarily a data source identifier.
DocuElevate resolves a database identifier only when the database has exactly
one data source. The title property is discovered from the resolved
data-source schema.

The optional DocuElevate base URL must use HTTPS without credentials,
query strings, or fragments. If omitted, the configured server URL is used.
Links are written as authenticated `/files/{id}` links. Enable **Attach the
PDF** to upload the source as a private Notion file block.

## Limits and behavior

Pages contain the source filename, available summary and tags, the document date when
available (otherwise a clearly labelled processed date), and a stable private
DocuElevate link. PDF attachments use Notion's single-part upload flow and are
limited to 20 MiB; Notion workspace limits may be lower. Oversized files fail
before page creation. Redirects are
not followed, requests have bounded connect/read timeouts, and connection
tests perform no writes. If page creation has an uncertain outcome, the task
is not retried automatically. Retrying it manually can create a duplicate;
inspect Notion before retrying.
