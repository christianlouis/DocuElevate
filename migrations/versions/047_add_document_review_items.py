"""Add document review queue table.

Revision ID: 047_add_document_review_items
Revises: 046_add_webhook_delivery_attempts
Create Date: 2026-07-06
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "047_add_document_review_items"
down_revision: Union[str, None] = "046_add_webhook_delivery_attempts"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create document review queue table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "document_review_items" in inspector.get_table_names():
        return

    op.create_table(
        "document_review_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_review_items_id", "document_review_items", ["id"])
    op.create_index("ix_document_review_items_file_id", "document_review_items", ["file_id"])
    op.create_index("ix_document_review_items_status", "document_review_items", ["status"])
    op.create_index("ix_document_review_items_created_by", "document_review_items", ["created_by"])


def downgrade() -> None:
    """Drop document review queue table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "document_review_items" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("document_review_items")}
    for index_name in (
        "ix_document_review_items_created_by",
        "ix_document_review_items_status",
        "ix_document_review_items_file_id",
        "ix_document_review_items_id",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="document_review_items")
    op.drop_table("document_review_items")
