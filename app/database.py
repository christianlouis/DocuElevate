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
    except exc.SQLAlchemyError as e:
        logger.error(f"Error initializing database: {e}")
        raise


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
