"""Persist idempotent destination size-policy delivery parts."""

import sqlalchemy as sa
from alembic import op

revision = "069_destination_delivery_parts"
down_revision = "068_bulk_capacity_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("files") as batch:
        batch.add_column(sa.Column("source_integration_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_files_source_integration_id",
            "user_integrations",
            ["source_integration_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_files_source_integration_id", "files", ["source_integration_id"])
    op.create_table(
        "destination_delivery_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "integration_id", sa.Integer(), sa.ForeignKey("user_integrations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "file_id",
            "integration_id",
            "content_hash",
            "policy_hash",
            "part_number",
            name="uq_destination_delivery_part",
        ),
    )
    op.create_index("ix_destination_delivery_parts_file_id", "destination_delivery_parts", ["file_id"])
    op.create_index("ix_destination_delivery_parts_integration_id", "destination_delivery_parts", ["integration_id"])
    op.create_index("ix_destination_delivery_parts_status", "destination_delivery_parts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_destination_delivery_parts_status", table_name="destination_delivery_parts")
    op.drop_index("ix_destination_delivery_parts_integration_id", table_name="destination_delivery_parts")
    op.drop_index("ix_destination_delivery_parts_file_id", table_name="destination_delivery_parts")
    op.drop_table("destination_delivery_parts")
    op.drop_index("ix_files_source_integration_id", table_name="files")
    with op.batch_alter_table("files") as batch:
        batch.drop_constraint("fk_files_source_integration_id", type_="foreignkey")
        batch.drop_column("source_integration_id")
