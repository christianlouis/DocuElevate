# Database Configuration

DocuElevate uses [SQLAlchemy](https://www.sqlalchemy.org/) as its ORM and [Alembic](https://alembic.sqlalchemy.org/) for schema migrations.  Any SQLAlchemy-compatible database is supported; this guide covers the most common choices.

## Table of Contents

- [Supported Databases](#supported-databases)
- [Configuration](#configuration)
- [SQLite (Development)](#sqlite-development)
- [PostgreSQL (Production)](#postgresql-production)
- [MySQL / MariaDB](#mysql--mariadb)
- [Schema Migrations with Alembic](#schema-migrations-with-alembic)
- [Connection Pooling](#connection-pooling)
- [Backup Procedures](#backup-procedures)
- [Performance Optimization](#performance-optimization)
- [Troubleshooting](#troubleshooting)

---

## Supported Databases

| Database | Recommended Use | Notes |
|----------|----------------|-------|
| **SQLite** | Development, single-user demos | Default. File-based. Not safe for multi-replica deployments. |
| **PostgreSQL** | Production, multi-replica | Strongly recommended for production. Full feature support. |
| **MySQL / MariaDB** | Production (alternative) | Supported; PostgreSQL preferred for JSON column support. |

---

## Configuration

Set the `DATABASE_URL` environment variable to point at your database:

```bash
# SQLite (default)
DATABASE_URL=sqlite:///./app/database.db

# PostgreSQL
DATABASE_URL=postgresql://user:password@host:5432/docuelevate

# PostgreSQL with SSL
DATABASE_URL=postgresql://user:password@host:5432/docuelevate?sslmode=require

# MySQL
DATABASE_URL=mysql+pymysql://user:password@host:3306/docuelevate
```

For Docker Compose, add this to your `.env` file or `docker-compose.yml`:

```yaml
environment:
  DATABASE_URL: postgresql://docuelevate:secret@postgres:5432/docuelevate
```

---

## SQLite (Development)

SQLite requires no additional services and is the zero-configuration default.

```bash
DATABASE_URL=sqlite:///./app/database.db
```

**Limitations:**

- Cannot be safely shared across multiple processes or containers.
- Not suitable for any multi-replica deployment.
- No support for concurrent writes under load.
- Backup is a simple file copy, but requires the application to be stopped to ensure consistency.

**When to use:**  Local development, automated testing, or single-user self-hosted setups with no redundancy requirement.

---

## PostgreSQL (Production)

PostgreSQL is the recommended database for any production deployment.

### Install and Create the Database

```sql
-- Run as a PostgreSQL superuser (e.g. postgres)
CREATE USER docuelevate WITH PASSWORD 'strongpassword';
CREATE DATABASE docuelevate OWNER docuelevate;
GRANT ALL PRIVILEGES ON DATABASE docuelevate TO docuelevate;
```

### Docker Compose with Bundled PostgreSQL

Add a `postgres` service to your `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: docuelevate
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: docuelevate
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  api:
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql://docuelevate:${POSTGRES_PASSWORD}@postgres:5432/docuelevate

volumes:
  postgres_data:
```

Set `POSTGRES_PASSWORD` in your `.env` file.

### Managed Cloud PostgreSQL

Using a managed service (AWS RDS, Google Cloud SQL, Azure Database for PostgreSQL, Supabase, etc.) is recommended for production because it handles backups, point-in-time recovery, and maintenance.

Example for Amazon RDS:

```bash
DATABASE_URL=postgresql://docuelevate:strongpassword@my-instance.us-east-1.rds.amazonaws.com:5432/docuelevate?sslmode=require
```

### Connection String Format

```
postgresql://<user>:<password>@<host>:<port>/<database>[?<options>]
```

Common options:

| Option | Description |
|--------|-------------|
| `sslmode=require` | Require TLS for the connection |
| `sslmode=verify-full` | Require TLS and verify the server certificate |
| `connect_timeout=10` | Connection timeout in seconds |
| `application_name=docuelevate` | Identifies the connection in `pg_stat_activity` |

---

## MySQL / MariaDB

MySQL and MariaDB are supported via the `PyMySQL` driver.

```bash
# Install the driver (it is not included by default)
pip install pymysql cryptography

# Connection string
DATABASE_URL=mysql+pymysql://user:password@host:3306/docuelevate?charset=utf8mb4
```

**Requirements:**

- Use the `utf8mb4` charset for full Unicode support.
- Set `innodb_large_prefix=ON` if using MySQL < 5.7.7.
- PostgreSQL is preferred because SQLAlchemy's JSON column type has better support with it.

---

## Schema Migrations with Alembic

DocuElevate uses Alembic **exclusively** to manage all database schema changes.  On application startup, `init_db()` automatically applies any pending Alembic migrations, so the database schema is always kept in sync with the running code.

> **Note:** Prior to this change, a manual `_run_schema_migrations()` helper in `app/database.py` applied schema changes outside of Alembic.  That function is now **deprecated** and will be removed in a future release.  All schema changes are tracked as Alembic revisions in `migrations/versions/`.

### How It Works

1. **Fresh databases** — `Base.metadata.create_all()` creates all tables from the SQLAlchemy models, then Alembic stamps the version to `head` (no migrations need to run).
2. **Existing databases** — `alembic upgrade head` applies any pending migration scripts.
3. **CLI usage** — You can still run `alembic upgrade head` manually or in CI/CD before the application starts.

### Apply Migrations

Run this command whenever you update DocuElevate or change the schema:

```bash
alembic upgrade head
```

This applies all pending migrations in order.  It is **idempotent** — safe to run multiple times.

### Check Current Version

```bash
alembic current
```

### View Migration History

```bash
alembic history --verbose
```

### Roll Back One Migration

```bash
alembic downgrade -1
```

### Roll Back to a Specific Revision

```bash
alembic downgrade <revision_id>
```

### Creating a New Migration (Developers)

After changing `app/models.py`:

```bash
alembic revision --autogenerate -m "describe your change"
```

Review the generated file in `migrations/versions/` before applying it.

### Automating Migrations in Docker Compose

Add a short-lived `migrate` service that runs before the API and Worker:

```yaml
services:
  migrate:
    image: ghcr.io/christianlouis/docuelevate:latest
    command: alembic upgrade head
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"

  api:
    depends_on:
      migrate:
        condition: service_completed_successfully
```

### Automating Migrations in Kubernetes (Helm)

The Helm chart includes a pre-install and pre-upgrade Job hook that runs `alembic upgrade head` automatically before new pods start.  No manual intervention is needed during `helm upgrade`.

---

## Connection Pooling

SQLAlchemy manages a connection pool automatically.  The defaults are suitable for most deployments.  For high-concurrency or Kubernetes deployments you may want to tune:

```bash
# Optional — these are set via environment variables if you extend app/database.py
# Typical production values:
DB_POOL_SIZE=10         # Number of persistent connections per worker
DB_MAX_OVERFLOW=20      # Additional connections allowed beyond pool_size
DB_POOL_TIMEOUT=30      # Seconds to wait for a connection from the pool
DB_POOL_RECYCLE=1800    # Recycle connections after 30 minutes (avoids stale connections)
```

> **Note:** These environment variables are not exposed in the default `app/config.py`.  If you need to tune them, extend the database engine creation in `app/database.py`.

For **PgBouncer** (external connection pooling), point `DATABASE_URL` at your PgBouncer instance and use transaction-mode pooling:

```bash
DATABASE_URL=postgresql://docuelevate:password@pgbouncer:5432/docuelevate?prepared_statements=false
```

Disable `prepared_statements` when using PgBouncer in transaction mode.

---

## Backup Procedures

### PostgreSQL

**Manual backup:**

```bash
pg_dump -h localhost -U docuelevate -F c docuelevate > docuelevate_$(date +%Y%m%d_%H%M).dump
```

**Restore:**

```bash
pg_restore -h localhost -U docuelevate -d docuelevate docuelevate_20240101_1200.dump
```

**Automated daily backup (cron example):**

```cron
0 2 * * * pg_dump -h localhost -U docuelevate -F c docuelevate | gzip > /backups/docuelevate_$(date +\%Y\%m\%d).dump.gz
```

Use your cloud provider's automated backup feature when available (e.g., RDS automated snapshots, Cloud SQL backups).

### SQLite

```bash
# Stop the application first, or use SQLite's online backup API
cp app/database.db /backups/docuelevate_$(date +%Y%m%d).db
```

---

## Performance Optimization

### PostgreSQL Index Recommendations

Run `ANALYZE` periodically to keep query planner statistics up to date:

```sql
ANALYZE;
```

For large deployments, consider adding indexes on frequently queried columns.  Review the Alembic migrations in `migrations/versions/` for the current schema and add any additional indexes as a new Alembic migration.

### Vacuum and Autovacuum

PostgreSQL's `autovacuum` daemon runs automatically, but for write-heavy workloads you may want to tune it or run `VACUUM ANALYZE` manually after large batch imports.

### Query Monitoring

Enable `pg_stat_statements` to monitor slow queries:

```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;
```

---

## Troubleshooting

### "Connection refused" when starting

- Verify the database host and port are reachable from the application container.
- For Docker Compose, ensure the `postgres` service has started before the `api` service — use `depends_on` with `condition: service_healthy`.
- Check PostgreSQL is listening: `pg_isready -h <host> -p 5432`

### "SSL connection required"

Add `?sslmode=require` to your `DATABASE_URL`, or set `sslmode=disable` if connecting to an internal-only database that does not use TLS.

### Alembic migration fails with "relation already exists"

The database is ahead of Alembic's tracked version.  Stamp the current version without re-running migrations:

```bash
alembic stamp head
```

Then retry `alembic upgrade head`.

### "too many connections" error

Either increase `max_connections` in `postgresql.conf` or add PgBouncer in front of PostgreSQL.  The default PostgreSQL `max_connections` is `100`; reduce `DB_POOL_SIZE` per worker to stay within this limit.

For more help, see the [Troubleshooting Guide](Troubleshooting.md).
