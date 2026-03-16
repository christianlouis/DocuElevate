"""Add preferred_theme and avatar_data columns to user_profiles.

Revision ID: 034_add_user_profile_settings
Revises: 033_add_imap_ingestion_profiles
Create Date: 2026-03-12
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_add_user_profile_settings"
down_revision: Union[str, None] = "033_add_imap_ingestion_profiles"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add preferred_theme and avatar_data columns to user_profiles table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_profiles" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "preferred_theme" not in existing_columns:
        op.add_column(
            "user_profiles",
            sa.Column("preferred_theme", sa.String(10), nullable=True, server_default=None),
        )
    if "avatar_data" not in existing_columns:
        op.add_column(
            "user_profiles",
            sa.Column("avatar_data", sa.Text, nullable=True, server_default=None),
        )


def downgrade() -> None:
    """Remove preferred_theme and avatar_data columns from user_profiles table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_profiles" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "avatar_data" in existing_columns:
        op.drop_column("user_profiles", "avatar_data")
    if "preferred_theme" in existing_columns:
        op.drop_column("user_profiles", "preferred_theme")
