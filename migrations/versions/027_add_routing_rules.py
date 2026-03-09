"""Add pipeline_routing_rules table for conditional document routing.

Revision ID: 027_add_routing_rules
Revises: 026_add_scheduled_jobs
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_add_routing_rules"
down_revision: Union[str, None] = "026_add_scheduled_jobs"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create pipeline_routing_rules table."""
    op.create_table(
        "pipeline_routing_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("field", sa.String(255), nullable=False),
        sa.Column("operator", sa.String(50), nullable=False),
        sa.Column("value", sa.String(1024), nullable=False),
        sa.Column("target_pipeline_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["target_pipeline_id"], ["pipelines.id"]),
    )
    op.create_index("ix_routing_rules_id", "pipeline_routing_rules", ["id"])
    op.create_index("ix_routing_rules_owner_id", "pipeline_routing_rules", ["owner_id"])
    op.create_index("ix_routing_rules_target_pipeline_id", "pipeline_routing_rules", ["target_pipeline_id"])


def downgrade() -> None:
    """Drop pipeline_routing_rules table."""
    op.drop_index("ix_routing_rules_target_pipeline_id", "pipeline_routing_rules")
    op.drop_index("ix_routing_rules_owner_id", "pipeline_routing_rules")
    op.drop_index("ix_routing_rules_id", "pipeline_routing_rules")
    op.drop_table("pipeline_routing_rules")
