"""Add backup_records table for database backup tracking

Revision ID: 021_add_backup_records
Revises: 020_add_subscription_change_pending
Create Date: 2026-03-07
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_add_backup_records"
down_revision: Union[str, None] = "020_add_subscription_change_pending"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create backup_records table."""
    op.create_table(
        "backup_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("local_path", sa.String(1024), nullable=True),
        sa.Column("backup_type", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        sa.Column("remote_destination", sa.String(50), nullable=True),
        sa.Column("remote_path", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )
    op.create_index("ix_backup_records_backup_type", "backup_records", ["backup_type"])
    op.create_index("ix_backup_records_created_at", "backup_records", ["created_at"])


def downgrade() -> None:
    """Drop backup_records table."""
    op.drop_index("ix_backup_records_created_at", "backup_records")
    op.drop_index("ix_backup_records_backup_type", "backup_records")
    op.drop_table("backup_records")
