"""Add automation_hooks table for Zapier / Make.com webhook subscriptions.

Revision ID: 037_add_automation_hooks
Revises: 036_add_document_translation_fields
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_add_automation_hooks"
down_revision: Union[str, None] = "036_add_document_translation_fields"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create automation_hooks table."""
    op.create_table(
        "automation_hooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column("secret", sa.String(), nullable=True),
        sa.Column("events", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("hook_type", sa.String(50), nullable=False, server_default="generic"),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_hooks_id", "automation_hooks", ["id"])


def downgrade() -> None:
    """Drop automation_hooks table."""
    op.drop_index("ix_automation_hooks_id", "automation_hooks")
    op.drop_table("automation_hooks")
