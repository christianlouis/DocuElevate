"""Add file_shares table for per-user document sharing and role-based access.

Revision ID: 042_add_file_shares
Revises: 041_add_document_comments_and_annotations
Create Date: 2026-03-22

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "042_add_file_shares"
down_revision: str = "041_add_document_comments_and_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create file_shares table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "file_shares" not in existing_tables:
        op.create_table(
            "file_shares",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("shared_with_user_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("file_id", "shared_with_user_id", name="uq_file_share_file_user"),
        )
        op.create_index("ix_file_shares_id", "file_shares", ["id"])
        op.create_index("ix_file_shares_file_id", "file_shares", ["file_id"])
        op.create_index("ix_file_shares_owner_id", "file_shares", ["owner_id"])
        op.create_index("ix_file_shares_shared_with_user_id", "file_shares", ["shared_with_user_id"])


def downgrade() -> None:
    """Drop file_shares table."""
    op.drop_index("ix_file_shares_shared_with_user_id", table_name="file_shares")
    op.drop_index("ix_file_shares_owner_id", table_name="file_shares")
    op.drop_index("ix_file_shares_file_id", table_name="file_shares")
    op.drop_index("ix_file_shares_id", table_name="file_shares")
    op.drop_table("file_shares")
