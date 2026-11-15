"""Store credential monitoring state in the shared database."""

import sqlalchemy as sa
from alembic import op

revision = "070_credential_check_states"
down_revision = "069_destination_delivery_parts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credential_check_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_name", sa.String(length=120), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("service_name", name="uq_credential_check_states_service"),
    )
    op.create_index(
        "ix_credential_check_states_service_name", "credential_check_states", ["service_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_credential_check_states_service_name", table_name="credential_check_states")
    op.drop_table("credential_check_states")
