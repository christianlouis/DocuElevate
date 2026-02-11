"""Add file processing steps table

Revision ID: 001_file_processing_steps
Revises:
Create Date: 2026-02-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_file_processing_steps"
down_revision: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create file_processing_steps table."""
    op.create_table(
        "file_processing_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], name="fk_file_processing_steps_file_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", "step_name", name="unique_file_step"),
    )
    op.create_index("ix_file_processing_steps_file_id", "file_processing_steps", ["file_id"])
    op.create_index("ix_file_processing_steps_step_name", "file_processing_steps", ["step_name"])


def downgrade() -> None:
    """Drop file_processing_steps table."""
    op.drop_index("ix_file_processing_steps_step_name", table_name="file_processing_steps")
    op.drop_index("ix_file_processing_steps_file_id", table_name="file_processing_steps")
    op.drop_table("file_processing_steps")
