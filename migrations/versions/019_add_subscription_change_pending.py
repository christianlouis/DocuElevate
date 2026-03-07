"""Add pending subscription-change columns to user_profiles

Revision ID: 019_add_subscription_change_pending
Revises: 018_add_local_users_and_billing
Create Date: 2026-03-07
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_add_subscription_change_pending"
down_revision: Union[str, None] = "018_add_local_users_and_billing"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add subscription_change_pending_tier and subscription_change_pending_date columns."""
    op.add_column(
        "user_profiles",
        sa.Column("subscription_change_pending_tier", sa.String(50), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("subscription_change_pending_date", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove pending subscription-change columns."""
    op.drop_column("user_profiles", "subscription_change_pending_date")
    op.drop_column("user_profiles", "subscription_change_pending_tier")
