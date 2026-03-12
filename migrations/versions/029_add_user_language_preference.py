"""Add preferred_language column to user_profiles for i18n support.

Revision ID: 029_add_user_language_preference
Revises: 028_add_audit_logs
Create Date: 2026-03-09
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "029_add_user_language_preference"
down_revision: Union[str, None] = "028_add_audit_logs"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add preferred_language column to user_profiles table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_profiles" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "preferred_language" not in existing_columns:
        op.add_column(
            "user_profiles",
            sa.Column("preferred_language", sa.String(10), nullable=True, server_default=None),
        )


def downgrade() -> None:
    """Remove preferred_language column from user_profiles table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_profiles" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("user_profiles")}
    if "preferred_language" in existing_columns:
        op.drop_column("user_profiles", "preferred_language")
