"""Meilisearch client utilities for full-text document search.

This module provides functions for indexing documents into Meilisearch
and searching across OCR text, AI metadata, filenames, and tags.

The search index is designed to support future RAG (Retrieval Augmented
Generation) workflows by storing full document text alongside structured
metadata fields.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Index settings applied once at index creation / first use
_INDEX_SETTINGS = {
    "searchableAttributes": [
        "document_title",
        "original_filename",
        "ocr_text",
        "tags",
        "sender",
        "recipient",
        "document_type",
        "correspondent",
    ],
    "filterableAttributes": [
        "mime_type",
        "document_type",
        "language",
        "tags",
        "created_at_ts",
        "file_id",
    ],
    "sortableAttributes": [
        "created_at_ts",
        "file_size",
    ],
    "displayedAttributes": [
        "file_id",
        "original_filename",
        "document_title",
        "document_type",
        "tags",
        "sender",
        "recipient",
        "correspondent",
        "language",
        "reference_number",
        "mime_type",
        "file_size",
        "created_at_ts",
        "ocr_text",
    ],
    "rankingRules": [
        "words",
        "typo",
        "proximity",
        "attribute",
        "sort",
        "exactness",
    ],
}


def get_meilisearch_client():
    """Return a configured Meilisearch client, or None if unavailable/disabled."""
    try:
        import meilisearch

        from app.config import settings

        if not settings.enable_search:
            return None

        kwargs: dict[str, Any] = {"url": settings.meilisearch_url}
        if settings.meilisearch_api_key:
            kwargs["api_key"] = settings.meilisearch_api_key

        client = meilisearch.Client(**kwargs)
        return client
    except ImportError:
        logger.warning("meilisearch package not installed; search disabled")
        return None
    except Exception as exc:
        logger.warning(f"Could not connect to Meilisearch: {exc}")
        return None


def _get_or_create_index(client):
    """Get the documents index, creating it with settings if it doesn't exist."""
    from app.config import settings

    index_name = settings.meilisearch_index_name
    try:
        index = client.get_index(index_name)
    except Exception:
        # Index doesn't exist – create it with file_id as primary key
        task = client.create_index(index_name, {"primaryKey": "file_id"})
        client.wait_for_task(task.task_uid)
        index = client.get_index(index_name)
        # Apply search settings
        try:
            task = index.update_settings(_INDEX_SETTINGS)
            client.wait_for_task(task.task_uid)
        except Exception as exc:
            logger.warning(f"Could not update Meilisearch index settings: {exc}")
    return index


def _build_document(file_record, text: str, metadata: dict) -> dict:
    """Build a Meilisearch document from a FileRecord and extracted content."""

    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    # Unix timestamp for sorting/filtering
    created_at_ts = 0
    if file_record.created_at:
        try:
            created_at_ts = int(file_record.created_at.timestamp())
        except Exception as ts_exc:  # noqa: BLE001
            logger.debug(f"Could not convert created_at to timestamp: {ts_exc}")

    return {
        "file_id": file_record.id,
        "original_filename": file_record.original_filename or "",
        "document_title": metadata.get("title") or metadata.get("filename") or file_record.original_filename or "",
        "document_type": metadata.get("document_type") or metadata.get("kommunikationsart") or "",
        "tags": tags,
        "sender": metadata.get("absender") or "",
        "recipient": metadata.get("empfaenger") or "",
        "correspondent": metadata.get("correspondent") or "",
        "language": metadata.get("language") or "",
        "reference_number": metadata.get("reference_number") or "",
        "mime_type": file_record.mime_type or "",
        "file_size": file_record.file_size or 0,
        "created_at_ts": created_at_ts,
        "ocr_text": text or "",
    }


