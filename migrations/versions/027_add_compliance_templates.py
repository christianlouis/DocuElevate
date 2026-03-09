"""Add compliance_templates table for GDPR, HIPAA, SOC2 compliance templates.

Revision ID: 027_add_compliance_templates
Revises: 026_add_scheduled_jobs
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_add_compliance_templates"
down_revision: Union[str, None] = "026_add_scheduled_jobs"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create compliance_templates table."""
    op.create_table(
        "compliance_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_applied"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_compliance_templates_name"),
    )
    op.create_index("ix_compliance_templates_id", "compliance_templates", ["id"])
    op.create_index("ix_compliance_templates_name", "compliance_templates", ["name"])


def downgrade() -> None:
    """Drop compliance_templates table."""
    op.drop_index("ix_compliance_templates_name", "compliance_templates")
    op.drop_index("ix_compliance_templates_id", "compliance_templates")
    op.drop_table("compliance_templates")
