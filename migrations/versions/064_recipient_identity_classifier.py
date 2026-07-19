"""Add Tribe-scoped recipient identities and explainable decisions.

Revision ID: 064_recipient_identity_classifier
Revises: 063_add_backup_error_detail
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "064_recipient_identity_classifier"
down_revision: Union[str, None] = "063_add_backup_error_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipient_identity_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tribe_id", sa.String(length=64), nullable=False),
        sa.Column("profile_type", sa.String(length=20), server_default="person", nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("user_ids", sa.Text(), server_default="[]", nullable=False),
        sa.Column("aliases", sa.Text(), server_default="[]", nullable=False),
        sa.Column("postal_addresses", sa.Text(), server_default="[]", nullable=False),
        sa.Column("email_addresses", sa.Text(), server_default="[]", nullable=False),
        sa.Column("identifiers", sa.Text(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tribe_id", "display_name", name="uq_recipient_profiles_tribe_name"),
    )
    for column in ("id", "tenant_id", "tribe_id", "is_active", "created_by"):
        op.create_index(f"ix_recipient_identity_profiles_{column}", "recipient_identity_profiles", [column])

    op.create_table(
        "recipient_routing_policies",
        sa.Column("tribe_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("auto_assign_threshold", sa.Integer(), server_default="80", nullable=False),
        sa.Column("review_threshold", sa.Integer(), server_default="45", nullable=False),
        sa.Column("minimum_margin", sa.Integer(), server_default="15", nullable=False),
        sa.Column("ai_fallback_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("ai_model", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tribe_id"),
    )
    op.create_index("ix_recipient_routing_policies_tenant_id", "recipient_routing_policies", ["tenant_id"])
    op.create_index("ix_recipient_routing_policies_updated_by", "recipient_routing_policies", ["updated_by"])

    op.create_table(
        "document_recipient_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tribe_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("recipient_user_ids", sa.Text(), server_default="[]", nullable=False),
        sa.Column("matched_profile_ids", sa.Text(), server_default="[]", nullable=False),
        sa.Column("candidates", sa.Text(), server_default="[]", nullable=False),
        sa.Column("evidence", sa.Text(), server_default="[]", nullable=False),
        sa.Column("confidence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("strategy", sa.String(length=32), server_default="deterministic", nullable=False),
        sa.Column("classifier_version", sa.String(length=32), server_default="recipient-v1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id"),
    )
    for column in ("id", "file_id", "tenant_id", "tribe_id", "status"):
        op.create_index(f"ix_document_recipient_decisions_{column}", "document_recipient_decisions", [column])


def downgrade() -> None:
    op.drop_table("document_recipient_decisions")
    op.drop_table("recipient_routing_policies")
    op.drop_table("recipient_identity_profiles")
