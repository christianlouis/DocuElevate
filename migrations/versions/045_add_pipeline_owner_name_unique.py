"""Add per-owner pipeline name uniqueness.

Revision ID: 045_add_pipeline_owner_name_unique
Revises: 044_add_saved_search_pinned
Create Date: 2026-07-06
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "045_add_pipeline_owner_name_unique"
down_revision: Union[str, None] = "044_add_saved_search_pinned"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create a database guard for duplicate pipeline names per owner."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "pipelines" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("pipelines")}
    existing_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("pipelines")}
    if "uq_pipelines_owner_name" not in existing_indexes | existing_constraints:
        op.create_index("uq_pipelines_owner_name", "pipelines", ["owner_id", "name"], unique=True)


def downgrade() -> None:
    """Remove the per-owner pipeline name database guard."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "pipelines" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("pipelines")}
    existing_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("pipelines")}
    if "uq_pipelines_owner_name" in existing_indexes:
        op.drop_index("uq_pipelines_owner_name", table_name="pipelines")
    elif "uq_pipelines_owner_name" in existing_constraints:
        op.drop_constraint("uq_pipelines_owner_name", "pipelines", type_="unique")
