"""Add user_integrations table for generic multi-tenant source/destination integrations

Revision ID: 023_add_user_integrations
Revises: 022_add_user_imap_accounts
Create Date: 2026-03-08
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_add_user_integrations"
down_revision: Union[str, None] = "022_add_user_imap_accounts"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create user_integrations table."""
    op.create_table(
        "user_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("integration_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_integrations_id", "user_integrations", ["id"])
    op.create_index("ix_user_integrations_owner_id", "user_integrations", ["owner_id"])
    op.create_index("ix_user_integrations_direction", "user_integrations", ["direction"])
    op.create_index("ix_user_integrations_integration_type", "user_integrations", ["integration_type"])


def downgrade() -> None:
    """Drop user_integrations table."""
    op.drop_index("ix_user_integrations_integration_type", "user_integrations")
    op.drop_index("ix_user_integrations_direction", "user_integrations")
    op.drop_index("ix_user_integrations_owner_id", "user_integrations")
    op.drop_index("ix_user_integrations_id", "user_integrations")
    op.drop_table("user_integrations")
