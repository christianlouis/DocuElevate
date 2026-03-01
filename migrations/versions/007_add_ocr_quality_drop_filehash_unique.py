"""Add ocr_quality_score column and drop unique filehash index

Revision ID: 007_add_ocr_quality_drop_filehash_unique
Revises: 006_add_detail_column
Create Date: 2026-03-01

"""

import logging
from typing import Union

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision: str = "007_add_ocr_quality_drop_filehash_unique"
down_revision: Union[str, None] = "006_add_detail_column"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add ocr_quality_score column and drop unique constraint on filehash."""
    # Add ocr_quality_score column for AI-assessed text quality (0-100)
    op.add_column("files", sa.Column("ocr_quality_score", sa.Integer(), nullable=True))

    # Drop unique index on filehash to allow duplicate file records.
    # The filehash column retains a non-unique index for lookups.
    try:
        op.drop_index("ix_files_filehash", table_name="files")
    except Exception as exc:
        logger.debug("Could not drop ix_files_filehash (may not exist): %s", exc)
    try:
        op.create_index("ix_files_filehash", "files", ["filehash"], unique=False)
    except Exception as exc:
        logger.debug("Could not create ix_files_filehash (may already exist): %s", exc)


def downgrade() -> None:
    """Remove ocr_quality_score column and restore unique filehash index."""
    op.drop_column("files", "ocr_quality_score")
