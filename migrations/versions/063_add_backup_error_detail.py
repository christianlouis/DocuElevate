"""Persist actionable backup failure diagnostics.

Revision ID: 063_add_backup_error_detail
Revises: 062_add_tribe_invitations
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "063_add_backup_error_detail"
down_revision: Union[str, None] = "062_add_tribe_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backup_records", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("backup_records", "error_detail")
