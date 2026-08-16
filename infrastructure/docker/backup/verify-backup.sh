#!/usr/bin/env bash
# ============================================================================
# LIA — PostgreSQL backup verification (ADR-109)
#
# Takes the LATEST dump produced by the postgres-backup sidecar, restores it
# into a THROWAWAY pgvector container (never touches the live database), then
# compares against the live source:
#   - alembic_version (schema revision)
#   - row counts of VERIFY_TABLES (side by side, drift-tolerant on a live DB)
#   - number of tables in the public schema
#
# Works in dev (Windows Git Bash) and prod (Raspberry Pi) — dumps are read via
# `docker cp`, so it does not matter whether /backups is a named volume (dev)
# or a host bind mount (prod).
#
# Usage:
#   bash infrastructure/docker/backup/verify-backup.sh          # dev (default)
#   BACKUP_CONTAINER=lia-postgres-backup-prod \
#   SOURCE_CONTAINER=lia-postgres-prod \
#   bash infrastructure/docker/backup/verify-backup.sh          # prod
#
# Env overrides:
#   BACKUP_CONTAINER  sidecar holding /backups   (default: lia-postgres-backup-dev)
#   SOURCE_CONTAINER  live postgres container    (default: lia-postgres-dev)
#   VERIFY_IMAGE      throwaway restore image    (default: pgvector/pgvector:pg16)
#   VERIFY_TABLES     space-separated tables     (default: users conversations conversation_messages)
#   BACKUP_FILE       dump path INSIDE the sidecar (default: newest /backups/last/*.sql.gz)
#
# Exit codes: 0 = PASS, 1 = FAIL (restore errors, alembic mismatch, empty
# restored table while source is non-empty), 2 = environment/usage error.
# ============================================================================

set -euo pipefail

BACKUP_CONTAINER="${BACKUP_CONTAINER:-lia-postgres-backup-dev}"
SOURCE_CONTAINER="${SOURCE_CONTAINER:-lia-postgres-dev}"
VERIFY_IMAGE="${VERIFY_IMAGE:-pgvector/pgvector:pg16}"
VERIFY_TABLES="${VERIFY_TABLES:-users conversations conversation_messages}"
BACKUP_FILE="${BACKUP_FILE:-}"

VERIFY_CONTAINER="lia-backup-verify-$$"
WORKDIR="$(mktemp -d)"
FAIL=0

