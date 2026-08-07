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
#   2. TARGET   - verifiably NOBODY HAS CHOSEN a personality yet.
# The count is a VETO only. It used to be the trigger ("count == 0 means fresh
# install"), which fired on every psql failure too, since the code read an
# unreadable answer as "0". Reversing its role is what makes it safe: no answer
# now means refuse, never proceed.
#
# The veto counts USERS holding a personality, not personality ROWS — and that
# correction is what makes this branch reachable at all. Migrations run first
# (`alembic upgrade head`, just above) and `add_personalities` inserts fourteen
# default rows unconditionally, so "the personalities table is empty" was NEVER
# true after a migration pass. Measured 2026-08-07 on a genuinely fresh
# database: "personalities already holds 14 row(s) - SQL seeds SKIPPED". The
# reference bundle could therefore never be applied by ANY installation, which
# left every fresh install with the migrations' 91 LLM prices instead of the
# bundle's 242 — and a model priced by the bundle alone is billed by the
# provider and recorded at ZERO.
#
# What the gate exists to protect is a user's CHOSEN personality
# (users.personality_id is ON DELETE SET NULL). Fourteen rows a migration put
# there are nobody's choice; a user pointing at one is. So the veto now asks
# exactly the question the comment above always claimed it asked.
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
        EXISTING_PERSONALITIES=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM users WHERE personality_id IS NOT NULL;" 2>/dev/null | tr -d ' ')
        # Third fail-closed gate (ADR-215): a non-empty seed-bundle marker
        # means a previous bundle already committed — re-seeding over it is
        # never an entrypoint decision.
        EXISTING_MARKER=$(PGPASSWORD="${POSTGRES_PASSWORD}" psql -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT COUNT(*) FROM system_settings WHERE key = 'SELF_HOST_SEED_BUNDLE';" 2>/dev/null | tr -d ' ')
        if [ -z "$EXISTING_PERSONALITIES" ] || [ -z "$EXISTING_MARKER" ]; then
            echo "ERROR: APPLY_SEEDS=true but the personality-choice/marker count could not be read - SQL seeds SKIPPED (fail-closed)"
        elif [ "$EXISTING_PERSONALITIES" != "0" ]; then
            echo "ERROR: APPLY_SEEDS=true but $EXISTING_PERSONALITIES user(s) already chose a personality - SQL seeds SKIPPED"
            echo "       The seeds delete before inserting; applying them here would reset those choices."
            echo "       For a genuine fresh install, start from an empty database."
        elif [ "$EXISTING_MARKER" != "0" ]; then
            echo "ERROR: APPLY_SEEDS=true but a SELF_HOST_SEED_BUNDLE marker already exists - SQL seeds SKIPPED"
        elif [ -z "${SEED_BUNDLE_SHA256:-}" ]; then
            echo "ERROR: APPLY_SEEDS=true but SEED_BUNDLE_SHA256 is not set - SQL seeds SKIPPED (fail-closed)"
        else
            echo "APPLY_SEEDS=true and nobody has chosen a personality - applying the seed bundle atomically (DESTRUCTIVE: each seed deletes its table before re-inserting; ADR-215: one transaction, blocking postconditions, marker)"
            # ONE wrapper invocation: digest-verified, single psql process,
            # single transaction over the five domains plus the verifier.
            if PGPASSWORD="${POSTGRES_PASSWORD}" SEEDS_DIR="$SEEDS_DIR" sh /app/scripts/data/apply_reference_seeds.sh "$SEED_BUNDLE_SHA256"; then
                echo "SQL seeds applied and verified successfully"
            else
                echo "ERROR: seed bundle application FAILED and was rolled back - the database is unchanged" >&2
                exit 1
            fi
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
# Keyed on the EFFECTIVE worker count, not on a command-line flag: the flag was
# removed from the image's CMD so that WEB_CONCURRENCY governs (a pinned
# --workers overrode it and made every other layer read a number nobody used).
# `case` on the flag would then never match, and production would fall back to
# per-worker metrics -- four workers each reporting a quarter of the truth.
# `-gt 1`, and the runtime check is what caught it: keying on the mere
# PRESENCE of a worker count turned multiprocess mode on for a single worker
# too, which the flag-based test never did (prod always passed 4). One worker
# needs no aggregation, and the MultiProcessCollector path is not free.
_workers="${WEB_CONCURRENCY:-1}"
case "$*" in *--workers*) _workers=2 ;; esac
if [ "$_workers" -gt 1 ] 2>/dev/null; then
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
fi

# Start application
echo "Starting application..."
exec "$@"
