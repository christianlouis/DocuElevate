"""Distinguish initial Dropbox backfills from incremental watch jobs.

Revision ID: 056_dropbox_import_job_mode
Revises: 055_dropbox_import_page_entries
"""

import sqlalchemy as sa
from alembic import op

revision = "056_dropbox_import_job_mode"
down_revision = "055_dropbox_import_page_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "is_backfill" not in columns:
        # Existing jobs are true-ups created before mode was persisted, so the
        # safe migration default keeps their cost guard enabled.
        op.add_column(
            "dropbox_import_jobs",
            sa.Column("is_backfill", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "dropbox_import_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("dropbox_import_jobs")}
    if "is_backfill" in columns:
        op.drop_column("dropbox_import_jobs", "is_backfill")
