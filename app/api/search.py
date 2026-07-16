"""Full-text search API endpoints.

Provides document search across OCR text, AI metadata, filenames, and tags
via Meilisearch.  Designed to serve as the backend for the UI search bar on
the /files page and as a standalone API for integrations.

Future extension point: the OCR text stored in the index is also suitable
for RAG (Retrieval Augmented Generation) chatbot workflows.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.models import FileRecord
from app.utils.hybrid_search import hybrid_rank, semantic_candidates
from app.utils.meilisearch_client import search_documents
from app.utils.user_scope import apply_owner_filter

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
    sort_by: Literal["relevance", "created_at", "file_size", "confidence_score"] = Query(
        "relevance", description="Result sort field"
    ),
    sort_order: Literal["asc", "desc"] = Query("desc", description="Result sort direction"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    mode: Literal["keyword", "semantic", "hybrid"] = Query("keyword", description="Ranking strategy"),
    debug_ranking: bool = Query(False, description="Include ranking score components"),
    db: Session = Depends(get_db),
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

    # Meilisearch is a shared external index.  Never rely on the database
    # checks performed by the file-detail endpoint to protect search results:
    # constrain the search itself to the IDs this principal may access.
    # Keeping this as an ID allowlist also includes explicitly shared files and
    # follows the same unowned-document policy as the rest of the application.
    accessible_file_ids: list[int] | None = None
    if settings.multi_user_enabled:
        accessible_file_ids = [
            row[0] for row in apply_owner_filter(db.query(FileRecord.id), request).order_by(FileRecord.id.asc()).all()
        ]

    result = search_documents(
        q,
        file_ids=accessible_file_ids,
        mime_type=mime_type,
        document_type=document_type,
        language=language,
        tags=tags,
        sender=sender,
        text_quality=text_quality,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )

    if mode == "keyword":
        return result

    semantic = semantic_candidates(db, request, q, mime_type=mime_type)
    ranked = semantic if mode == "semantic" else hybrid_rank(result["results"], semantic)
    start = (page - 1) * per_page
    page_results = ranked[start : start + per_page]
    if not debug_ranking:
        for item in page_results:
            item.pop("ranking_components", None)
    return {
        **result,
        "results": page_results,
        "total": len(ranked),
        "pages": (len(ranked) + per_page - 1) // per_page,
        "mode": mode,
    }
