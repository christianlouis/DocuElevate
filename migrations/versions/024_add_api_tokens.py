"""Add api_tokens table for personal API token authentication

Revision ID: 024_add_api_tokens
Revises: 023_add_user_integrations
Create Date: 2026-03-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_add_api_tokens"
down_revision: Union[str, None] = "023_add_user_integrations"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create api_tokens table."""
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(45), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_api_tokens_id", "api_tokens", ["id"])
    op.create_index("ix_api_tokens_owner_id", "api_tokens", ["owner_id"])
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"])


def downgrade() -> None:
    """Drop api_tokens table."""
    op.drop_index("ix_api_tokens_token_hash", "api_tokens")
    op.drop_index("ix_api_tokens_owner_id", "api_tokens")
    op.drop_index("ix_api_tokens_id", "api_tokens")
    op.drop_table("api_tokens")
