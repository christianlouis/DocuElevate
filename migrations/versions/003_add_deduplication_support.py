"""Add deduplication support with is_duplicate and duplicate_of_id fields

Revision ID: 003_add_deduplication_support
Revises: 002_add_file_paths
Create Date: 2026-02-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_deduplication_support"
down_revision: Union[str, None] = "002_add_file_paths"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add is_duplicate and duplicate_of_id columns to files table."""
    # Add is_duplicate column with default False
    op.add_column("files", sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="0"))
    
    # Add duplicate_of_id column as foreign key to self
    op.add_column("files", sa.Column("duplicate_of_id", sa.Integer(), nullable=True))
    
    # Create index on is_duplicate for efficient filtering
    op.create_index("ix_files_is_duplicate", "files", ["is_duplicate"])
    
    # Create foreign key relationship
    op.create_foreign_key("fk_files_duplicate_of_id", "files", "files", ["duplicate_of_id"], ["id"])


def downgrade() -> None:
    """Remove is_duplicate and duplicate_of_id columns from files table."""
    # Drop foreign key
    op.drop_constraint("fk_files_duplicate_of_id", "files", type_="foreignkey")
    
    # Drop index
    op.drop_index("ix_files_is_duplicate", table_name="files")
    
    # Drop columns
    op.drop_column("files", "duplicate_of_id")
    op.drop_column("files", "is_duplicate")
