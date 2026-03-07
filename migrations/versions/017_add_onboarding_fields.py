"""Add onboarding fields to user_profiles

Revision ID: 017_add_onboarding_fields
Revises: 016_add_userprofile_billing
Create Date: 2026-03-08

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_add_onboarding_fields"
down_revision: Union[str, None] = "016_add_userprofile_billing"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add onboarding_completed, onboarding_completed_at, contact_email, preferred_destination to user_profiles."""
    op.add_column(
        "user_profiles",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user_profiles",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("contact_email", sa.String(255), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column("preferred_destination", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Remove onboarding columns from user_profiles."""
    op.drop_column("user_profiles", "preferred_destination")
    op.drop_column("user_profiles", "contact_email")
    op.drop_column("user_profiles", "onboarding_completed_at")
    op.drop_column("user_profiles", "onboarding_completed")
