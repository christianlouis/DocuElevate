"""Add local_users table and billing columns

Revision ID: 018_add_local_users_and_billing
Revises: 017_add_onboarding_fields, 017_add_pipelines
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_add_local_users_and_billing"
down_revision: Union[str, tuple] = ("017_add_onboarding_fields", "017_add_pipelines")
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create local_users table and add billing columns."""
    op.create_table(
        "local_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("email_verification_token", sa.String(128), nullable=True),
        sa.Column("email_verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_reset_token", sa.String(128), nullable=True),
        sa.Column("password_reset_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.add_column("user_profiles", sa.Column("stripe_customer_id", sa.String(64), nullable=True))
    op.add_column("subscription_plans", sa.Column("stripe_price_id_monthly", sa.String(128), nullable=True))
    op.add_column("subscription_plans", sa.Column("stripe_price_id_yearly", sa.String(128), nullable=True))


def downgrade() -> None:
    """Reverse the migration."""
    op.drop_column("subscription_plans", "stripe_price_id_yearly")
    op.drop_column("subscription_plans", "stripe_price_id_monthly")
    op.drop_column("user_profiles", "stripe_customer_id")
    op.drop_table("local_users")
