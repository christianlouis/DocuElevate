"""Add legal hold flag to files.

Revision ID: 048_add_file_legal_hold
Revises: 047_add_document_review_items
Create Date: 2026-07-06
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "048_add_file_legal_hold"
down_revision: Union[str, None] = "047_add_document_review_items"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add legal_hold to files."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "files" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("files")}
    if "legal_hold" not in columns:
        op.add_column("files", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default="0"))
    existing_indexes = {index["name"] for index in inspector.get_indexes("files")}
    if "ix_files_legal_hold" not in existing_indexes:
        op.create_index("ix_files_legal_hold", "files", ["legal_hold"])


def downgrade() -> None:
    """Remove legal_hold from files."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "files" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("files")}
    if "ix_files_legal_hold" in existing_indexes:
        op.drop_index("ix_files_legal_hold", table_name="files")
    columns = {column["name"] for column in inspector.get_columns("files")}
    if "legal_hold" in columns:
        op.drop_column("files", "legal_hold")
