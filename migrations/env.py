"""Alembic environment configuration for DocuElevate.

This module configures Alembic to use the application's database URL
from ``app.config.settings`` and the SQLAlchemy ``Base.metadata`` so
that autogenerate can detect model changes.

It also supports receiving an existing connection via
``config.attributes["connection"]`` for programmatic invocation from
``app.database.init_db()``, which is essential for in-memory SQLite
databases used in testing.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import application Base and models so target_metadata reflects the full schema.
from app.database import Base

# Ensure all models are imported so Base.metadata is populated.
from app.models import (  # noqa: F401
    ApplicationSettings,
    DocumentMetadata,
    FileProcessingStep,
    FileRecord,
    ProcessingLog,
    SavedSearch,
    SettingsAuditLog,
)

# Alembic Config object – provides access to values in alembic.ini.
config = context.config

# Set up Python logging from the config file (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData object for autogenerate support.
target_metadata = Base.metadata


def _get_url() -> str:
    """Return the database URL, preferring the application config."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    # Fall back to application settings
    from app.config import settings

    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine.
    Calls to ``context.execute()`` emit the given string to the script output.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine (or reuses a connection passed via
    ``config.attributes["connection"]``) and associates it with the context.
    """
    # If a connection was passed programmatically, reuse it.
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        # Already have a connection — run migrations directly.
        context.configure(connection=connectable, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    else:
        # Create a new engine from configuration.
        configuration = config.get_section(config.config_ini_section, {})
        url = _get_url()
        if url:
            configuration["sqlalchemy.url"] = url
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
