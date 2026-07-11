"""
Tests for migration 045: idempotency of upgrade/downgrade.
"""

import sys
from importlib import util
from unittest.mock import MagicMock, patch

import pytest

# Dynamically load the migration module
migration_path = "migrations/versions/045_add_pipeline_owner_name_unique.py"
spec = util.spec_from_file_location("migration_045", migration_path)
migration_045 = util.module_from_spec(spec)
sys.modules["migration_045"] = migration_045
spec.loader.exec_module(migration_045)


@pytest.fixture
def mock_op_and_inspector():
    with patch.object(migration_045, "op") as mock_op, patch.object(migration_045, "sa") as mock_sa:
        mock_conn = MagicMock()
        mock_op.get_bind.return_value = mock_conn

        mock_inspector = MagicMock()
        mock_sa.inspect.return_value = mock_inspector

        # Default: table exists
        mock_inspector.get_table_names.return_value = ["pipelines"]
        yield mock_op, mock_inspector


def test_upgrade_idempotent_no_existing(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = []
    mock_inspector.get_unique_constraints.return_value = []

    migration_045.upgrade()

    mock_op.create_index.assert_called_once_with(
        "uq_pipelines_owner_name", "pipelines", ["owner_id", "name"], unique=True
    )


def test_upgrade_idempotent_index_exists(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = [{"name": "uq_pipelines_owner_name"}]
    mock_inspector.get_unique_constraints.return_value = []

    migration_045.upgrade()

    mock_op.create_index.assert_not_called()


def test_upgrade_idempotent_constraint_exists(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = []
    mock_inspector.get_unique_constraints.return_value = [{"name": "uq_pipelines_owner_name"}]

    migration_045.upgrade()

    mock_op.create_index.assert_not_called()


def test_downgrade_idempotent_no_existing(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = []
    mock_inspector.get_unique_constraints.return_value = []

    migration_045.downgrade()

    mock_op.drop_index.assert_not_called()
    mock_op.drop_constraint.assert_not_called()


def test_downgrade_idempotent_index_exists(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = [{"name": "uq_pipelines_owner_name"}]
    mock_inspector.get_unique_constraints.return_value = []

    migration_045.downgrade()

    mock_op.drop_index.assert_called_once_with("uq_pipelines_owner_name", table_name="pipelines")
    mock_op.drop_constraint.assert_not_called()


def test_downgrade_idempotent_constraint_exists(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_indexes.return_value = []
    mock_inspector.get_unique_constraints.return_value = [{"name": "uq_pipelines_owner_name"}]

    migration_045.downgrade()

    mock_op.drop_index.assert_not_called()
    mock_op.drop_constraint.assert_called_once_with("uq_pipelines_owner_name", table_name="pipelines", type_="unique")


def test_skip_if_no_table(mock_op_and_inspector):
    mock_op, mock_inspector = mock_op_and_inspector
    mock_inspector.get_table_names.return_value = []

    migration_045.upgrade()
    mock_inspector.get_indexes.assert_not_called()
    mock_op.create_index.assert_not_called()

    migration_045.downgrade()
    mock_inspector.get_indexes.assert_not_called()
    mock_op.drop_index.assert_not_called()
    mock_op.drop_constraint.assert_not_called()
