"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
depends_on: Union[str, None] = None


def upgrade() -> None:
    """${message}."""
    # Use ``op.batch_alter_table()`` for SQLite compatibility.
    # Always check whether the table/column already exists before altering
    # to keep migrations idempotent (safe to re-run).
    #
    # Example – add a column only if it is missing:
    #
    #     conn = op.get_bind()
    #     inspector = sa.inspect(conn)
    #     if "my_table" in inspector.get_table_names():
    #         existing = {c["name"] for c in inspector.get_columns("my_table")}
    #         if "new_col" not in existing:
    #             with op.batch_alter_table("my_table") as batch_op:
    #                 batch_op.add_column(sa.Column("new_col", sa.String(128), nullable=True))
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverse ${message}."""
    ${downgrades if downgrades else "pass"}
