"""Add detail column to processing_logs table

Revision ID: 006_add_detail_column
Revises: 005_add_saved_searches
Create Date: 2026-03-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_detail_column"
down_revision: Union[str, None] = "005_add_saved_searches"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add detail column to processing_logs table for verbose worker log output."""
    op.add_column("processing_logs", sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove detail column from processing_logs table."""
    op.drop_column("processing_logs", "detail")
