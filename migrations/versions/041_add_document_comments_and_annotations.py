"""Add document_comments and document_annotations tables.

Revision ID: 041_add_document_comments_and_annotations
Revises: 040_add_automation_hooks
Create Date: 2026-03-21

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "041_add_document_comments_and_annotations"
down_revision: Union[str, None] = "040_add_automation_hooks"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add document_comments and document_annotations tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "document_comments" not in existing_tables:
        op.create_table(
            "document_comments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("mentions", sa.Text(), nullable=True),
            sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
            sa.ForeignKeyConstraint(["parent_id"], ["document_comments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_document_comments_id", "document_comments", ["id"])
        op.create_index("ix_document_comments_file_id", "document_comments", ["file_id"])
        op.create_index("ix_document_comments_user_id", "document_comments", ["user_id"])
        op.create_index("ix_document_comments_parent_id", "document_comments", ["parent_id"])

    if "document_annotations" not in existing_tables:
        op.create_table(
            "document_annotations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("file_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("page", sa.Integer(), nullable=False),
            sa.Column("x", sa.Float(), nullable=False),
            sa.Column("y", sa.Float(), nullable=False),
            sa.Column("width", sa.Float(), nullable=False),
            sa.Column("height", sa.Float(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("annotation_type", sa.String(50), nullable=False, server_default="note"),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_document_annotations_id", "document_annotations", ["id"])
        op.create_index("ix_document_annotations_file_id", "document_annotations", ["file_id"])
        op.create_index("ix_document_annotations_user_id", "document_annotations", ["user_id"])


def downgrade() -> None:
    """Drop document_comments and document_annotations tables."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    if "document_annotations" in existing_tables:
        op.drop_index("ix_document_annotations_user_id", "document_annotations")
        op.drop_index("ix_document_annotations_file_id", "document_annotations")
        op.drop_index("ix_document_annotations_id", "document_annotations")
        op.drop_table("document_annotations")

    if "document_comments" in existing_tables:
        op.drop_index("ix_document_comments_parent_id", "document_comments")
        op.drop_index("ix_document_comments_user_id", "document_comments")
        op.drop_index("ix_document_comments_file_id", "document_comments")
        op.drop_index("ix_document_comments_id", "document_comments")
        op.drop_table("document_comments")
