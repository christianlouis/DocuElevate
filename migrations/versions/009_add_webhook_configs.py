"""Add webhook_configs table for external integrations

Revision ID: 009_add_webhook_configs
Revises: 008_add_performance_indexes
Create Date: 2026-03-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_webhook_configs"
down_revision: Union[str, None] = "008_add_performance_indexes"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create webhook_configs table."""
    op.create_table(
        "webhook_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=True),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop webhook_configs table."""
    op.drop_table("webhook_configs")
