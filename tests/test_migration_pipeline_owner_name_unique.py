"""Regression tests for the pipeline owner/name uniqueness migration."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


def _load_migration():
    path = Path(__file__).parents[1] / "migrations" / "versions" / "045_add_pipeline_owner_name_unique.py"
    spec = importlib.util.spec_from_file_location("pipeline_owner_name_unique", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_upgrade_accepts_existing_unique_constraint(monkeypatch):
    migration = _load_migration()
    migration.op = MagicMock()
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["pipelines"]
    inspector.get_indexes.return_value = []
    inspector.get_unique_constraints.return_value = [{"name": "uq_pipelines_owner_name"}]
    monkeypatch.setattr(migration.sa, "inspect", lambda _connection: inspector)

    migration.upgrade()

    migration.op.create_index.assert_not_called()


def test_downgrade_drops_existing_unique_constraint(monkeypatch):
    migration = _load_migration()
    migration.op = MagicMock()
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["pipelines"]
    inspector.get_indexes.return_value = []
    inspector.get_unique_constraints.return_value = [{"name": "uq_pipelines_owner_name"}]
    monkeypatch.setattr(migration.sa, "inspect", lambda _connection: inspector)

    migration.downgrade()

    migration.op.drop_constraint.assert_called_once_with(
        "uq_pipelines_owner_name", "pipelines", type_="unique"
    )
