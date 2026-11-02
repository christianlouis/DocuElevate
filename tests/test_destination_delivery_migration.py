"""Exercise the delivery migration against a real SQLite database."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_delivery_migration_upgrade_and_downgrade():
    path = Path(__file__).parents[1] / "migrations/versions/069_destination_delivery_parts.py"
    spec = importlib.util.spec_from_file_location("delivery_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE user_integrations (id INTEGER PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(sa.text("INSERT INTO files VALUES (1, 'original')"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert "destination_delivery_parts" in sa.inspect(connection).get_table_names()
        assert "source_integration_id" in {c["name"] for c in sa.inspect(connection).get_columns("files")}
        module.downgrade()
        assert "destination_delivery_parts" not in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text("SELECT name FROM files")).scalar() == "original"
