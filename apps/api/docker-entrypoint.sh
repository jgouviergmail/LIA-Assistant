#!/usr/bin/env sh
set -e

echo "=== LIA API Dev Entrypoint ==="

# Wait for PostgreSQL
echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h postgres -U postgres -d lia > /dev/null 2>&1; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 1
done
echo "PostgreSQL is ready"

# Run migrations
echo "Running database migrations..."
alembic upgrade head
echo "Database migrations completed successfully"

# Run SQL seeds if available (only if APPLY_SEEDS=true or personalities table is empty)
SEEDS_DIR="/app/infrastructure/database/seeds"
if [ -d "$SEEDS_DIR" ]; then
    # Check if personalities table is empty (first deployment)
    PERSONALITIES_COUNT=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM personalities;" 2>/dev/null | tr -d ' ' || echo "0")

    if [ "${APPLY_SEEDS:-false}" = "true" ] || [ "$PERSONALITIES_COUNT" = "0" ]; then
        echo "Applying SQL seeds..."
        for seed_file in "$SEEDS_DIR"/*.sql; do
            if [ -f "$seed_file" ]; then
                echo "  -> Applying $(basename $seed_file)..."
                PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f "$seed_file"
            fi
        done
        echo "SQL seeds applied successfully"
    else
        echo "Skipping SQL seeds (personalities table has $PERSONALITIES_COUNT entries, use APPLY_SEEDS=true to force)"
    fi
fi

# Start application
echo "Starting application..."
exec "$@"
