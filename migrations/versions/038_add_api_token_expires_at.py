"""Add expires_at column to api_tokens table.

Allows API tokens to be issued with an optional lifetime.  If ``expires_at``
is set, the token is automatically rejected after that timestamp.

Revision ID: 038_add_api_token_expires_at
Revises: 037_add_user_sessions_and_qr_challenges
Create Date: 2026-03-18
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "038_add_api_token_expires_at"
down_revision: Union[str, None] = "037_add_user_sessions_and_qr_challenges"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add expires_at column to api_tokens (idempotent)."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "api_tokens" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("api_tokens")}
    if "expires_at" not in existing_columns:
        op.add_column(
            "api_tokens",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Remove expires_at column from api_tokens."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "api_tokens" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("api_tokens")}
    if "expires_at" in existing_columns:
        op.drop_column("api_tokens", "expires_at")
