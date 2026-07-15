"""Persist the current Dropbox result-page offset.

Revision ID: 055_dropbox_import_page_offset
Revises: 054_corpus_llm_daily_usage
"""

import sqlalchemy as sa
from alembic import op

revision = "055_dropbox_import_page_offset"
down_revision = "054_corpus_llm_daily_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "page_offset" not in columns:
        op.add_column(
            "dropbox_import_jobs",
            sa.Column("page_offset", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "page_offset" in columns:
        op.drop_column("dropbox_import_jobs", "page_offset")
