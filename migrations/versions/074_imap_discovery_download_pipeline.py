"""Add lane-aware IMAP discovery cursor and candidate outbox fields."""
import sqlalchemy as sa
from alembic import op

revision = "074_imap_discovery_download_pipeline"
down_revision = "073_translation_checkpoint"
branch_labels = None
depends_on = None

def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("imap_message_ledger")}
    for name, column in (("lane", sa.Column("lane", sa.String(16), nullable=False, server_default="backlog")), ("account_ref", sa.Column("account_ref", sa.String(255))), ("discovery_state", sa.Column("discovery_state", sa.String(24), nullable=False, server_default="discovered")), ("is_candidate", sa.Column("is_candidate", sa.Boolean(), nullable=False, server_default="0")), ("download_attempts", sa.Column("download_attempts", sa.Integer(), nullable=False, server_default="0")), ("download_lease_token", sa.Column("download_lease_token", sa.String(64))), ("download_lease_expires_at", sa.Column("download_lease_expires_at", sa.DateTime(timezone=True))), ("metadata_json", sa.Column("metadata_json", sa.Text()))):
        if name not in columns:
            op.add_column("imap_message_ledger", column)
    op.create_index("ix_imap_ledger_lane", "imap_message_ledger", ["lane"])
    op.create_index("ix_imap_ledger_candidate", "imap_message_ledger", ["is_candidate", "discovery_state"])
    op.create_table("imap_pipeline_cursors", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_key", sa.String(255), nullable=False), sa.Column("mailbox_key", sa.String(255), nullable=False), sa.Column("uidvalidity", sa.String(255), nullable=False), sa.Column("lane", sa.String(16), nullable=False), sa.Column("last_uid", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("highwater_uid", sa.BigInteger()), sa.Column("initialized", sa.Boolean(), nullable=False, server_default="0"), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("owner_key", "mailbox_key", "uidvalidity", "lane", name="uq_imap_pipeline_cursor_identity"))
    op.create_index("ix_imap_pipeline_cursor_lane", "imap_pipeline_cursors", ["mailbox_key", "lane"])

def downgrade() -> None:
    op.drop_index("ix_imap_pipeline_cursor_lane", table_name="imap_pipeline_cursors")
    op.drop_table("imap_pipeline_cursors")
    op.drop_index("ix_imap_ledger_candidate", table_name="imap_message_ledger")
    op.drop_index("ix_imap_ledger_lane", table_name="imap_message_ledger")
    for name in ("metadata_json", "download_lease_expires_at", "download_lease_token", "download_attempts", "is_candidate", "discovery_state", "account_ref", "lane"):
        op.drop_column("imap_message_ledger", name)
