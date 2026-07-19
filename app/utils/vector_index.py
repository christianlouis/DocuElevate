"""Optional chunk-level Qdrant index for retrieval-augmented applications.

The existing ``FileRecord.embedding`` remains the document-level vector used
for duplicate detection.  This module creates a separate, optional index of
overlapping OCR-text chunks so external assistants can retrieve precise,
source-backed passages without changing the stable ingestion pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from app.config import settings
from app.utils.similarity import generate_embeddings

logger = logging.getLogger(__name__)


class VectorIndexError(RuntimeError):
    """Raised when the external vector index cannot satisfy a request."""


@dataclass(frozen=True)
class TextChunk:
    """A stable, ordered excerpt of a document's OCR text."""

    index: int
    text: str
    token_start: int
    token_end: int


def content_hash(text: str) -> str:
    """Return a stable digest used to detect stale indexed documents."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _token_chunks(text: str, model: str, size: int, overlap: int) -> list[TextChunk]:
    import tiktoken

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    encode = getattr(encoding, "encode_ordinary", encoding.encode)
    tokens = encode(text)
    if not tokens:
        return []

    chunks: list[TextChunk] = []
    start = 0
    step = size - overlap
    while start < len(tokens):
        end = min(start + size, len(tokens))
        chunk_text = encoding.decode(tokens[start:end]).strip()
        if chunk_text:
            chunks.append(TextChunk(len(chunks), chunk_text, start, end))
        if end >= len(tokens):
            break
        start += step
    return chunks


def _character_chunks(text: str, size: int, overlap: int) -> list[TextChunk]:
    """Conservative fallback using roughly four characters per token."""
    char_size = size * 4
    char_overlap = overlap * 4
    step = char_size - char_overlap
    chunks: list[TextChunk] = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(TextChunk(len(chunks), chunk_text, start // 4, (end + 3) // 4))
        if end >= len(text):
            break
        start += step
    return chunks


def chunk_text(
    text: str,
    *,
    model: str | None = None,
    size: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    """Split text into overlapping chunks suitable for semantic retrieval."""
    normalized = text.strip()
    if not normalized:
        return []

    model = model or settings.embedding_model
    size = size or settings.vector_chunk_tokens
    overlap = settings.vector_chunk_overlap_tokens if overlap is None else overlap
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("vector chunk overlap must be non-negative and smaller than chunk size")

    try:
        return _token_chunks(normalized, model, size, overlap)
    except Exception as exc:
        logger.warning("Token-aware chunking failed; using character fallback: %s", exc)
        return _character_chunks(normalized, size, overlap)


def _embedding_batches(chunks: list[TextChunk], token_budget: int) -> Iterable[list[TextChunk]]:
    """Group ordered chunks below a provider's aggregate request-token limit."""
    batch: list[TextChunk] = []
    batch_tokens = 0
    for chunk in chunks:
        chunk_tokens = max(1, chunk.token_end - chunk.token_start)
        if batch and batch_tokens + chunk_tokens > token_budget:
            yield batch
            batch = []
            batch_tokens = 0
        batch.append(chunk)
        batch_tokens += chunk_tokens
    if batch:
        yield batch


