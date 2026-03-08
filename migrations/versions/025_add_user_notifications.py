"""Add user notification tables (targets, preferences, in-app inbox)

Revision ID: 025_add_user_notifications
Revises: 024_add_api_tokens
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_add_user_notifications"
down_revision: Union[str, None] = "024_add_api_tokens"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create user_notification_targets, user_notification_preferences, and in_app_notifications tables."""
    op.create_table(
        "user_notification_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_notification_targets_id", "user_notification_targets", ["id"])
    op.create_index("ix_user_notification_targets_owner_id", "user_notification_targets", ["owner_id"])

    op.create_table(
        "user_notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "event_type", "channel_type", "target_id"),
    )
    op.create_index("ix_user_notification_preferences_id", "user_notification_preferences", ["id"])
    op.create_index("ix_user_notification_preferences_owner_id", "user_notification_preferences", ["owner_id"])

    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_in_app_notifications_id", "in_app_notifications", ["id"])
    op.create_index("ix_in_app_notifications_owner_id", "in_app_notifications", ["owner_id"])
    op.create_index("ix_in_app_notifications_is_read", "in_app_notifications", ["is_read"])
    op.create_index("ix_in_app_notifications_created_at", "in_app_notifications", ["created_at"])


def downgrade() -> None:
    """Drop user notification tables."""
    op.drop_index("ix_in_app_notifications_created_at", "in_app_notifications")
    op.drop_index("ix_in_app_notifications_is_read", "in_app_notifications")
    op.drop_index("ix_in_app_notifications_owner_id", "in_app_notifications")
    op.drop_index("ix_in_app_notifications_id", "in_app_notifications")
    op.drop_table("in_app_notifications")

    op.drop_index("ix_user_notification_preferences_owner_id", "user_notification_preferences")
    op.drop_index("ix_user_notification_preferences_id", "user_notification_preferences")
    op.drop_table("user_notification_preferences")

    op.drop_index("ix_user_notification_targets_owner_id", "user_notification_targets")
    op.drop_index("ix_user_notification_targets_id", "user_notification_targets")
    op.drop_table("user_notification_targets")
