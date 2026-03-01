"""Add saved_searches table for user-defined filter combinations

Revision ID: 005_add_saved_searches
Revises: 004_add_search_fields
Create Date: 2026-03-01

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_saved_searches"
down_revision: Union[str, None] = "004_add_search_fields"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create saved_searches table."""
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("filters", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="unique_user_search_name"),
    )


def downgrade() -> None:
    """Drop saved_searches table."""
    op.drop_table("saved_searches")
