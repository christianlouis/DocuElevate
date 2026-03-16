"""Add classification_rules table for custom document classification rules.

Revision ID: 037_add_classification_rules
Revises: 036_add_document_translation_fields
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_add_classification_rules"
down_revision: Union[str, None] = "036_add_document_translation_fields"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create classification_rules table."""
    op.create_table(
        "classification_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("pattern", sa.String(1000), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_classification_rules_owner_name"),
    )
    op.create_index("ix_classification_rules_id", "classification_rules", ["id"])
    op.create_index("ix_classification_rules_owner_id", "classification_rules", ["owner_id"])
    op.create_index("ix_classification_rules_category", "classification_rules", ["category"])


def downgrade() -> None:
    """Drop classification_rules table."""
    op.drop_index("ix_classification_rules_category", "classification_rules")
    op.drop_index("ix_classification_rules_owner_id", "classification_rules")
    op.drop_index("ix_classification_rules_id", "classification_rules")
    op.drop_table("classification_rules")
