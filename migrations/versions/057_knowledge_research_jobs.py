"""Add durable exhaustive knowledge research jobs.

Revision ID: 057_knowledge_research_jobs
Revises: 056_dropbox_import_job_mode
"""

import sqlalchemy as sa
from alembic import op

revision = "057_knowledge_research_jobs"
down_revision = "056_dropbox_import_job_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "knowledge_research_jobs" in inspector.get_table_names():
        return
    op.create_table(
        "knowledge_research_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("history_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("accessible_file_ids_json", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_research_jobs_owner_id", "knowledge_research_jobs", ["owner_id"])
    op.create_index("ix_knowledge_research_jobs_cache_key", "knowledge_research_jobs", ["cache_key"])
    op.create_index("ix_knowledge_research_jobs_state", "knowledge_research_jobs", ["state"])
    op.create_index("ix_knowledge_research_jobs_created_at", "knowledge_research_jobs", ["created_at"])
    op.create_index(
        "uq_knowledge_research_active_owner_cache",
        "knowledge_research_jobs",
        ["owner_id", "cache_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'running')"),
        sqlite_where=sa.text("state IN ('queued', 'running')"),
    )


def downgrade() -> None:
    if "knowledge_research_jobs" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("knowledge_research_jobs")
