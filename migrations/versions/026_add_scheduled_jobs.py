"""Add scheduled_jobs table for admin-managed batch processing schedules.

Revision ID: 026_add_scheduled_jobs
Revises: 025_add_user_notifications
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_add_scheduled_jobs"
down_revision: Union[str, None] = "025_add_user_notifications"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create scheduled_jobs table."""
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("schedule_type", sa.String(20), nullable=False, server_default="cron"),
        sa.Column("cron_minute", sa.String(50), nullable=False, server_default="0"),
        sa.Column("cron_hour", sa.String(50), nullable=False, server_default="*"),
        sa.Column("cron_day_of_week", sa.String(50), nullable=False, server_default="*"),
        sa.Column("cron_day_of_month", sa.String(50), nullable=False, server_default="*"),
        sa.Column("cron_month_of_year", sa.String(50), nullable=False, server_default="*"),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(20), nullable=True),
        sa.Column("last_run_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_scheduled_jobs_name"),
    )
    op.create_index("ix_scheduled_jobs_id", "scheduled_jobs", ["id"])
    op.create_index("ix_scheduled_jobs_name", "scheduled_jobs", ["name"])


def downgrade() -> None:
    """Drop scheduled_jobs table."""
    op.drop_index("ix_scheduled_jobs_name", "scheduled_jobs")
    op.drop_index("ix_scheduled_jobs_id", "scheduled_jobs")
    op.drop_table("scheduled_jobs")