def index_document(file_record, text: str, metadata: dict) -> bool:
    """Index a document in Meilisearch.

    Args:
        file_record: FileRecord ORM instance with at minimum .id set.
        text: Full OCR / extracted text for the document.
        metadata: AI-extracted metadata dict.

    Returns:
        True if indexing succeeded, False otherwise.
    """
    client = get_meilisearch_client()
    if client is None:
        return False

    try:
        index = _get_or_create_index(client)
        doc = _build_document(file_record, text, metadata)
        task = index.add_documents([doc])
        logger.info(f"Queued Meilisearch indexing for file_id={file_record.id} (task_uid={task.task_uid})")
        return True
    except Exception as exc:
        logger.warning(f"Meilisearch indexing failed for file_id={file_record.id}: {exc}")
        return False


def delete_document(file_id: int) -> bool:
    """Remove a document from the Meilisearch index.

    Args:
        file_id: The database ID of the file to remove.

    Returns:
        True if deletion succeeded, False otherwise.
    """
    client = get_meilisearch_client()
    if client is None:
        return False

    try:
        from app.config import settings

        index = client.get_index(settings.meilisearch_index_name)
        task = index.delete_document(file_id)
        logger.info(f"Queued Meilisearch deletion for file_id={file_id} (task_uid={task.task_uid})")
        return True
    except Exception as exc:
        logger.warning(f"Meilisearch deletion failed for file_id={file_id}: {exc}")
        return False


def search_documents(
    query: str,
    *,
    mime_type: Optional[str] = None,
    document_type: Optional[str] = None,
    language: Optional[str] = None,
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Search documents in Meilisearch.

    Args:
        query: Full-text search query string.
        mime_type: Optional MIME-type filter.
        document_type: Optional document type filter.
        language: Optional language filter (ISO 639-1, e.g. "de").
        date_from: Optional lower bound Unix timestamp for created_at.
        date_to: Optional upper bound Unix timestamp for created_at.
        page: 1-based page number.
        per_page: Results per page (max 100).

    Returns:
        Dict with keys: results, total, page, pages, query.
        Returns empty results dict on any error.
    """
    empty: dict = {"results": [], "total": 0, "page": page, "pages": 0, "query": query}

    client = get_meilisearch_client()
    if client is None:
        return empty

    try:

        index = _get_or_create_index(client)

        # Build filter expressions
        filters: list[str] = []
        if mime_type:
            filters.append(f'mime_type = "{mime_type}"')
        if document_type:
            filters.append(f'document_type = "{document_type}"')
        if language:
            filters.append(f'language = "{language}"')
        if date_from is not None:
            filters.append(f"created_at_ts >= {date_from}")
        if date_to is not None:
            filters.append(f"created_at_ts <= {date_to}")

        search_params: dict[str, Any] = {
            "offset": (page - 1) * per_page,
            "limit": per_page,
            "attributesToHighlight": ["document_title", "original_filename", "ocr_text", "tags"],
            "highlightPreTag": "<mark>",
            "highlightPostTag": "</mark>",
            "attributesToCrop": ["ocr_text"],
            "cropLength": 200,
        }

        if filters:
            search_params["filter"] = " AND ".join(filters)

        result = index.search(query, search_params)

        hits = result.get("hits", [])
        total = result.get("estimatedTotalHits", result.get("nbHits", len(hits)))

        # Attach highlights to each hit
        formatted_results = []
        for hit in hits:
            formatted = dict(hit)
            # Include formatted (highlighted) snippets if available
            if "_formatted" in hit:
                formatted["_formatted"] = hit["_formatted"]
            # Exclude raw ocr_text from results (use _formatted snippet instead)
            formatted.pop("ocr_text", None)
            formatted_results.append(formatted)

        pages = (total + per_page - 1) // per_page if total > 0 else 0

        return {
            "results": formatted_results,
            "total": total,
            "page": page,
            "pages": pages,
            "query": query,
        }

    except Exception as exc:
        logger.warning(f"Meilisearch search failed for query '{query}': {exc}")
        return empty
