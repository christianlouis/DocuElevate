"""Add performance indexes for common query patterns

Revision ID: 008_add_performance_indexes
Revises: 007_add_ocr_quality_drop_filehash_unique
Create Date: 2026-03-01

"""

from typing import Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "008_add_performance_indexes"
down_revision: Union[str, None] = "007_add_ocr_quality_drop_filehash_unique"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create performance indexes for file listing, filtering, and log retrieval.

    Uses ``CREATE INDEX IF NOT EXISTS`` to remain idempotent — safe to run
    even if the indexes were previously created by ``Base.metadata.create_all()``
    or an earlier manual migration.
    """
    conn = op.get_bind()
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_files_created_at ON files (created_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_files_mime_type ON files (mime_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_processing_logs_file_id ON processing_logs (file_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_processing_logs_timestamp ON processing_logs (timestamp)"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_file_processing_steps_status ON file_processing_steps (status)")
    )


def downgrade() -> None:
    """Drop performance indexes."""
    op.drop_index("ix_file_processing_steps_status", table_name="file_processing_steps")
    op.drop_index("ix_processing_logs_timestamp", table_name="processing_logs")
    op.drop_index("ix_processing_logs_file_id", table_name="processing_logs")
    op.drop_index("ix_files_mime_type", table_name="files")
    op.drop_index("ix_files_created_at", table_name="files")
