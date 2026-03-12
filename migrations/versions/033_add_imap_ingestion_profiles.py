"""Add imap_ingestion_profiles table and migrate user_imap_accounts.

Creates the ``imap_ingestion_profiles`` table, seeds the two built-in profiles
("Documents Only" and "All Files"), and replaces the ``attachment_filter``
string column on ``user_imap_accounts`` with a ``profile_id`` FK that references
the new table.

Revision ID: 033_add_imap_ingestion_profiles
Revises: 032_add_imap_attachment_filter
Create Date: 2026-03-12
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_add_imap_ingestion_profiles"
down_revision: Union[str, None] = "032_add_imap_attachment_filter"
depends_on: Union[str, None] = None

# Fixed IDs for the built-in profiles so that the FK migration is reproducible.
_BUILTIN_DOCUMENTS_ONLY_ID = 1
_BUILTIN_ALL_FILES_ID = 2


def upgrade() -> None:
    """Create profiles table, seed built-ins, migrate accounts column."""
    # 1 — Create the imap_ingestion_profiles table
    op.create_table(
        "imap_ingestion_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column(
            "allowed_categories",
            sa.Text(),
            nullable=False,
            server_default='["pdf","office","opendocument","text","web"]',
        ),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imap_ingestion_profiles_id", "imap_ingestion_profiles", ["id"])
    op.create_index("ix_imap_ingestion_profiles_owner_id", "imap_ingestion_profiles", ["owner_id"])

    # 2 — Seed the two built-in profiles
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO imap_ingestion_profiles "
            "(id, name, description, owner_id, allowed_categories, is_builtin) "
            "VALUES (:id, :name, :desc, NULL, :cats, 1)"
        ),
        [
            {
                "id": _BUILTIN_DOCUMENTS_ONLY_ID,
                "name": "Documents Only",
                "desc": (
                    "Ingest PDFs, Microsoft Office files, OpenDocument files, "
                    "plain text, CSV, RTF, HTML and Markdown. Images are excluded."
                ),
                "cats": '["pdf","office","opendocument","text","web"]',
            },
            {
                "id": _BUILTIN_ALL_FILES_ID,
                "name": "All Files",
                "desc": "Ingest all supported file types, including images.",
                "cats": '["pdf","office","opendocument","text","web","images"]',
            },
        ],
    )

    # 3 — Add profile_id column to user_imap_accounts
    op.add_column(
        "user_imap_accounts",
        sa.Column("profile_id", sa.Integer(), nullable=True),
    )

    # 4 — Migrate existing attachment_filter values to profile_id
    bind.execute(
        sa.text(
            "UPDATE user_imap_accounts SET profile_id = :pid "
            "WHERE attachment_filter = 'all'"
        ),
        {"pid": _BUILTIN_ALL_FILES_ID},
    )
    bind.execute(
        sa.text(
            "UPDATE user_imap_accounts SET profile_id = :pid "
            "WHERE attachment_filter = 'documents_only'"
        ),
        {"pid": _BUILTIN_DOCUMENTS_ONLY_ID},
    )
    # Rows with NULL attachment_filter keep profile_id = NULL (use global default)

    # 5 — Add FK constraint (skip for SQLite which does not enforce FKs at DDL time)
    # We use batch_alter_table so this works across SQLite and PostgreSQL
    with op.batch_alter_table("user_imap_accounts") as batch_op:
        batch_op.create_foreign_key(
            "fk_user_imap_accounts_profile_id",
            "imap_ingestion_profiles",
            ["profile_id"],
            ["id"],
        )

    # 6 — Drop the now-redundant attachment_filter column
    with op.batch_alter_table("user_imap_accounts") as batch_op:
        batch_op.drop_column("attachment_filter")


def downgrade() -> None:
    """Reverse the migration: restore attachment_filter, drop profiles table."""
    # 1 — Re-add attachment_filter column
    with op.batch_alter_table("user_imap_accounts") as batch_op:
        batch_op.add_column(sa.Column("attachment_filter", sa.String(50), nullable=True))

    # 2 — Restore string values from profile_id
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE user_imap_accounts SET attachment_filter = 'all' "
            "WHERE profile_id = :pid"
        ),
        {"pid": _BUILTIN_ALL_FILES_ID},
    )
    bind.execute(
        sa.text(
            "UPDATE user_imap_accounts SET attachment_filter = 'documents_only' "
            "WHERE profile_id = :pid"
        ),
        {"pid": _BUILTIN_DOCUMENTS_ONLY_ID},
    )

    # 3 — Drop the FK and profile_id column
    with op.batch_alter_table("user_imap_accounts") as batch_op:
        batch_op.drop_constraint("fk_user_imap_accounts_profile_id", type_="foreignkey")
        batch_op.drop_column("profile_id")

    # 4 — Drop the profiles table
    op.drop_index("ix_imap_ingestion_profiles_owner_id", "imap_ingestion_profiles")
    op.drop_index("ix_imap_ingestion_profiles_id", "imap_ingestion_profiles")
    op.drop_table("imap_ingestion_profiles")
