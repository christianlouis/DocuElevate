"""Add multi-user support: owner_id column on files table

Revision ID: 012_add_multi_user_support
Revises: 011_add_pdfa_paths
Create Date: 2026-03-05

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_multi_user_support"
down_revision: Union[str, None] = "011_add_pdfa_paths"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add owner_id column to files table for multi-user document isolation."""
    op.add_column("files", sa.Column("owner_id", sa.String(255), nullable=True))
    op.create_index("ix_files_owner_id", "files", ["owner_id"])


def downgrade() -> None:
    """Remove owner_id column from files table."""
    op.drop_index("ix_files_owner_id", table_name="files")
    op.drop_column("files", "owner_id")
