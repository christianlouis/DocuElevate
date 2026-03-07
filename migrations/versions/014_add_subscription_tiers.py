"""Add subscription_tier column to user_profiles

Revision ID: 014_add_subscription_tiers
Revises: 013_add_user_profiles
Create Date: 2026-03-06

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014_add_subscription_tiers"
down_revision: Union[str, None] = "013_add_user_profiles"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add subscription_tier column to user_profiles."""
    op.add_column(
        "user_profiles",
        sa.Column("subscription_tier", sa.String(50), nullable=True, server_default="free"),
    )


def downgrade() -> None:
    """Remove subscription_tier column from user_profiles."""
    op.drop_column("user_profiles", "subscription_tier")
