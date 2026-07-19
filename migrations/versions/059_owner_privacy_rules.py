"""Add owner privacy rules and decision audit.

Revision ID: 059_owner_privacy_rules
Revises: 058_add_file_private_flag
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "059_owner_privacy_rules"
down_revision: Union[str, None] = "058_add_file_private_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    file_columns = {column["name"] for column in inspector.get_columns("files")}
    if "privacy_manual_override" not in file_columns:
        op.add_column("files", sa.Column("privacy_manual_override", sa.Boolean(), nullable=True))

    tables = set(inspector.get_table_names())
    if "privacy_rules" not in tables:
        op.create_table(
            "privacy_rules",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("rule_type", sa.String(length=50), nullable=False),
            sa.Column("pattern", sa.String(length=1000), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("case_sensitive", sa.Boolean(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("policy_version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_id", "name", name="uq_privacy_rules_owner_name"),
        )
        op.create_index("ix_privacy_rules_id", "privacy_rules", ["id"])
        op.create_index("ix_privacy_rules_owner_id", "privacy_rules", ["owner_id"])

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "privacy_decision_audits" not in tables:
        op.create_table(
            "privacy_decision_audits",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("rule_id", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False),
            sa.Column("is_private", sa.Boolean(), nullable=False),
            sa.Column("policy_version", sa.Integer(), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["rule_id"], ["privacy_rules.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_privacy_decision_audits_id", "privacy_decision_audits", ["id"])
        op.create_index("ix_privacy_decision_audits_file_id", "privacy_decision_audits", ["file_id"])
        op.create_index("ix_privacy_decision_audits_owner_id", "privacy_decision_audits", ["owner_id"])
        op.create_index("ix_privacy_decision_audits_rule_id", "privacy_decision_audits", ["rule_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "privacy_decision_audits" in tables:
        op.drop_table("privacy_decision_audits")
    if "privacy_rules" in tables:
        op.drop_table("privacy_rules")
    file_columns = {column["name"] for column in inspector.get_columns("files")}
    if "privacy_manual_override" in file_columns:
        op.drop_column("files", "privacy_manual_override")
