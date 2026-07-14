"""Add durable document intake idempotency ledger.

Revision ID: 051_document_intakes
Revises: 050_pipeline_versions
"""

import sqlalchemy as sa
from alembic import op

revision = "051_document_intakes"
down_revision = "050_pipeline_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "document_intakes" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "document_intakes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("local_path", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("principal_id", "idempotency_key", name="uq_document_intake_principal_key"),
    )
    op.create_index("ix_document_intakes_id", "document_intakes", ["id"])
    op.create_index("ix_document_intakes_principal_id", "document_intakes", ["principal_id"])
    op.create_index("ix_document_intakes_source", "document_intakes", ["source"])
    op.create_index("ix_document_intakes_task_id", "document_intakes", ["task_id"])
    op.create_index("ix_document_intakes_state", "document_intakes", ["state"])


def downgrade() -> None:
    if "document_intakes" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_table("document_intakes")
