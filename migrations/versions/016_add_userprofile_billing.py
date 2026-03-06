"""Add billing cycle and overage columns to user_profiles

Revision ID: 016_add_userprofile_billing
Revises: 015_add_subscription_plans
Create Date: 2026-03-07

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016_add_userprofile_billing"
down_revision: Union[str, None] = "015_add_subscription_plans"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add subscription_billing_cycle, subscription_period_start, allow_overage to user_profiles."""
    op.add_column(
        "user_profiles",
        sa.Column(
            "subscription_billing_cycle",
            sa.String(10),
            nullable=False,
            server_default="monthly",
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column("subscription_period_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("allow_overage", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Remove billing columns from user_profiles."""
    op.drop_column("user_profiles", "allow_overage")
    op.drop_column("user_profiles", "subscription_period_start")
    op.drop_column("user_profiles", "subscription_billing_cycle")
