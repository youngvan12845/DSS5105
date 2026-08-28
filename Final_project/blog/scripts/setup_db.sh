#!/usr/bin/env bash
# Create the cheeseoo database for local PostgreSQL (macOS EDB installer).
# Usage:
#   export PGPASSWORD='your_postgres_password'
#   ./scripts/setup_db.sh

set -euo pipefail

PG_BIN="/Library/PostgreSQL/18/bin"
if [[ -d "$PG_BIN" ]]; then
  export PATH="$PG_BIN:$PATH"
fi

DB_NAME="${POSTGRES_DB:-cheeseoo}"
DB_USER="${POSTGRES_USER:-postgres}"
DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5432}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  echo "Set PGPASSWORD first, e.g.:"
  echo "  export PGPASSWORD='your_postgres_password'"
  exit 1
fi

echo "Creating database '$DB_NAME' (if not exists)..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 \
  || psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";"

echo "Done. Database '$DB_NAME' is ready."
echo "Next:"
echo "  cp .env.example .env   # set POSTGRES_PASSWORD"
echo "  python manage.py migrate"
