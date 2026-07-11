"""Add webhook delivery attempts table.

Revision ID: 046_add_webhook_delivery_attempts
Revises: 045_add_pipeline_owner_name_unique
Create Date: 2026-07-06
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "046_add_webhook_delivery_attempts"
down_revision: Union[str, None] = "045_add_pipeline_owner_name_unique"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create persisted outbound webhook delivery attempts."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "webhook_delivery_attempts" in inspector.get_table_names():
        return

    op.create_table(
        "webhook_delivery_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("webhook_config_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_delivery_attempts_id", "webhook_delivery_attempts", ["id"])
    op.create_index(
        "ix_webhook_delivery_attempts_webhook_config_id", "webhook_delivery_attempts", ["webhook_config_id"]
    )
    op.create_index("ix_webhook_delivery_attempts_task_id", "webhook_delivery_attempts", ["task_id"])
    op.create_index("ix_webhook_delivery_attempts_event", "webhook_delivery_attempts", ["event"])
    op.create_index("ix_webhook_delivery_attempts_status", "webhook_delivery_attempts", ["status"])


def downgrade() -> None:
    """Drop persisted outbound webhook delivery attempts."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "webhook_delivery_attempts" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("webhook_delivery_attempts")}
    for index_name in (
        "ix_webhook_delivery_attempts_status",
        "ix_webhook_delivery_attempts_event",
        "ix_webhook_delivery_attempts_task_id",
        "ix_webhook_delivery_attempts_webhook_config_id",
        "ix_webhook_delivery_attempts_id",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="webhook_delivery_attempts")
    op.drop_table("webhook_delivery_attempts")
