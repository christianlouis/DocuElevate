"""Add durable resumable IMAP message ledger."""

import sqlalchemy as sa
from alembic import op

revision = "070_imap_message_ledger"
down_revision = "069_destination_delivery_parts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imap_message_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("mailbox_key", sa.String(length=255), nullable=False),
        sa.Column("uidvalidity", sa.String(length=255), nullable=False),
        sa.Column("uid", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.String(length=998), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_key", "mailbox_key", "uidvalidity", "uid", name="uq_imap_ledger_owner_mailbox_uid"),
    )
    op.create_table(
        "imap_scan_cursors",
        sa.Column("mailbox_key", sa.String(64), primary_key=True),
        sa.Column("uidvalidity", sa.String(255), primary_key=True),
        sa.Column("last_uid", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_imap_message_ledger_id", "imap_message_ledger", ["id"])
    op.create_index("ix_imap_message_ledger_state", "imap_message_ledger", ["state"])
    op.create_index("ix_imap_ledger_state", "imap_message_ledger", ["owner_key", "mailbox_key", "state"])


def downgrade() -> None:
    op.drop_index("ix_imap_ledger_state", table_name="imap_message_ledger")
    op.drop_index("ix_imap_message_ledger_state", table_name="imap_message_ledger")
    op.drop_index("ix_imap_message_ledger_id", table_name="imap_message_ledger")
    op.drop_table("imap_message_ledger")
    op.drop_table("imap_scan_cursors")
