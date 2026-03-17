"""Add user_sessions and qr_login_challenges tables.

Adds server-side session tracking (user_sessions) for the "log off
everywhere" feature and per-session revocation, and QR login challenges
(qr_login_challenges) for secure mobile app authentication via QR code.

Revision ID: 037_add_user_sessions_and_qr_challenges
Revises: 036_add_document_translation_fields
Create Date: 2026-03-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_add_user_sessions_and_qr_challenges"
down_revision: Union[str, None] = "036_add_document_translation_fields"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create user_sessions and qr_login_challenges tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "user_sessions" not in existing_tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_token", sa.String(128), nullable=False, unique=True, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column("device_info", sa.String(255), nullable=True),
            sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "qr_login_challenges" not in existing_tables:
        op.create_table(
            "qr_login_challenges",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("challenge_token", sa.String(128), nullable=False, unique=True, index=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("is_claimed", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_by_ip", sa.String(45), nullable=True),
            sa.Column("claimed_by_ip", sa.String(45), nullable=True),
            sa.Column("device_name", sa.String(255), nullable=True),
            sa.Column("issued_token_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    """Drop user_sessions and qr_login_challenges tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "qr_login_challenges" in existing_tables:
        op.drop_table("qr_login_challenges")

    if "user_sessions" in existing_tables:
        op.drop_table("user_sessions")
