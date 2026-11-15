"""Record optional isolated restore verification results for backups."""

import sqlalchemy as sa
from alembic import op

revision = "072_backup_restore_verification"
down_revision = "071_credential_check_states"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backup_records", sa.Column("verification_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backup_records", sa.Column("verification_status", sa.String(length=20), nullable=True))
    op.add_column("backup_records", sa.Column("verification_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("backup_records", "verification_detail")
    op.drop_column("backup_records", "verification_status")
    op.drop_column("backup_records", "verification_at")
