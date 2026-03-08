"""Add user_imap_accounts table for per-user IMAP ingestion

Revision ID: 022_add_user_imap_accounts
Revises: 021_add_backup_records
Create Date: 2026-03-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_add_user_imap_accounts"
down_revision: Union[str, None] = "021_add_backup_records"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create user_imap_accounts table for per-user IMAP ingestion."""
    op.create_table(
        "user_imap_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("password", sa.String(1024), nullable=False),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("delete_after_process", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_imap_accounts_id", "user_imap_accounts", ["id"])
    op.create_index("ix_user_imap_accounts_owner_id", "user_imap_accounts", ["owner_id"])


def downgrade() -> None:
    """Drop user_imap_accounts table."""
    op.drop_index("ix_user_imap_accounts_owner_id", "user_imap_accounts")
    op.drop_index("ix_user_imap_accounts_id", "user_imap_accounts")
    op.drop_table("user_imap_accounts")
