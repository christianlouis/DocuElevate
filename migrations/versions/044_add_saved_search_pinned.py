"""Add pinned flag to saved searches

Revision ID: 044_add_saved_search_pinned
Revises: 043_add_pipeline_assignment_provenance
Create Date: 2026-07-06

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "044_add_saved_search_pinned"
down_revision: Union[str, None] = "043_add_pipeline_assignment_provenance"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add saved-search pinning support."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "saved_searches" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("saved_searches")}
    if "pinned" not in existing_columns:
        op.add_column(
            "saved_searches",
            sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    """Remove saved-search pinning support."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "saved_searches" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("saved_searches")}
    if "pinned" in existing_columns:
        op.drop_column("saved_searches", "pinned")
