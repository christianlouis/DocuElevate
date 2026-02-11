"""Add original_file_path and processed_file_path to FileRecord

Revision ID: 002_add_file_paths
Revises: 001_file_processing_steps
Create Date: 2026-02-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_file_paths"
down_revision: Union[str, None] = "001_file_processing_steps"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add original_file_path and processed_file_path columns to files table."""
    op.add_column("files", sa.Column("original_file_path", sa.String(), nullable=True))
    op.add_column("files", sa.Column("processed_file_path", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove original_file_path and processed_file_path columns from files table."""
    op.drop_column("files", "processed_file_path")
    op.drop_column("files", "original_file_path")
