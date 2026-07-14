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
            return

        config = response.json().get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
        current_size = config.get("size") if isinstance(config, dict) else None
        if current_size is not None and int(current_size) != dimensions:
            raise VectorIndexError(
                f"Collection {self.collection!r} uses {current_size} dimensions, but "
                f"{settings.embedding_model!r} returned {dimensions}"
            )

    def index_document(self, file_record: Any) -> int:
        """Replace all indexed chunks for one FileRecord and return their count."""
        text = (file_record.ocr_text or "").strip()
        chunks = chunk_text(text)
        if not chunks:
            return 0

        vectors = generate_embeddings([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise VectorIndexError("Embedding provider returned an unexpected number of vectors")
        self.ensure_collection(len(vectors[0]))

        digest = content_hash(text)
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:{file_record.id}:{digest}:{chunk.index}"))
            created_at = getattr(file_record, "created_at", None)
            points.append(
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "document_id": file_record.id,
                        "owner_id": file_record.owner_id,
                        "file_hash": file_record.filehash,
                        "content_hash": digest,
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

        # Generate every embedding before deleting old points.  A provider
        # outage therefore leaves the last known-good index intact.
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete?wait=true",
            {"filter": {"must": [{"key": "document_id", "match": {"value": file_record.id}}]}},
        )
        self._request(
            "PUT",
            f"/collections/{self.collection}/points?wait=true",
            {"points": points},
            expected=(200, 201),
        )
        return len(points)

    def search(self, query: str, *, limit: int, score_threshold: float | None = None) -> list[dict[str, Any]]:
        vector = generate_embeddings([query])[0]
        body: dict[str, Any] = {
            "query": vector,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if score_threshold is not None:
            body["score_threshold"] = score_threshold

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
