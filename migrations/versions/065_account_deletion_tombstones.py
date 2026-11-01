"""Add durable account-deletion fencing state."""
import sqlalchemy as sa
from alembic import op

revision = "065_account_deletion_tombstones"
down_revision = "064_scope_automation_hooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_tombstones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="deleting"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("cleanup_manifest", sa.Text(), nullable=True),
        sa.Column("external_references", sa.Text(), nullable=True),
        sa.UniqueConstraint("owner_id", name="uq_account_deletion_owner"),
    )
    op.create_index("ix_account_deletion_tombstones_owner_id", "account_deletion_tombstones", ["owner_id"])
    op.create_index("ix_account_deletion_tombstones_status", "account_deletion_tombstones", ["status"])
    op.create_table("provider_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner_id", "provider", name="uq_provider_grant_owner_provider"))
    op.create_index("ix_provider_grants_owner_id", "provider_grants", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_provider_grants_owner_id", table_name="provider_grants")
    op.drop_table("provider_grants")
    op.drop_index("ix_account_deletion_tombstones_status", table_name="account_deletion_tombstones")
    op.drop_index("ix_account_deletion_tombstones_owner_id", table_name="account_deletion_tombstones")
    op.drop_table("account_deletion_tombstones")
