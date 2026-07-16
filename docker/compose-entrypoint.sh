#!/bin/sh
set -eu

bootstrap_dir="${DOCUELEVATE_BOOTSTRAP_DIR:-/run/docuelevate-bootstrap}"

if [ -z "${SESSION_SECRET:-}" ]; then
  SESSION_SECRET="$(cat "$bootstrap_dir/session_secret")"
  export SESSION_SECRET
fi

if [ -z "${DATABASE_URL:-}" ]; then
  postgres_password="$(cat "$bootstrap_dir/postgres_password")"
  DATABASE_URL="postgresql+psycopg://docuelevate:${postgres_password}@postgres:5432/docuelevate"
  export DATABASE_URL
fi

exec "$@"
