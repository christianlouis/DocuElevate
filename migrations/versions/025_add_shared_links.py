"""Add shared_links table for document sharing with expiring links

Revision ID: 025_add_shared_links
Revises: 024_add_api_tokens
Create Date: 2026-03-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_add_shared_links"
down_revision: Union[str, None] = "024_add_api_tokens"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create shared_links table."""
    op.create_table(
        "shared_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_views", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("password_hash", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_shared_links_id", "shared_links", ["id"])
    op.create_index("ix_shared_links_token", "shared_links", ["token"])
    op.create_index("ix_shared_links_file_id", "shared_links", ["file_id"])
    op.create_index("ix_shared_links_owner_id", "shared_links", ["owner_id"])


def downgrade() -> None:
    """Drop shared_links table."""
    op.drop_index("ix_shared_links_owner_id", "shared_links")
    op.drop_index("ix_shared_links_file_id", "shared_links")
    op.drop_index("ix_shared_links_token", "shared_links")
    op.drop_index("ix_shared_links_id", "shared_links")
    op.drop_table("shared_links")
