# app/database.py

import logging
import os

from sqlalchemy import create_engine, exc
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Parse the DATABASE_URL
DB_URL = settings.database_url
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """
    Ensures the SQLite database file and its parent directory exist (if using sqlite).
    Then runs Base.metadata.create_all(bind=engine) to initialize tables.
    Logs a message if a new SQLite DB file is created.
    """
    # 1. Parse the DB URL to see if it's sqlite
    url = make_url(DB_URL)
    if url.get_backend_name() == "sqlite":
        # 2. Extract the database path from the URL
        database_path = url.database  # e.g. "/workdir/db/database.db" or ":memory:"

        if database_path != ":memory:":
            # 3. Ensure directory exists
            db_dir = os.path.dirname(database_path)
            if db_dir and not os.path.exists(db_dir):
                logger.info(f"Creating directory for SQLite DB: {db_dir}")
                os.makedirs(db_dir, exist_ok=True)

            # 4. If the file does not exist, create an empty one
            if not os.path.exists(database_path):
                logger.info(f"Creating new SQLite database file at {database_path}")
                open(database_path, "a").close()

    # 5. Now create tables if they don't exist yet
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialization complete (tables created if not exist).")

        # 6. Run lightweight schema migrations for existing databases
        _run_schema_migrations(engine)
    except exc.SQLAlchemyError as e:
        logger.error(f"Error initializing database: {e}")
        raise


def _run_schema_migrations(engine):
    """
    Apply lightweight schema migrations for columns added after the initial release.
    Each migration is idempotent and safe to run multiple times.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)

    # Migration: Add 'detail' column to processing_logs (added for verbose worker log output)
    if "processing_logs" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("processing_logs")]
        if "detail" not in columns:
            logger.info("Migrating processing_logs: adding 'detail' column")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE processing_logs ADD COLUMN detail TEXT"))
            logger.info("Migration complete: 'detail' column added to processing_logs")

    # Migration: Add file path columns to files table
    if "files" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("files")]
        if "original_file_path" not in columns:
            logger.info("Migrating files: adding 'original_file_path' column")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE files ADD COLUMN original_file_path VARCHAR"))
            logger.info("Migration complete: 'original_file_path' column added to files")

        if "processed_file_path" not in columns:
            logger.info("Migrating files: adding 'processed_file_path' column")
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE files ADD COLUMN processed_file_path VARCHAR"))
            logger.info("Migration complete: 'processed_file_path' column added to files")


def get_db():
    """
    Dependency for FastAPI routes or general DB usage.
    Yields a SQLAlchemy session, and closes it upon exit.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
