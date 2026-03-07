"""Add pipelines and pipeline_steps tables; add pipeline_id to files

Revision ID: 017_add_pipelines
Revises: 016_add_userprofile_billing
Create Date: 2026-03-07

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017_add_pipelines"
down_revision: Union[str, None] = "016_add_userprofile_billing"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create pipelines, pipeline_steps tables and add pipeline_id FK to files."""
    op.create_table(
        "pipelines",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("owner_id", sa.String(), nullable=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("pipeline_id", sa.Integer(), sa.ForeignKey("pipelines.id"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step_type", sa.String(100), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Use batch mode for SQLite compatibility when altering the files table.
    # SQLite does not support adding FK constraints inline via ALTER TABLE, so we
    # add the plain integer column and define the FK reference at the model level.
    with op.batch_alter_table("files") as batch_op:
        batch_op.add_column(
            sa.Column("pipeline_id", sa.Integer(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_files_pipeline_id",
            "pipelines",
            ["pipeline_id"],
            ["id"],
        )


def downgrade() -> None:
    """Drop pipeline_id from files and remove pipeline tables."""
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("pipeline_id")

    op.drop_table("pipeline_steps")
    op.drop_table("pipelines")
