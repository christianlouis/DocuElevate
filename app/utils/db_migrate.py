"""
Database migration utility for transferring data between databases.

Copies all table rows from a *source* SQLAlchemy database to a *target*
database.  This is designed for the common scenario of migrating from the
built-in SQLite database to an external PostgreSQL / MySQL instance.

The utility:
1. Creates the schema in the target via ``Base.metadata.create_all``.
2. Copies rows table-by-table in dependency order.
3. Stamps the Alembic version in the target to ``head``.
"""

import logging
import re
from typing import Any

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Tables to skip during migration (Alembic manages its own state).
_SKIP_TABLES = {"alembic_version"}

# Ordered list — parent tables first to respect foreign-key constraints.
_TABLE_ORDER = [
    "documents",
    "files",
    "file_processing_steps",
    "processing_logs",
    "application_settings",
    "settings_audit_log",
    "audit_logs",
    "saved_searches",
    "webhook_configs",
    "shared_links",
]


def _make_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine from *url* with sensible defaults."""
    parsed = make_url(url)
    connect_args: dict[str, Any] = {}
    if parsed.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args)


def _ordered_tables(inspector: Any) -> list[str]:
    """Return table names in safe insertion order.

    Tables listed in ``_TABLE_ORDER`` come first (in that order); any
    remaining tables are appended alphabetically.
    """
    existing = set(inspector.get_table_names())
    ordered: list[str] = []
    for name in _TABLE_ORDER:
        if name in existing and name not in _SKIP_TABLES:
            ordered.append(name)
    for name in sorted(existing):
        if name not in ordered and name not in _SKIP_TABLES:
            ordered.append(name)
    return ordered


def preview_migration(source_url: str) -> dict[str, Any]:
    """Preview what a migration would do without actually copying data.

    Args:
        source_url: Connection string for the source database.

    Returns:
        Dict with ``tables`` (list of dicts with ``name`` and ``row_count``)
        and ``total_rows``.
    """
    try:
        src_engine = _make_engine(source_url)
        src_inspector = inspect(src_engine)
        tables = _ordered_tables(src_inspector)

        result: list[dict[str, Any]] = []
        total = 0
        with src_engine.connect() as conn:
            for table_name in tables:
                if not re.match(r"^[a-zA-Z0-9_]+$", table_name):
                    logger.warning(f"Skipping table with invalid name format: {table_name}")
                    continue
                # table_name is safe — sourced from inspect().get_table_names(), not user input
                quoted_table = conn.dialect.identifier_preparer.quote(table_name)
                row = conn.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).fetchone()  # noqa: S608
                count = row[0] if row else 0
                result.append({"name": table_name, "row_count": count})
                total += count

        src_engine.dispose()
        return {"tables": result, "total_rows": total, "success": True}
    except Exception as exc:
        logger.error(f"Migration preview failed: {exc}")
        return {"success": False, "error": str(exc), "tables": [], "total_rows": 0}


def migrate_data(
    source_url: str,
    target_url: str,
    *,
    batch_size: int = 500,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Copy all data from *source_url* to *target_url*.

    The target schema is created automatically from the application models.
    Alembic is stamped to ``head`` in the target after a successful copy.

    Args:
        source_url: SQLAlchemy connection string for the source DB.
        target_url: SQLAlchemy connection string for the target DB.
        batch_size: Number of rows to insert per batch.
        progress_callback: Optional ``callable(table_name, copied, total)``
            invoked after each batch.

    Returns:
        Dict with ``success`` (bool), ``tables_copied`` (int),
        ``rows_copied`` (int), and ``errors`` (list of str).
    """
    errors: list[str] = []
    tables_copied = 0
    rows_copied = 0

    try:
        src_engine = _make_engine(source_url)
        tgt_engine = _make_engine(target_url)

        # ------------------------------------------------------------------
        # 1.  Create schema in target from application models
        # ------------------------------------------------------------------
        from app.database import Base  # local import to avoid circular deps

        Base.metadata.create_all(bind=tgt_engine)
        logger.info("Target schema created from application models.")

        # ------------------------------------------------------------------
        # 2.  Reflect source schema & determine copy order
        # ------------------------------------------------------------------
        src_meta = MetaData()
        src_meta.reflect(bind=src_engine)

        src_inspector = inspect(src_engine)
        table_names = _ordered_tables(src_inspector)

        SrcSession = sessionmaker(bind=src_engine)
        TgtSession = sessionmaker(bind=tgt_engine)

        # ------------------------------------------------------------------
        # 3.  Copy data table-by-table
        # ------------------------------------------------------------------
        for table_name in table_names:
            try:
                src_session = SrcSession()
                tgt_session = TgtSession()

                src_table = src_meta.tables.get(table_name)
                if src_table is None:
                    continue

                # Read all rows from source
                rows = src_session.execute(src_table.select()).fetchall()
                column_names = [c.name for c in src_table.columns]

                if not rows:
                    logger.info(f"Skipping empty table: {table_name}")
                    tables_copied += 1
                    src_session.close()
                    tgt_session.close()
                    continue

                # Reflect the target table to insert into
                tgt_meta = MetaData()
                tgt_meta.reflect(bind=tgt_engine, only=[table_name])
                tgt_table = tgt_meta.tables.get(table_name)
                if tgt_table is None:
                    errors.append(f"Target table {table_name} not found after schema creation")
                    src_session.close()
                    tgt_session.close()
                    continue

                # Batch insert
                total_for_table = len(rows)
                for i in range(0, total_for_table, batch_size):
                    batch = rows[i : i + batch_size]
                    # strict=False: column count should always match, but tolerate
                    # minor schema drift (e.g. extra columns) to avoid crashing mid-migration.
                    insert_data = [dict(zip(column_names, row, strict=False)) for row in batch]
                    tgt_session.execute(tgt_table.insert(), insert_data)
                    tgt_session.commit()

                    rows_copied += len(batch)
                    if progress_callback:
                        progress_callback(table_name, min(i + batch_size, total_for_table), total_for_table)

                tables_copied += 1
                logger.info(f"Copied {total_for_table} rows from {table_name}")
                src_session.close()
                tgt_session.close()

            except Exception as exc:
                msg = f"Error copying table {table_name}: {exc}"
                logger.error(msg)
                errors.append(msg)

        # ------------------------------------------------------------------
        # 4.  Stamp Alembic to head in the target
        # ------------------------------------------------------------------
        try:
            _stamp_alembic_head(tgt_engine)
            logger.info("Alembic version stamped to head in target database.")
        except Exception as exc:
            msg = f"Failed to stamp Alembic version: {exc}"
            logger.error(msg)
            errors.append(msg)

        src_engine.dispose()
        tgt_engine.dispose()

        return {
            "success": len(errors) == 0,
            "tables_copied": tables_copied,
            "rows_copied": rows_copied,
            "errors": errors,
        }

    except Exception as exc:
        logger.error(f"Migration failed: {exc}")
        return {
            "success": False,
            "tables_copied": tables_copied,
            "rows_copied": rows_copied,
            "errors": errors + [str(exc)],
        }


def _stamp_alembic_head(engine: Engine) -> None:
    """Stamp the Alembic version table to ``head`` in the given engine."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    migrations_dir = str(Path(__file__).resolve().parent.parent.parent / "migrations")
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", migrations_dir)
    alembic_cfg.set_main_option("sqlalchemy.url", "")

    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.stamp(alembic_cfg, "head")
