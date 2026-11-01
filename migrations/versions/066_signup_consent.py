"""Persist legal-version acknowledgement for local signup."""

import sqlalchemy as sa
from alembic import op

revision = "066_signup_consent"
down_revision = "065_account_deletion_tombstones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("local_users", sa.Column("terms_accepted_version", sa.String(length=64), nullable=True))
    op.add_column("local_users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("local_users", sa.Column("privacy_accepted_version", sa.String(length=64), nullable=True))
    op.add_column("local_users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("local_users", "privacy_accepted_at")
    op.drop_column("local_users", "privacy_accepted_version")
    op.drop_column("local_users", "terms_accepted_at")
    op.drop_column("local_users", "terms_accepted_version")
