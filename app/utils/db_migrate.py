"""Database migration utility for copying SQLite state to another SQL backend.

The production 0.30.2 deployment stores state in SQLite.  This module provides
a conservative data-copy path for moving that state into PostgreSQL while
preserving tables that may have been created by newer application builds.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any

from sqlalchemy import MetaData, column, create_engine, func, inspect, select, table, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)

_SKIP_TABLES = {"alembic_version", "sqlite_sequence"}
_TABLE_ORDER = [
    "documents",
    "files",
    "file_processing_steps",
    "processing_logs",
    "application_settings",
]
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _make_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine with SQLite-only connection arguments."""
    parsed = make_url(url)
    connect_args: dict[str, Any] = {}
    if parsed.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


def _safe_table_names(inspector: Any) -> list[str]:
    """Return source table names, excluding internal and unsafe identifiers."""
    result = []
    for name in inspector.get_table_names():
        if name in _SKIP_TABLES:
            continue
        if not _SAFE_IDENTIFIER.match(name):
            logger.warning("Skipping table with unsafe name: %s", name)
            continue
        result.append(name)
    return result


def _ordered_tables(inspector: Any) -> list[str]:
    """Return table names in stable parent-first order."""
    existing = set(_safe_table_names(inspector))
    ordered = [name for name in _TABLE_ORDER if name in existing]
    ordered.extend(sorted(existing - set(ordered)))
    return ordered


def preview_migration(source_url: str) -> dict[str, Any]:
    """Preview source tables and row counts without copying data."""
    try:
        engine = _make_engine(source_url)
        inspector = inspect(engine)
        tables = []
        total_rows = 0

        with engine.connect() as conn:
            for table_name in _ordered_tables(inspector):
                row = conn.execute(select(func.count()).select_from(table(table_name))).fetchone()
                count = row[0] if row else 0
                tables.append({"name": table_name, "row_count": count})
                total_rows += count

        engine.dispose()
        return {"success": True, "tables": tables, "total_rows": total_rows}
    except Exception as exc:
        logger.error("Migration preview failed: %s", exc)
        return {"success": False, "error": str(exc), "tables": [], "total_rows": 0}


def _create_target_schema_from_source(src_engine: Engine, tgt_engine: Engine) -> MetaData:
    """Reflect the source schema and create equivalent target tables."""
    source_metadata = MetaData()
    source_metadata.reflect(bind=src_engine, views=False)
    for table_name in list(source_metadata.tables):
        if table_name in _SKIP_TABLES or not _SAFE_IDENTIFIER.match(table_name):
            source_metadata.remove(source_metadata.tables[table_name])
    source_metadata.create_all(bind=tgt_engine)
    return source_metadata


def _reset_postgres_sequences(engine: Engine, table_names: list[str]) -> None:
    """Move PostgreSQL serial sequences past copied explicit primary keys."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conn:
        for table_name in table_names:
            if not _SAFE_IDENTIFIER.match(table_name):
                continue
            sequence = conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"), {"table_name": table_name}
            ).scalar()
            if not sequence:
                continue
            reflected_table = table(table_name, column("id"))
            max_id = conn.execute(select(func.max(reflected_table.c.id))).scalar()
            conn.execute(
                text("SELECT setval(:sequence_name, :value, :is_called)"),
                {"sequence_name": sequence, "value": max_id or 1, "is_called": max_id is not None},
            )


def migrate_data(
    source_url: str,
    target_url: str,
    *,
    batch_size: int = 500,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Copy all supported tables from *source_url* to *target_url*."""
    errors: list[str] = []
    tables_copied = 0
    rows_copied = 0

    try:
        src_engine = _make_engine(source_url)
        tgt_engine = _make_engine(target_url)
        source_metadata = _create_target_schema_from_source(src_engine, tgt_engine)
        source_inspector = inspect(src_engine)
        table_names = _ordered_tables(source_inspector)

        for table_name in table_names:
            try:
                src_table = source_metadata.tables.get(table_name)
                if src_table is None:
                    continue

                rows = []
                with src_engine.connect() as conn:
                    for row in conn.execute(src_table.select()):
                        rows.append(dict(row._mapping))

                if not rows:
                    tables_copied += 1
                    continue

                target_metadata = MetaData()
                target_metadata.reflect(bind=tgt_engine, only=[table_name])
                target_table = target_metadata.tables[table_name]
                total_for_table = len(rows)

                with tgt_engine.begin() as conn:
                    for offset in range(0, total_for_table, batch_size):
                        batch = rows[offset : offset + batch_size]
                        conn.execute(target_table.insert(), batch)
                        rows_copied += len(batch)
                        if progress_callback:
                            progress_callback(table_name, min(offset + batch_size, total_for_table), total_for_table)

                tables_copied += 1
                logger.info("Copied %s rows from %s", total_for_table, table_name)
            except Exception as exc:
                message = f"Error copying table {table_name}: {exc}"
                logger.error(message)
                errors.append(message)

        try:
            _reset_postgres_sequences(tgt_engine, table_names)
        except Exception as exc:
            message = f"Failed to reset PostgreSQL sequences: {exc}"
            logger.error(message)
            errors.append(message)

        src_engine.dispose()
        tgt_engine.dispose()
        return {
            "success": len(errors) == 0,
            "tables_copied": tables_copied,
            "rows_copied": rows_copied,
            "errors": errors,
        }
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        return {
            "success": False,
            "tables_copied": tables_copied,
            "rows_copied": rows_copied,
            "errors": errors + [str(exc)],
        }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Copy DocuElevate database rows between SQLAlchemy URLs.")
    parser.add_argument("source_url")
    parser.add_argument("target_url")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = migrate_data(args.source_url, args.target_url, batch_size=args.batch_size)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
