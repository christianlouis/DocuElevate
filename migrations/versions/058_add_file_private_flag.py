"""Add owner-controlled document privacy.

Revision ID: 058_add_file_private_flag
Revises: 057_knowledge_research_jobs
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "058_add_file_private_flag"
down_revision: Union[str, None] = "057_knowledge_research_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("files")}
    indexes = {index["name"] for index in inspector.get_indexes("files")}
    if "is_private" not in columns:
        op.add_column(
            "files",
            sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "ix_files_is_private" not in indexes:
        op.create_index("ix_files_is_private", "files", ["is_private"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("files")}
    columns = {column["name"] for column in inspector.get_columns("files")}
    if "ix_files_is_private" in indexes:
        op.drop_index("ix_files_is_private", table_name="files")
    if "is_private" in columns:
        op.drop_column("files", "is_private")
