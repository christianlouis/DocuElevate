"""Add is_complimentary column to user_profiles

Revision ID: 019_add_is_complimentary
Revises: 018_add_local_users_and_billing
Create Date: 2026-03-07

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_add_is_complimentary"
down_revision: Union[str, None] = "018_add_local_users_and_billing"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add is_complimentary column to user_profiles."""
    op.add_column(
        "user_profiles",
        sa.Column("is_complimentary", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Remove is_complimentary column from user_profiles."""
    op.drop_column("user_profiles", "is_complimentary")
