"""Track one-time release of bulk-upload admission capacity."""

import sqlalchemy as sa
from alembic import op

revision = "068_bulk_capacity_release"
down_revision = "067_durable_bulk_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("upload_items", sa.Column("capacity_released", sa.Boolean(), nullable=False, server_default="0"))
    op.create_index("ix_upload_items_capacity_released", "upload_items", ["capacity_released"])


def downgrade() -> None:
    op.drop_index("ix_upload_items_capacity_released", table_name="upload_items")
    op.drop_column("upload_items", "capacity_released")
