"""Reconcile the canonical file privacy flag into derived search stores."""

from __future__ import annotations

import json
import logging

from app.celery_app import celery
from app.config import settings
from app.database import SessionLocal
from app.models import FileRecord

logger = logging.getLogger(__name__)


@celery.task(name="reconcile_file_privacy")
def reconcile_file_privacy(file_id: int) -> dict:
    with SessionLocal() as db:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            return {"status": "skipped", "detail": "File not found"}

        metadata = {}
        if file_record.ai_metadata:
            try:
                parsed = json.loads(file_record.ai_metadata)
                metadata = parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        from app.utils.meilisearch_client import index_document

        meilisearch_updated = index_document(file_record, file_record.ocr_text or "", metadata)
        vector_updated = False
        if settings.vector_index_enabled:
            from app.utils.vector_index import QdrantVectorIndex

            vector_updated = QdrantVectorIndex().set_document_privacy(
                file_record.id,
                owner_id=file_record.owner_id,
                is_private=file_record.is_private,
            )

        logger.info(
            "Reconciled file privacy: file_id=%s is_private=%s meilisearch=%s vector=%s",
            file_id,
            file_record.is_private,
            meilisearch_updated,
            vector_updated,
        )
        return {
            "status": "success",
            "file_id": file_id,
            "is_private": file_record.is_private,
            "meilisearch_updated": meilisearch_updated,
            "vector_updated": vector_updated,
        }
