"""Add OCR text and AI metadata fields to files table for full-text search

Revision ID: 004_add_search_fields
Revises: 003_add_deduplication_support
Create Date: 2026-02-25

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_search_fields"
down_revision: Union[str, None] = "003_add_deduplication_support"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ocr_text, ai_metadata, and document_title columns to files table."""
    op.add_column("files", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column("files", sa.Column("ai_metadata", sa.Text(), nullable=True))
    op.add_column("files", sa.Column("document_title", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove ocr_text, ai_metadata, and document_title columns from files table."""
    op.drop_column("files", "document_title")
    op.drop_column("files", "ai_metadata")
    op.drop_column("files", "ocr_text")
