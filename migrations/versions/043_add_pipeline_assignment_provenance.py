"""Add pipeline assignment provenance to files.

Revision ID: 043_add_pipeline_assignment_provenance
Revises: 042_add_file_shares
Create Date: 2026-07-06

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "043_add_pipeline_assignment_provenance"
down_revision: Union[str, None] = "042_add_file_shares"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Add provenance columns for pipeline assignment decisions."""
    columns = _column_names("files")

    if "pipeline_assignment_source" not in columns:
        op.add_column("files", sa.Column("pipeline_assignment_source", sa.String(length=50), nullable=True))
    if "pipeline_routing_rule_id" not in columns:
        op.add_column("files", sa.Column("pipeline_routing_rule_id", sa.Integer(), nullable=True))
    if "pipeline_assignment_reason" not in columns:
        op.add_column("files", sa.Column("pipeline_assignment_reason", sa.Text(), nullable=True))

    indexes = _index_names("files")
    if "ix_files_pipeline_assignment_source" not in indexes:
        op.create_index("ix_files_pipeline_assignment_source", "files", ["pipeline_assignment_source"])
    if "ix_files_pipeline_routing_rule_id" not in indexes:
        op.create_index("ix_files_pipeline_routing_rule_id", "files", ["pipeline_routing_rule_id"])

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_files_pipeline_routing_rule_id",
            "files",
            "pipeline_routing_rules",
            ["pipeline_routing_rule_id"],
            ["id"],
        )


def downgrade() -> None:
    """Remove pipeline assignment provenance columns."""
    bind = op.get_bind()
    indexes = _index_names("files")

    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_files_pipeline_routing_rule_id", "files", type_="foreignkey")

    if "ix_files_pipeline_routing_rule_id" in indexes:
        op.drop_index("ix_files_pipeline_routing_rule_id", table_name="files")
    if "ix_files_pipeline_assignment_source" in indexes:
        op.drop_index("ix_files_pipeline_assignment_source", table_name="files")

    columns = _column_names("files")
    if "pipeline_assignment_reason" in columns:
        op.drop_column("files", "pipeline_assignment_reason")
    if "pipeline_routing_rule_id" in columns:
        op.drop_column("files", "pipeline_routing_rule_id")
    if "pipeline_assignment_source" in columns:
        op.drop_column("files", "pipeline_assignment_source")
