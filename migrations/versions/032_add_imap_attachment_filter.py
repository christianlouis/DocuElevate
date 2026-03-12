"""Add attachment_filter column to user_imap_accounts table.

Revision ID: 032_add_imap_attachment_filter
Revises: 031_add_compliance_templates
Create Date: 2026-03-12
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "032_add_imap_attachment_filter"
down_revision: Union[str, None] = "031_add_compliance_templates"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add attachment_filter column to user_imap_accounts."""
    op.add_column(
        "user_imap_accounts",
        sa.Column("attachment_filter", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    """Remove attachment_filter column from user_imap_accounts."""
    op.drop_column("user_imap_accounts", "attachment_filter")
