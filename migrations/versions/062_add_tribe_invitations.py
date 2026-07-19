"""Add revocable, auditable Tribe invitations.

Revision ID: 062_add_tribe_invitations
Revises: 061_encrypt_sensitive_settings_audit
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "062_add_tribe_invitations"
down_revision: Union[str, None] = "061_encrypt_sensitive_settings_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tribe_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tribe_id", sa.String(length=64), nullable=False),
        sa.Column("invitee_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="member", nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=False),
        sa.Column("accepted_by", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in (
        "id",
        "tenant_id",
        "tribe_id",
        "invitee_id",
        "token_hash",
        "invited_by",
        "accepted_by",
        "expires_at",
    ):
        op.create_index(f"ix_tribe_invitations_{column}", "tribe_invitations", [column])


def downgrade() -> None:
    for column in (
        "expires_at",
        "accepted_by",
        "invited_by",
        "token_hash",
        "invitee_id",
        "tribe_id",
        "tenant_id",
        "id",
    ):
        op.drop_index(f"ix_tribe_invitations_{column}", table_name="tribe_invitations")
    op.drop_table("tribe_invitations")
