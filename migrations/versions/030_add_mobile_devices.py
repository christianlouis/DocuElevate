"""Add mobile_devices table for push notification device registration.

Revision ID: 030_add_mobile_devices
Revises: 029_add_user_language_preference
Create Date: 2026-03-10
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_add_mobile_devices"
down_revision: Union[str, None] = "029_add_user_language_preference"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create mobile_devices table."""
    op.create_table(
        "mobile_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("platform", sa.String(20), nullable=False, server_default="ios"),
        sa.Column("push_token", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "push_token", name="uq_mobile_device_owner_token"),
    )
    op.create_index("ix_mobile_devices_id", "mobile_devices", ["id"])
    op.create_index("ix_mobile_devices_owner_id", "mobile_devices", ["owner_id"])


def downgrade() -> None:
    """Drop mobile_devices table."""
    op.drop_index("ix_mobile_devices_owner_id", table_name="mobile_devices")
    op.drop_index("ix_mobile_devices_id", table_name="mobile_devices")
    op.drop_table("mobile_devices")
