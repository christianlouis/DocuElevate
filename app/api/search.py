"""Full-text search API endpoints.

Provides document search across OCR text, AI metadata, filenames, and tags
via Meilisearch.  Designed to serve as the backend for the UI search bar on
the /files page and as a standalone API for integrations.

Future extension point: the OCR text stored in the index is also suitable
for RAG (Retrieval Augmented Generation) chatbot workflows.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.auth import require_login
from app.utils.meilisearch_client import search_documents

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
@require_login
def search_api(
    request: Request,
    q: str = Query(..., min_length=1, max_length=512, description="Full-text search query"),
    mime_type: Optional[str] = Query(None, description="Filter by MIME type (e.g. application/pdf)"),
    document_type: Optional[str] = Query(None, description="Filter by document type (e.g. Invoice)"),
    language: Optional[str] = Query(None, description="Filter by language code (e.g. de, en)"),
    tags: Optional[str] = Query(None, description="Filter by tag (exact match)"),
    sender: Optional[str] = Query(None, description="Filter by sender/absender (exact match)"),
    text_quality: Optional[str] = Query(
        None,
        description="Filter by OCR text quality: no_text, low, medium, high",
    ),
    date_from: Optional[int] = Query(None, description="Filter results created after this Unix timestamp"),
    date_to: Optional[int] = Query(None, description="Filter results created before this Unix timestamp"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
):
    """Search documents by full text, metadata, and tags.

    Searches across:
    - Document title and filename
    - OCR / extracted text
    - Tags, sender, recipient, document type
    - Correspondent and reference number

    Results are ranked by Meilisearch relevance and include highlighted
    snippets showing where the query terms matched.

    Query Parameters:
    - q: Search query (required)
    - mime_type: Filter by MIME type
    - document_type: Filter by document type
    - language: Filter by language code
    - tags: Filter by tag (exact match on a single tag)
    - sender: Filter by sender/absender (exact match)
    - text_quality: Filter by OCR text quality (no_text, low, medium, high)
    - date_from: Unix timestamp lower bound
    - date_to: Unix timestamp upper bound
    - page: Page number (default: 1)
    - per_page: Results per page (default: 20, max: 100)

    Example:
    ```
    GET /api/search?q=invoice&document_type=Invoice&tags=amazon&date_from=1704067200&page=1&per_page=20
    ```

    Response:
    ```json
    {
      "results": [
        {
          "file_id": 42,
          "original_filename": "2026-01-15_Invoice_Amazon.pdf",
          "document_title": "Amazon Invoice January 2026",
          "document_type": "Invoice",
          "tags": ["amazon", "invoice"],
          "_formatted": {
            "document_title": "Amazon <mark>Invoice</mark> January 2026",
            "ocr_text": "...total amount of the <mark>invoice</mark> is..."
          }
        }
      ],
      "total": 42,
      "page": 1,
      "pages": 3,
      "query": "invoice"
    }
    ```
    """
    logger.info(f"Search request: q={q!r}, mime_type={mime_type}, page={page}, per_page={per_page}")

    result = search_documents(
        q,
        mime_type=mime_type,
        document_type=document_type,
        language=language,
        tags=tags,
        sender=sender,
        text_quality=text_quality,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

    return result
