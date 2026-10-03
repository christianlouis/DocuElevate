"""Scope automation hooks to their creating principal."""

from alembic import op
import sqlalchemy as sa

revision = "064_scope_automation_hooks"
down_revision = "063_add_backup_error_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("automation_hooks", sa.Column("owner_id", sa.String(), nullable=True))
    op.execute("UPDATE automation_hooks SET owner_id = '' WHERE owner_id IS NULL")
    op.alter_column("automation_hooks", "owner_id", nullable=False)
    op.create_index("ix_automation_hooks_owner_id", "automation_hooks", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_hooks_owner_id", table_name="automation_hooks")
    op.drop_column("automation_hooks", "owner_id")
