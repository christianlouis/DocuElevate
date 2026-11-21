"""Add durable checkpoints for long document translations."""

import sqlalchemy as sa
from alembic import op

revision = "073_translation_checkpoint"
down_revision = "072_backup_restore_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "translation_checkpoint" not in {column["name"] for column in inspector.get_columns("files")}:
        op.add_column("files", sa.Column("translation_checkpoint", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "translation_checkpoint" in {column["name"] for column in inspector.get_columns("files")}:
        op.drop_column("files", "translation_checkpoint")
