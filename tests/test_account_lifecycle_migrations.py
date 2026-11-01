"""SQLite upgrade/downgrade coverage for account lifecycle migrations."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

MIGRATIONS = Path(__file__).parents[1] / "migrations" / "versions"


def _migration(name: str):
    path = MIGRATIONS / name
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run(connection, module, operation: str) -> None:
    context = MigrationContext.configure(connection)
    module.op = Operations(context)
    getattr(module, operation)()


def test_account_lifecycle_upgrade_and_downgrade_preserves_existing_rows():
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE local_users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)"))
        connection.execute(sa.text("CREATE TABLE user_profiles (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"))
        connection.execute(sa.text("INSERT INTO local_users (id, email) VALUES (1, 'existing@example.test')"))
        connection.execute(sa.text("INSERT INTO user_profiles (id, user_id) VALUES (1, 1)"))

        migration_065 = _migration("065_account_deletion_tombstones.py")
        migration_066 = _migration("066_signup_consent.py")
        _run(connection, migration_065, "upgrade")
        _run(connection, migration_066, "upgrade")

        local_columns = {column["name"] for column in sa.inspect(connection).get_columns("local_users")}
        profile_columns = {column["name"] for column in sa.inspect(connection).get_columns("user_profiles")}
        assert {
            "terms_accepted_version",
            "terms_accepted_at",
            "privacy_accepted_version",
            "privacy_accepted_at",
        } <= local_columns
        assert {
            "terms_accepted_version",
            "terms_accepted_at",
            "privacy_accepted_version",
            "privacy_accepted_at",
        } <= profile_columns
        assert (
            connection.execute(sa.text("SELECT email FROM local_users WHERE id = 1")).scalar_one()
            == "existing@example.test"
        )

        connection.execute(sa.text("INSERT INTO account_deletion_tombstones (owner_id) VALUES ('owner-1')"))
        with pytest.raises(IntegrityError):
            connection.execute(sa.text("INSERT INTO account_deletion_tombstones (owner_id) VALUES ('owner-1')"))
        connection.execute(
            sa.text(
                "INSERT INTO provider_grants (owner_id, provider, encrypted_token) VALUES ('owner-1', 'apple', 'ciphertext')"
            )
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO provider_grants (owner_id, provider, encrypted_token) VALUES ('owner-1', 'apple', 'other')"
                )
            )

        _run(connection, migration_066, "downgrade")
        assert "terms_accepted_version" not in {
            column["name"] for column in sa.inspect(connection).get_columns("local_users")
        }
        assert "privacy_accepted_at" not in {
            column["name"] for column in sa.inspect(connection).get_columns("user_profiles")
        }
        _run(connection, migration_065, "downgrade")
        assert not sa.inspect(connection).has_table("account_deletion_tombstones")
        assert not sa.inspect(connection).has_table("provider_grants")
        assert (
            connection.execute(sa.text("SELECT email FROM local_users WHERE id = 1")).scalar_one()
            == "existing@example.test"
        )
