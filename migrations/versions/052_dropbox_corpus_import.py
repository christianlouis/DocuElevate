"""Add resumable Dropbox corpus import ledgers.

Revision ID: 052_dropbox_corpus_import
Revises: 051_document_intakes
"""

import sqlalchemy as sa
from alembic import op

revision = "052_dropbox_corpus_import"
down_revision = "051_document_intakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "dropbox_import_jobs" not in tables:
        op.create_table(
            "dropbox_import_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("integration_id", sa.Integer(), sa.ForeignKey("user_integrations.id"), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("root_path", sa.String(), nullable=False),
            sa.Column("cursor", sa.Text(), nullable=True),
            sa.Column("state", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("discovered", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("downloaded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("queued", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_dropbox_import_jobs_integration_id", "dropbox_import_jobs", ["integration_id"])
        op.create_index("ix_dropbox_import_jobs_owner_id", "dropbox_import_jobs", ["owner_id"])
        op.create_index("ix_dropbox_import_jobs_state", "dropbox_import_jobs", ["state"])
    if "dropbox_import_objects" not in tables:
        op.create_table(
            "dropbox_import_objects",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("integration_id", sa.Integer(), sa.ForeignKey("user_integrations.id"), nullable=False),
            sa.Column("dropbox_file_id", sa.String(), nullable=False),
            sa.Column("revision", sa.String(), nullable=False),
            sa.Column("remote_path", sa.Text(), nullable=False),
            sa.Column("intake_id", sa.Integer(), sa.ForeignKey("document_intakes.id"), nullable=True),
            sa.Column("task_id", sa.String(), nullable=True),
            sa.Column("state", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("integration_id", "dropbox_file_id", name="uq_dropbox_import_integration_file"),
        )
        op.create_index("ix_dropbox_import_objects_integration_id", "dropbox_import_objects", ["integration_id"])


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "dropbox_import_objects" in tables:
        op.drop_table("dropbox_import_objects")
    if "dropbox_import_jobs" in tables:
        op.drop_table("dropbox_import_jobs")