class QdrantVectorIndex:
    """Small HTTP client covering the Qdrant operations DocuElevate needs."""

    def __init__(self) -> None:
        self.base_url = settings.vector_index_url.rstrip("/")
        self.collection = settings.vector_index_collection
        self.timeout = settings.vector_index_timeout_seconds
        self.headers = {"Content-Type": "application/json"}
        if settings.vector_index_api_key:
            self.headers["api-key"] = settings.vector_index_api_key

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        expected: Iterable[int] = (200,),
    ) -> requests.Response:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=self.headers,
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise VectorIndexError(f"Vector index request failed: {exc}") from exc
        if response.status_code not in expected:
            detail = response.text[:500]
            raise VectorIndexError(f"Qdrant {method} {path} returned {response.status_code}: {detail}")
        return response

    def ensure_collection(self, dimensions: int) -> None:
        response = self._request(
            "GET",
            f"/collections/{self.collection}",
            expected=(200, 404),
        )
        if response.status_code == 404:
            self._request(
                "PUT",
                f"/collections/{self.collection}",
                {"vectors": {"size": dimensions, "distance": "Cosine"}},
                expected=(200, 201),
            )
        else:
            config = response.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
            current_size = config.get("size") if isinstance(config, dict) else None
            if current_size is not None and int(current_size) != dimensions:
                raise VectorIndexError(
                    f"Collection {self.collection!r} uses {current_size} dimensions, but "
                    f"{settings.embedding_model!r} returned {dimensions}"
                )

        # Qdrant needs payload indexes to evaluate tenant and document filters
        # before vector ranking without scanning the whole shared collection.
        for field_name, field_schema in (
            ("tenant_id", "keyword"),
            ("tribe_id", "keyword"),
            ("owner_id", "keyword"),
            ("document_id", "integer"),
            ("is_private", "bool"),
        ):
            self._request(
                "PUT",
                f"/collections/{self.collection}/index?wait=true",
                {"field_name": field_name, "field_schema": field_schema},
                expected=(200, 201),
            )

    @staticmethod
    def _owner_condition(owner_id: str | None) -> dict[str, Any]:
        if owner_id is None:
            return {"is_null": {"key": "owner_id"}}
        return {"key": "owner_id", "match": {"value": owner_id}}

    @classmethod
    def _authorization_filter(
        cls,
        *,
        owner_id: str | None,
        shared_document_ids: list[int] | None,
        include_unowned: bool,
        tribe_scopes: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any] | None:
        scope_filter: dict[str, Any] | None = None
        tenant_filter: dict[str, Any] | None = None
        if tribe_scopes is not None:
            tenant_ids = sorted({tenant_id for tenant_id, _tribe_id in tribe_scopes})
            scope_filter = (
                {
                    "should": [
                        {
                            "must": [
                                {"key": "tenant_id", "match": {"value": tenant_id}},
                                {"key": "tribe_id", "match": {"value": tribe_id}},
                            ]
                        }
                        for tenant_id, tribe_id in tribe_scopes
                    ]
                }
                if tribe_scopes
                else {"key": "tribe_id", "match": {"value": "__no_authorized_tribe__"}}
            )
            tenant_filter = (
                {"key": "tenant_id", "match": {"any": tenant_ids}}
                if tenant_ids
                else {"key": "tenant_id", "match": {"value": "__no_authorized_tenant__"}}
            )

        conditions: list[dict[str, Any]] = []
        if owner_id is not None:
            owner_condition: dict[str, Any] = cls._owner_condition(owner_id)
            conditions.append(
                {"must": [scope_filter, owner_condition]} if scope_filter is not None else owner_condition
            )
            if scope_filter is not None and tribe_scopes:
                # Points written before Tribe payloads existed remain usable
                # for their owner during the rolling reindex. Requiring both
                # fields to be absent prevents this compatibility path from
                # weakening newly scoped points.
                conditions.append(
                    {
                        "must": [
                            {"is_null": {"key": "tenant_id"}},
                            {"is_null": {"key": "tribe_id"}},
                            owner_condition,
                        ]
                    }
                )
        if scope_filter is not None:
            conditions.append(
                {
                    "must": [
                        scope_filter,
                        {"key": "is_private", "match": {"value": False}},
                    ]
                }
            )
        if shared_document_ids:
            shared_condition: dict[str, Any] = {
                "key": "document_id",
                "match": {"any": shared_document_ids},
            }
            conditions.append(
                {
                    "must": [
                        shared_condition,
                        {"key": "is_private", "match": {"value": False}},
                    ]
                }
                if scope_filter is not None
                else shared_condition
            )
            if scope_filter is not None and tribe_scopes:
                conditions.append(
                    {
                        "must": [
                            {"is_null": {"key": "tenant_id"}},
                            {"is_null": {"key": "tribe_id"}},
                            shared_condition,
                            {"key": "is_private", "match": {"value": False}},
                        ]
                    }
                )
        if include_unowned:
            unowned_conditions = [
                cls._owner_condition(None),
                {"key": "is_private", "match": {"value": False}},
            ]
            if tenant_filter is not None:
                unowned_conditions.insert(0, tenant_filter)
            conditions.append({"must": unowned_conditions})
            if tribe_scopes:
                conditions.append(
                    {
                        "must": [
                            {"is_null": {"key": "tenant_id"}},
                            {"is_null": {"key": "tribe_id"}},
                            cls._owner_condition(None),
                            {"key": "is_private", "match": {"value": False}},
                        ]
                    }
                )
        return {"should": conditions} if conditions else None

    def index_document(self, file_record: Any) -> int:
        """Replace all indexed chunks for one FileRecord and return their count."""
        text = (file_record.ocr_text or "").strip()
        chunks = chunk_text(text)
        if not chunks:
            return 0

        vectors: list[list[float]] = []
        for batch_number, batch in enumerate(
            _embedding_batches(chunks, settings.vector_embedding_batch_tokens),
            start=1,
        ):
            logger.info(
                "Embedding vector-index batch %d for document %s (%d chunks, %d tokens)",
                batch_number,
                file_record.id,
                len(batch),
                sum(max(1, chunk.token_end - chunk.token_start) for chunk in batch),
            )
            vectors.extend(generate_embeddings([chunk.text for chunk in batch]))
        if len(vectors) != len(chunks):
            raise VectorIndexError("Embedding provider returned an unexpected number of vectors")
        self.ensure_collection(len(vectors[0]))

        digest = content_hash(text)
        index_version = hashlib.sha256(
            (
                f"{digest}:{settings.embedding_model}:"
                f"{settings.vector_chunk_tokens}:{settings.vector_chunk_overlap_tokens}"
            ).encode("utf-8")
        ).hexdigest()
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"docuelevate:{file_record.id}:{index_version}:{chunk.index}",
                )
            )
            created_at = getattr(file_record, "created_at", None)
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "document_id": file_record.id,
                        "tenant_id": getattr(file_record, "tenant_id", "default"),
                        "tribe_id": getattr(file_record, "tribe_id", "default-quarantine"),
                        "owner_id": file_record.owner_id,
                        "is_private": bool(getattr(file_record, "is_private", False)),
                        "file_hash": file_record.filehash,
                        "content_hash": digest,
                        "index_version": index_version,
                        "filename": file_record.original_filename,
                        "title": file_record.document_title,
                        "mime_type": file_record.mime_type,
                        "created_at": created_at.isoformat() if created_at else None,
                        "chunk_index": chunk.index,
                        "chunk_count": len(chunks),
                        "token_start": chunk.token_start,
                        "token_end": chunk.token_end,
                        "text": chunk.text,
                    },
                }
            )

        # Keep the last complete index live until every new batch is stored.
        # Stable point IDs make retries idempotent; cleanup happens only after
        # the complete replacement version has been written successfully.
        batch_size = settings.vector_upsert_batch_size
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            self._request(
                "PUT",
                f"/collections/{self.collection}/points?wait=true",
                {"points": batch},
                expected=(200, 201),
            )
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete?wait=true",
            {
                "filter": {
                    "must": [
                        {"key": "document_id", "match": {"value": file_record.id}},
                        self._owner_condition(file_record.owner_id),
                    ],
                    "must_not": [{"key": "index_version", "match": {"value": index_version}}],
                }
            },
        )
        return len(points)

    def delete_documents(self, document_ids: list[int], *, owner_id: str | None) -> None:
        """Delete derived chunks for owner-scoped documents."""
        if not document_ids:
            return
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete?wait=true",
            {
                "filter": {
                    "must": [
                        {"key": "document_id", "match": {"any": document_ids}},
                        self._owner_condition(owner_id),
                    ]
                }
            },
            expected=(200, 404),
        )

    def set_document_privacy(self, document_id: int, *, owner_id: str | None, is_private: bool) -> bool:
        """Update privacy payloads without recomputing document embeddings.

        A missing collection means no vector payload exists yet and is a clean
        no-op, not a privacy failure.
        """
        response = self._request(
            "POST",
            f"/collections/{self.collection}/points/payload?wait=true",
            {
                "payload": {"is_private": bool(is_private)},
                "filter": {
                    "must": [
                        {"key": "document_id", "match": {"value": document_id}},
                        self._owner_condition(owner_id),
                    ]
                },
            },
            expected=(200, 201, 404),
        )
        return response.status_code != 404

    def search(
        self,
        query: str,
        *,
        limit: int,
        score_threshold: float | None = None,
        document_ids: list[int] | None = None,
        owner_id: str | None = None,
        shared_document_ids: list[int] | None = None,
        include_unowned: bool = False,
        tribe_scopes: list[tuple[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        vector = generate_embeddings([query])[0]
        body: dict[str, Any] = {
            "query": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if score_threshold is not None:
            body["score_threshold"] = score_threshold
        authorization_filter = self._authorization_filter(
            owner_id=owner_id,
            shared_document_ids=shared_document_ids,
            include_unowned=include_unowned,
            tribe_scopes=tribe_scopes,
        )
        if document_ids is not None:
            if not document_ids:
                return []
            document_filter = {"key": "document_id", "match": {"any": document_ids}}
            body["filter"] = (
                {"must": [document_filter, authorization_filter]}
                if authorization_filter
                else {"must": [document_filter]}
            )
        elif authorization_filter is not None:
            body["filter"] = authorization_filter

        response = self._request(
            "POST",
            f"/collections/{self.collection}/points/query",
            body,
            expected=(200, 404),
        )
        if response.status_code == 404:
            legacy_body = dict(body)
            legacy_body["vector"] = legacy_body.pop("query")
            response = self._request(
                "POST",
                f"/collections/{self.collection}/points/search",
                legacy_body,
            )
        result = response.json().get("result", [])
        if isinstance(result, dict):
            result = result.get("points", [])
        return result if isinstance(result, list) else []

    def status(self) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/collections/{self.collection}",
            expected=(200, 404),
        )
        if response.status_code == 404:
            return {"available": True, "collection_exists": False, "points_count": 0}
        result = response.json().get("result", {})
        return {
            "available": True,
            "collection_exists": True,
            "points_count": result.get("points_count", 0),
            "status": result.get("status"),
        }