log()  { printf '%s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

cleanup() {
    docker rm -f "$VERIFY_CONTAINER" >/dev/null 2>&1 || true
    rm -rf "$WORKDIR"
}
trap cleanup EXIT

# --- Preconditions -----------------------------------------------------------
docker inspect "$BACKUP_CONTAINER" >/dev/null 2>&1 \
    || die "backup container '$BACKUP_CONTAINER' not found (is the stack up?)"
docker inspect "$SOURCE_CONTAINER" >/dev/null 2>&1 \
    || die "source container '$SOURCE_CONTAINER' not found (is the stack up?)"

PGUSER="$(docker exec "$SOURCE_CONTAINER" printenv POSTGRES_USER)" \
    || die "cannot read POSTGRES_USER from $SOURCE_CONTAINER"
PGDB="$(docker exec "$SOURCE_CONTAINER" printenv POSTGRES_DB)" \
    || die "cannot read POSTGRES_DB from $SOURCE_CONTAINER"

# --- Locate the latest dump inside the sidecar --------------------------------
if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE="$(docker exec "$BACKUP_CONTAINER" sh -c \
        "ls -1t /backups/last/*.sql.gz 2>/dev/null | grep -v -- '-latest' | head -1")" || true
    [ -n "$BACKUP_FILE" ] || die "no dump found in /backups/last — run 'task backup:now' first"
fi
log "==> Dump under verification: $BACKUP_FILE"

# Relative destination path: avoids MSYS path mangling under Git Bash.
( cd "$WORKDIR" && docker cp "$BACKUP_CONTAINER:$BACKUP_FILE" ./dump.sql.gz )
DUMP_SIZE="$(wc -c < "$WORKDIR/dump.sql.gz")"
log "==> Dump copied ($DUMP_SIZE bytes)"
[ "$DUMP_SIZE" -gt 1024 ] || die "dump suspiciously small (<1KB)"

# --- Throwaway restore target --------------------------------------------------
# Same image as the live server => same major version + pgvector available.
# trust auth is acceptable: container is unpublished, local, and destroyed on exit.
log "==> Starting throwaway container ($VERIFY_IMAGE)..."
docker run -d --name "$VERIFY_CONTAINER" \
    -e POSTGRES_USER="$PGUSER" \
    -e POSTGRES_DB="$PGDB" \
    -e POSTGRES_HOST_AUTH_METHOD=trust \
    "$VERIFY_IMAGE" >/dev/null

for i in $(seq 1 30); do
    if docker exec "$VERIFY_CONTAINER" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1; then
        break
    fi
    [ "$i" -eq 30 ] && die "throwaway postgres did not become ready in 60s"
    sleep 2
done
log "==> Throwaway postgres ready"

# --- Restore -------------------------------------------------------------------
log "==> Restoring dump (this is the real proof)..."
docker exec -i "$VERIFY_CONTAINER" sh -c \
    "gunzip -c | psql -q -v ON_ERROR_STOP=0 -U '$PGUSER' -d '$PGDB'" \
    < "$WORKDIR/dump.sql.gz" > /dev/null 2> "$WORKDIR/restore.err" || true

ERRORS="$(grep -c '^ERROR' "$WORKDIR/restore.err" || true)"
if [ "$ERRORS" -gt 0 ]; then
    log "!! $ERRORS SQL error(s) during restore — first 10:"
    grep '^ERROR' "$WORKDIR/restore.err" | head -10
    FAIL=1
else
    log "==> Restore completed with 0 SQL errors"
fi

# --- Comparisons ----------------------------------------------------------------
psql_src() { docker exec "$SOURCE_CONTAINER" psql -tA -U "$PGUSER" -d "$PGDB" -c "$1"; }
psql_dst() { docker exec "$VERIFY_CONTAINER" psql -tA -U "$PGUSER" -d "$PGDB" -c "$1"; }

ALEMBIC_SRC="$(psql_src 'SELECT version_num FROM alembic_version' | tr -d '[:space:]')"
ALEMBIC_DST="$(psql_dst 'SELECT version_num FROM alembic_version' | tr -d '[:space:]')"
if [ -n "$ALEMBIC_DST" ] && [ "$ALEMBIC_SRC" = "$ALEMBIC_DST" ]; then
    log "==> alembic_version: MATCH ($ALEMBIC_DST)"
else
    log "!! alembic_version MISMATCH: source='$ALEMBIC_SRC' restored='$ALEMBIC_DST'"
    FAIL=1
fi

TABLES_SRC="$(psql_src "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
TABLES_DST="$(psql_dst "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
log "==> public tables: source=$TABLES_SRC restored=$TABLES_DST"
[ "$TABLES_SRC" = "$TABLES_DST" ] || { log "!! public table count differs"; FAIL=1; }

# Row counts: strict equality is not required (the source is live and may have
# moved since the dump) — but a table that is EMPTY in the restore while the
# source has rows means data loss => FAIL.
log "==> Row counts (source vs restored):"
for table in $VERIFY_TABLES; do
    SRC_COUNT="$(psql_src "SELECT count(*) FROM \"$table\"" 2>/dev/null | tr -d '[:space:]')" || SRC_COUNT="?"
    DST_COUNT="$(psql_dst "SELECT count(*) FROM \"$table\"" 2>/dev/null | tr -d '[:space:]')" || DST_COUNT="?"
    STATUS="OK"
    if [ "$DST_COUNT" = "?" ]; then
        STATUS="FAIL (table missing in restore)"; FAIL=1
    elif [ "$SRC_COUNT" != "?" ] && [ "$SRC_COUNT" -gt 0 ] && [ "$DST_COUNT" -eq 0 ]; then
        STATUS="FAIL (restored empty, source has rows)"; FAIL=1
    elif [ "$SRC_COUNT" != "$DST_COUNT" ]; then
        STATUS="WARN (live drift since dump)"
    fi
    printf '    %-28s source=%-8s restored=%-8s %s\n' "$table" "$SRC_COUNT" "$DST_COUNT" "$STATUS"
done

# --- Verdict --------------------------------------------------------------------
if [ "$FAIL" -eq 0 ]; then
    log "==> VERIFY PASS — dump is restorable and schema-consistent"
else
    log "==> VERIFY FAIL — see messages above"
fi
exit "$FAIL"
