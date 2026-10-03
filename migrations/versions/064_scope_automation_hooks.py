"""Scope automation hooks to their creating principal."""

import sqlalchemy as sa
from alembic import op

revision = "064_scope_automation_hooks"
down_revision = "063_add_backup_error_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("automation_hooks", sa.Column("owner_id", sa.String(), nullable=True))
    op.execute("UPDATE automation_hooks SET owner_id = '' WHERE owner_id IS NULL")
    # SQLite does not support ALTER COLUMN directly; batch mode rebuilds the
    # table there while retaining native ALTER behavior on other databases.
    with op.batch_alter_table("automation_hooks") as batch_op:
        batch_op.alter_column("owner_id", nullable=False)
    op.create_index("ix_automation_hooks_owner_id", "automation_hooks", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_automation_hooks_owner_id", table_name="automation_hooks")
    op.drop_column("automation_hooks", "owner_id")
