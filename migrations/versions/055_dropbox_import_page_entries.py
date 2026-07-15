"""Persist committed Dropbox result-page entries.

Revision ID: 055_dropbox_import_page_entries
Revises: 054_corpus_llm_daily_usage
"""

import sqlalchemy as sa
from alembic import op

revision = "055_dropbox_import_page_entries"
down_revision = "054_corpus_llm_daily_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "page_entry_keys" not in columns:
        op.add_column(
            "dropbox_import_jobs",
            sa.Column("page_entry_keys", sa.Text(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "page_entry_keys" in columns:
        op.drop_column("dropbox_import_jobs", "page_entry_keys")
