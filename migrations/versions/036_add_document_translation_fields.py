"""Add document translation fields to files and user_profiles tables.

Adds detected_language, default_language_text, and default_language_code to
the files table so that a translated version of the document text can be
stored alongside the original.

Adds default_document_language to user_profiles so each user can override
the system-wide default translation target language.

Revision ID: 036_add_document_translation_fields
Revises: 035_add_routing_rules
Create Date: 2026-03-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "036_add_document_translation_fields"
down_revision: Union[str, None] = "035_add_routing_rules"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add translation columns to files and user_profiles."""
    with op.batch_alter_table("files") as batch_op:
        batch_op.add_column(sa.Column("detected_language", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("default_language_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("default_language_code", sa.String(10), nullable=True))

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.add_column(sa.Column("default_document_language", sa.String(10), nullable=True))


def downgrade() -> None:
    """Remove translation columns."""
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_column("default_document_language")

    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("default_language_code")
        batch_op.drop_column("default_language_text")
        batch_op.drop_column("detected_language")
