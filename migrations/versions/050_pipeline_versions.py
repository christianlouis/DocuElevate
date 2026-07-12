"""Add pipeline publishing and immutable versions.

Revision ID: 050_pipeline_versions
Revises: 049_workflow_bulk_operations
"""

import sqlalchemy as sa
from alembic import op

revision = "050_pipeline_versions"
down_revision = "049_workflow_bulk_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "pipelines" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.add_column("pipelines", sa.Column("lifecycle_state", sa.String(20), nullable=False, server_default="draft"))
    op.add_column("pipelines", sa.Column("published_version", sa.Integer(), nullable=True))
    op.create_table(
        "pipeline_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_id", sa.Integer(), sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.Text(), nullable=False),
        sa.Column("published_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("pipeline_id", "version", name="uq_pipeline_versions_number"),
    )
    op.create_index("ix_pipeline_versions_pipeline_id", "pipeline_versions", ["pipeline_id"])


def downgrade() -> None:
    if "pipelines" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_pipeline_versions_pipeline_id", table_name="pipeline_versions")
    op.drop_table("pipeline_versions")
    op.drop_column("pipelines", "published_version")
    op.drop_column("pipelines", "lifecycle_state")
