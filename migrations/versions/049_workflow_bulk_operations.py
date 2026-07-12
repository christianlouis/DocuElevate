"""Add workflow snapshots and recoverable bulk operations.

Revision ID: 049_workflow_bulk_operations
Revises: 048_add_file_legal_hold
Create Date: 2026-07-12
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "049_workflow_bulk_operations"
down_revision: Union[str, None] = "048_add_file_legal_hold"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("workflow_plan", sa.Text(), nullable=True))
    op.add_column(
        "files",
        sa.Column("workflow_plan_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "bulk_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("completed_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("task_ids", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bulk_operations_owner_id", "bulk_operations", ["owner_id"])
    op.create_index("ix_bulk_operations_action", "bulk_operations", ["action"])
    op.create_index("ix_bulk_operations_state", "bulk_operations", ["state"])
    op.create_index("ix_bulk_operations_created_at", "bulk_operations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_bulk_operations_created_at", table_name="bulk_operations")
    op.drop_index("ix_bulk_operations_state", table_name="bulk_operations")
    op.drop_index("ix_bulk_operations_action", table_name="bulk_operations")
    op.drop_index("ix_bulk_operations_owner_id", table_name="bulk_operations")
    op.drop_table("bulk_operations")
    op.drop_column("files", "workflow_plan_version")
    op.drop_column("files", "workflow_plan")
