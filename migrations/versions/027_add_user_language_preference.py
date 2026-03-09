"""Add preferred_language column to user_profiles for i18n support.

Revision ID: 027_add_user_language_preference
Revises: 026_add_scheduled_jobs
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_add_user_language_preference"
down_revision: Union[str, None] = "026_add_scheduled_jobs"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add preferred_language column to user_profiles table."""
    op.add_column(
        "user_profiles",
        sa.Column("preferred_language", sa.String(10), nullable=True, server_default=None),
    )


def downgrade() -> None:
    """Remove preferred_language column from user_profiles table."""
    op.drop_column("user_profiles", "preferred_language")
