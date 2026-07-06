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
    op.add_column(
        "saved_searches",
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Remove saved-search pinning support."""
    op.drop_column("saved_searches", "pinned")
