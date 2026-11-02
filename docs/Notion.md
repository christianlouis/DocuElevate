# Notion destination

## Global destination (single-user only)

The optional global Notion destination is disabled by default. Configure
`NOTION_ENABLED=true`, `NOTION_API_TOKEN`, and exactly one of
`NOTION_DATA_SOURCE_ID` or `NOTION_DATABASE_ID` for a single-user deployment.
The global destination is automatically blocked when `MULTI_USER_ENABLED=true`;
multi-user installations must use the encrypted per-user Notion integration.

Global Notion is added to the existing global fan-out and does not replace or
suppress Dropbox, Google Drive, OneDrive, Nextcloud, Paperless-ngx, S3, or any
other configured global destination. It does not set a default owner, create
user integrations, or migrate existing documents.

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
DocuElevate link. PDF attachments up to 20 MiB use Notion's single-part flow;
larger PDFs use 10 MiB multipart chunks, completed before page creation. They
remain one complete file in Notion. Every upload checks the workspace limit
reported by `/v1/users/me` (cached for five minutes): 5 MiB on free workspaces,
up to 5 GiB on eligible paid workspaces. The workspace's actual value controls.
See Notion's [file limits](https://developers.notion.com/guides/data-apis/working-with-files-and-media)
and [multipart upload flow](https://developers.notion.com/guides/data-apis/sending-larger-files).

For personal destinations, choose **Stop** or **Send a DocuElevate link instead**
when the file exceeds that limit. Link fallback requires a file ID and configured
HTTPS DocuElevate URL; readers must authenticate and have document access.
An unavailable workspace-limit lookup does not silently switch to a link.
Optionally try lossless PDF optimization first; signed PDFs are left untouched.
The original file is never rewritten. Source-specific settings override the
destination default when trusted source provenance is available.
Oversized files with the stop policy fail before page creation. Redirects are
not followed, requests have bounded connect/read timeouts, and connection
tests perform no writes. If page creation has an uncertain outcome, the task
is not retried automatically. Retrying it manually can create a duplicate;
inspect Notion before retrying.
