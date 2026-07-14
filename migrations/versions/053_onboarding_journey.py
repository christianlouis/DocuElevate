"""Add resumable per-user onboarding journey state.

Revision ID: 053_onboarding_journey
Revises: 052_dropbox_corpus_import
"""

import sqlalchemy as sa
from alembic import op

revision = "053_onboarding_journey"
down_revision = "052_dropbox_corpus_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("user_profiles")}
    if "onboarding_current_step" not in columns:
        op.add_column(
            "user_profiles",
            sa.Column("onboarding_current_step", sa.Integer(), nullable=False, server_default="1"),
        )
    if "onboarding_journey_state" not in columns:
        op.add_column("user_profiles", sa.Column("onboarding_journey_state", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("user_profiles")}
    if "onboarding_journey_state" in columns:
        op.drop_column("user_profiles", "onboarding_journey_state")
    if "onboarding_current_step" in columns:
        op.drop_column("user_profiles", "onboarding_current_step")
