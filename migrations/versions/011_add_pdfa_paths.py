"""Add PDF/A archival variant path columns to files table

Revision ID: 011_add_pdfa_paths
Revises: 010_add_embedding_column
Create Date: 2026-03-02

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_add_pdfa_paths"
down_revision: Union[str, None] = "010_add_embedding_column"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add PDF/A variant path columns to files table."""
    op.add_column("files", sa.Column("original_pdfa_path", sa.String(), nullable=True))
    op.add_column("files", sa.Column("processed_pdfa_path", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove PDF/A variant path columns from files table."""
    op.drop_column("files", "processed_pdfa_path")
    op.drop_column("files", "original_pdfa_path")
