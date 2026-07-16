# DearConcierge Knowledge Bridge

## Outcome

DearConcierge can search the user's processed document corpus, retrieve the exact
source passages behind a result, and use those facts for project, life, and calendar
planning. The pilot runs only on the new DocuElevate preprod line. The production
Evergreen release remains unchanged until its small outbound bridge receives a
separate promotion approval.

## System boundary

```text
Evergreen DocuElevate -- signed multipart delivery --> Preprod intake
Dropbox corpus ------ resumable recursive import ----> Preprod intake
                                                      |
                                                      v
                                  normal OCR / metadata pipeline
                                                      |
                                                      v
                                      token chunks -> Qdrant
                                                      |
DearConcierge ---- OAuth session or Bearer token ---> retrieval API
DearConcierge MCP adapter --------------------------> retrieval API
```

The relational database and document work directory remain authoritative. Qdrant is
a derived index that can be deleted and rebuilt. Search results are never trusted for
authorization: document IDs returned by Qdrant are checked against the relational
owner/share model before any text is returned.

Qdrant is configured as a normal `VECTOR_DATABASE` destination on the user's
integration dashboard. The connection remains operator-managed, while destination
selection, processing status, retries, and errors follow the same per-user flow as
Google Drive or Dropbox. A Dropbox corpus is represented by a `WATCH_FOLDER` source
with `true_up_existing=true`; the initial recursive import includes subfolders and
subsequent polls continue from Dropbox's change cursor.

## Delivery slices and acceptance criteria

### KB-1: Authenticated preprod intake

- `POST /api/intake/documents` accepts `multipart/form-data` containing `file`,
  `source`, optional JSON metadata, and an idempotency key.
- Browser OAuth sessions and personal `Authorization: Bearer de_...` tokens use the
  existing DocuElevate identity and ownership model.
- A separately configured shared secret may be supplied for the one controlled legacy
  migration bridge. It must not reuse the OpenAI, database, or session secret.
- The endpoint validates size and file type, writes atomically, and calls the existing
  `process_document` task rather than maintaining a second pipeline.
- Repeating an idempotency key returns the original task/document state without writing
  a second file.

### KB-2: Evergreen outbound bridge

- A disabled-by-default destination posts document bytes, original filename, source
  document ID/hash, owner, processing timestamp, and an idempotency key to KB-1.
- Authentication is either a dedicated Bearer token or dedicated shared secret injected
  at runtime.
- Delivery has bounded timeouts and Celery retry behavior. A failed bridge delivery is
  visible but does not mark the already processed legacy document as failed.
- Contract tests run against the current code and the Evergreen source baseline before
  the sender is considered retrofit-safe.

### KB-3: Dropbox corpus import

- An authenticated operation starts a recursive import for a configured Dropbox SOURCE
  integration and folder root.
- Folder pagination and nested folders are supported.
- Dropbox file ID, revision, and path form the durable checkpoint. Restarting after a
  crash resumes without duplicating unchanged documents.
- Source files are never deleted during the corpus import.
- Progress reports discovered, downloaded, skipped, queued, failed, and last cursor.
- An optional bounded second pass OCRs index-first scans with no embedded text and
  sends the resulting text directly to Qdrant without metadata LLM work or legacy
  destination distribution.

### KB-4: Chunk vector index

- Full OCR text is split into overlapping, token-aware chunks.
- Every vector payload carries document ID, content hash, filename, title, MIME type,
  owner, chunk position, timestamp, and the cited text.
- Replacement is idempotent and retains the old index if embedding generation fails.
- An explicit corpus backfill and a health endpoint exist.
- Qdrant is private to the cluster and protected by its own API key.

### KB-5: Retrieval and MCP

- Semantic search returns ranked cited passages and never returns unauthorized payloads.
- Interactive document chat answers only from accessible evidence, returns numbered
  source links, and uses a separately configurable RAG model.
- Cross-document questions about counts, maxima, and trends combine semantic and
  full-text candidates. Limited retrieval is disclosed and must not be presented as a
  corpus-complete result.
- The lexical index reconciler pages through the full Meilisearch corpus and commits
  missing documents in resumable bulk updates on its own worker queue.
- A cited document endpoint returns authoritative OCR text and metadata for follow-up.
- OAuth-authenticated browser clients and Bearer-token clients use the same endpoints.
- The MCP server is a stateless adapter exposing `search_documents` and `get_document`;
  it holds a scoped DocuElevate token and does not connect directly to Qdrant.

### KB-6: Preprod gate

- Automated tests cover intake authentication, idempotency, path safety, size/type
  validation, outbound retries, Dropbox resume, chunk overlap, Qdrant replacement,
  authorization filtering, and source citations.
- A preprod smoke test imports a representative Dropbox subset, rebuilds Qdrant and
  Meilisearch from scratch, and answers agreed DearConcierge questions with traceable
  source documents and explicit coverage.
- Production deployment, Evergreen enablement, and credential changes require explicit
  approval after the evidence above is reviewed.

## Authentication evolution

The first release intentionally reuses mature controls already present in DocuElevate:

1. personal API token for DearConcierge service access;
2. existing OAuth/OIDC login for interactive users;
3. optional dedicated shared secret only for the legacy migration sender.

OAuth 2.1 authorization-server functionality, dynamic client registration, token scopes,
and MCP authorization metadata can be added later. They should extend the retrieval API,
not become a prerequisite for indexing the corpus.
