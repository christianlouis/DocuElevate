"""Add embedding column to files table for document similarity

Revision ID: 009_add_embedding_column
Revises: 008_add_performance_indexes
Create Date: 2026-03-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_embedding_column"
down_revision: Union[str, None] = "008_add_performance_indexes"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add embedding column to files table for storing text embedding vectors."""
    op.add_column("files", sa.Column("embedding", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove embedding column from files table."""
    op.drop_column("files", "embedding")
