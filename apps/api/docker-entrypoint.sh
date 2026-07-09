#!/usr/bin/env sh
set -e

echo "=== LIA API Entrypoint ==="

# Wait for PostgreSQL
# Fallbacks mirror the compose defaults so the image still boots when run
# outside compose (an unset var would expand empty and loop forever).
echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-lia}" > /dev/null 2>&1; do
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

# Prometheus multiprocess mode — enabled ONLY when launched with multiple uvicorn
# workers (prod uses --workers 4). Single-worker dev (--reload) is left untouched.
# Each worker writes its metric files here; the worker that binds the metrics port
# serves the AGGREGATE via MultiProcessCollector. RAM-backed (/dev/shm) to spare the
# SD card on the Raspberry Pi prod host. Override with PROMETHEUS_MULTIPROC_DIR.
case "$*" in
    *--workers*)
        # Non-fatal under `set -e`: if the dir cannot be (re)created, fall back to
        # single-process metrics rather than aborting startup. Dir creation runs
        # inside the `if` condition so a failure never propagates to `set -e`.
        _mp_dir="${PROMETHEUS_MULTIPROC_DIR:-/dev/shm/prometheus_multiproc}"
        if rm -rf "$_mp_dir" 2>/dev/null && mkdir -p "$_mp_dir" 2>/dev/null; then
            export PROMETHEUS_MULTIPROC_DIR="$_mp_dir"
            echo "Prometheus multiprocess mode enabled (PROMETHEUS_MULTIPROC_DIR=$_mp_dir)"
        else
            echo "WARN: could not prepare '$_mp_dir' — Prometheus multiprocess DISABLED (single-process metrics, app still starts)"
        fi
        ;;
esac

# Start application
echo "Starting application..."
exec "$@"
