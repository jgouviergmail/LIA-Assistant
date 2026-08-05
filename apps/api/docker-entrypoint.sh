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

# Reference content for a FRESH install (personalities, LLM pricing).
#
# The seed files DELETE before they insert (personalities_seed.sql wipes
# personality_translations and personalities), and the schema propagates that:
# users.personality_id is ON DELETE SET NULL, so an unwanted run resets the
# personality every user has chosen.
#
# TWO independent conditions must therefore hold, and both fail CLOSED:
#   1. INTENT   - APPLY_SEEDS=true, an explicit operator decision;
#   2. TARGET   - the personalities table is verifiably EMPTY.
# The row count is a VETO only. It used to be the trigger ("count == 0 means
# fresh install"), which fired on every psql failure too, since the code read an
# unreadable answer as "0". Reversing its role is what makes it safe: no answer
# now means refuse, never proceed.
#
# See docs/GETTING_STARTED.md ("Reference Content on a Fresh Production Install")
# for the procedure, and tests/unit/test_entrypoint_seed_gate_guard.py for the
# contract this must keep satisfying.
SEEDS_DIR="/app/infrastructure/database/seeds"
if [ -d "$SEEDS_DIR" ]; then
    if [ "${APPLY_SEEDS:-false}" = "true" ]; then
        # Second, INDEPENDENT condition: the target must actually be empty.
        # Intent alone is not enough, because `APPLY_SEEDS` reaches compose through
        # `${APPLY_SEEDS:-false}`, which interpolates from the shell AND from .env
        # (measured) - a value left behind in an env file would otherwise re-arm the
        # deletion on every subsequent deploy. Used only as a VETO, never as a
        # trigger: an unreadable count refuses, exactly like a populated one.
        EXISTING_PERSONALITIES=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM personalities;" 2>/dev/null | tr -d ' ')
        if [ -z "$EXISTING_PERSONALITIES" ]; then
            echo "ERROR: APPLY_SEEDS=true but the personalities count could not be read - SQL seeds SKIPPED (fail-closed)"
        elif [ "$EXISTING_PERSONALITIES" != "0" ]; then
            echo "ERROR: APPLY_SEEDS=true but personalities already holds $EXISTING_PERSONALITIES row(s) - SQL seeds SKIPPED"
            echo "       The seeds delete before inserting; applying them here would reset every user's chosen personality."
            echo "       For a genuine fresh install, start from an empty database."
        else
            echo "APPLY_SEEDS=true and database empty - applying SQL seeds (DESTRUCTIVE: each file deletes its table before re-inserting)"
            for seed_file in "$SEEDS_DIR"/*.sql; do
                if [ -f "$seed_file" ]; then
                    echo "  -> Applying $(basename $seed_file)..."
                    PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -f "$seed_file"
                fi
            done
            echo "SQL seeds applied successfully"
        fi
    else
        echo "Skipping SQL seeds (set APPLY_SEEDS=true for a fresh install only)"
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
