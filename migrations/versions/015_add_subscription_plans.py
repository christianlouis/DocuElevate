"""Add subscription_plans table

Revision ID: 015_add_subscription_plans
Revises: 014_add_subscription_tiers
Create Date: 2026-03-07

"""

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015_add_subscription_plans"
down_revision: Union[str, None] = "014_add_subscription_tiers"
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Create subscription_plans table for admin-configurable plan definitions."""
    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), primary_key=True, index=True, nullable=False),
        sa.Column("plan_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tagline", sa.String(255), nullable=True),
        # Pricing
        sa.Column("price_monthly", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("price_yearly", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        # Volume limits
        sa.Column("lifetime_file_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_upload_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("monthly_upload_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_storage_destinations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_ocr_pages_monthly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_file_size_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_mailboxes", sa.Integer(), nullable=False, server_default="0"),
        # Overage
        sa.Column("overage_percent", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("allow_overage_billing", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("overage_price_per_doc", sa.Float(), nullable=True),
        sa.Column("overage_price_per_ocr_page", sa.Float(), nullable=True),
        # Display / marketing
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("is_highlighted", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("badge_text", sa.String(50), nullable=True),
        sa.Column("cta_text", sa.String(100), nullable=False, server_default="Get started"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("features", sa.Text(), nullable=True),
        sa.Column("api_access", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop subscription_plans table."""
    op.drop_table("subscription_plans")
