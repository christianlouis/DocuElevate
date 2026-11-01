"""Add durable reload-safe bulk upload ledgers."""
import sqlalchemy as sa
from alembic import op

revision = "065_durable_bulk_uploads"
down_revision = "064_scope_automation_hooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("upload_batches", sa.Column("id", sa.String(36), primary_key=True), sa.Column("principal_id", sa.String(), nullable=False), sa.Column("owner_id", sa.String(), nullable=True), sa.Column("client_batch_id", sa.String(255), nullable=False), sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"), sa.Column("total_bytes", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("state", sa.String(20), nullable=False, server_default="open"), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("principal_id", "client_batch_id", name="uq_upload_batch_principal_client"))
    op.create_table("upload_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.String(36), sa.ForeignKey("upload_batches.id", ondelete="CASCADE"), nullable=False), sa.Column("client_id", sa.String(255), nullable=False), sa.Column("principal_id", sa.String(), nullable=False), sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("mime_type", sa.String(255), nullable=True), sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("state", sa.String(20), nullable=False, server_default="pending"), sa.Column("error", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("batch_id", "client_id", name="uq_upload_item_batch_client"))
    op.create_table("upload_outbox", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("item_id", sa.Integer(), sa.ForeignKey("upload_items.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"), sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True), sa.Column("claim_token", sa.String(36), nullable=True), sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True), sa.Column("pipeline_started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("last_error", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_upload_outbox_claim_expires_at", "upload_outbox", ["claim_expires_at"])
    op.create_table("upload_capacity", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("reserved_files", sa.Integer(), nullable=False, server_default="0"), sa.Column("reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.execute(sa.text("INSERT INTO upload_capacity (id, reserved_files, reserved_bytes) VALUES (1, 0, 0)"))


def downgrade() -> None:
    op.drop_table("upload_capacity")
    op.drop_table("upload_outbox")
    op.drop_table("upload_items")
    op.drop_table("upload_batches")
