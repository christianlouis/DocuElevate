"""Add durable daily corpus LLM token reservations.

Revision ID: 054_corpus_llm_daily_usage
Revises: 053_onboarding_journey
"""

import sqlalchemy as sa
from alembic import op

revision = "054_corpus_llm_daily_usage"
down_revision = "053_onboarding_journey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "corpus_llm_daily_usage" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "corpus_llm_daily_usage",
        sa.Column("usage_date", sa.Date(), primary_key=True),
        sa.Column("reserved_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    if "corpus_llm_daily_usage" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("corpus_llm_daily_usage")
