"""Add the hard tenant and mandatory Tribe document boundary.

Revision ID: 060_add_tenant_tribe_foundation
Revises: 059_owner_privacy_rules
"""

from __future__ import annotations

import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "060_add_tenant_tribe_foundation"
down_revision: Union[str, None] = "059_owner_privacy_rules"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "default"
QUARANTINE_TRIBE_ID = "default-quarantine"


def _personal_tribe_id(owner_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"docuelevate:tribe:{DEFAULT_TENANT_ID}:{owner_id}"))


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tribes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tribes_tenant_name"),
    )
    op.create_index("ix_tribes_tenant_id", "tribes", ["tenant_id"])
    op.create_table(
        "tribe_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("tribe_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="member", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tribe_id"], ["tribes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tribe_id", "user_id", name="uq_tribe_memberships_tribe_user"),
    )
    op.create_index("ix_tribe_memberships_id", "tribe_memberships", ["id"])
    op.create_index("ix_tribe_memberships_tenant_id", "tribe_memberships", ["tenant_id"])
    op.create_index("ix_tribe_memberships_tribe_id", "tribe_memberships", ["tribe_id"])
    op.create_index("ix_tribe_memberships_user_id", "tribe_memberships", ["user_id"])

    op.execute(
        sa.text("INSERT INTO tenants (id, name) VALUES (:id, :name)").bindparams(
            id=DEFAULT_TENANT_ID, name="Default tenant"
        )
    )
    op.execute(
        sa.text("INSERT INTO tribes (id, tenant_id, name) VALUES (:id, :tenant, :name)").bindparams(
            id=QUARANTINE_TRIBE_ID, tenant=DEFAULT_TENANT_ID, name="Unassigned intake quarantine"
        )
    )

    op.add_column(
        "files",
        sa.Column("tenant_id", sa.String(length=64), server_default=DEFAULT_TENANT_ID, nullable=False),
    )
    op.add_column(
        "files",
        sa.Column("tribe_id", sa.String(length=64), server_default=QUARANTINE_TRIBE_ID, nullable=False),
    )

    bind = op.get_bind()
    owners = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT owner_id FROM files WHERE owner_id IS NOT NULL"))]
    profile_owners = [row[0] for row in bind.execute(sa.text("SELECT user_id FROM user_profiles"))]
    share_recipients = [row[0] for row in bind.execute(sa.text("SELECT DISTINCT shared_with_user_id FROM file_shares"))]
    for owner_id in sorted(set(owners + profile_owners + share_recipients)):
        tribe_id = _personal_tribe_id(owner_id)
        bind.execute(
            sa.text("INSERT INTO tribes (id, tenant_id, name) VALUES (:id, :tenant, :name)"),
            {"id": tribe_id, "tenant": DEFAULT_TENANT_ID, "name": f"Personal space for {owner_id}"},
        )
        bind.execute(
            sa.text(
                "INSERT INTO tribe_memberships (tenant_id, tribe_id, user_id, role) "
                "VALUES (:tenant, :tribe, :user, 'admin')"
            ),
            {"tenant": DEFAULT_TENANT_ID, "tribe": tribe_id, "user": owner_id},
        )
        bind.execute(
            sa.text("UPDATE files SET tribe_id=:tribe WHERE owner_id=:owner"),
            {"tribe": tribe_id, "owner": owner_id},
        )

    op.create_index("ix_files_tenant_id", "files", ["tenant_id"])
    op.create_index("ix_files_tribe_id", "files", ["tribe_id"])
    with op.batch_alter_table("files") as batch_op:
        batch_op.create_foreign_key("fk_files_tenant_id", "tenants", ["tenant_id"], ["id"])
        batch_op.create_foreign_key("fk_files_tribe_id", "tribes", ["tribe_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_constraint("fk_files_tribe_id", type_="foreignkey")
        batch_op.drop_constraint("fk_files_tenant_id", type_="foreignkey")
    op.drop_index("ix_files_tribe_id", table_name="files")
    op.drop_index("ix_files_tenant_id", table_name="files")
    op.drop_column("files", "tribe_id")
    op.drop_column("files", "tenant_id")
    op.drop_table("tribe_memberships")
    op.drop_table("tribes")
    op.drop_table("tenants")
