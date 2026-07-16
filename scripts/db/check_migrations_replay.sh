#!/usr/bin/env bash
# Verify the Alembic migration chain is replayable FROM SCRATCH (audit F007).
#
# Landmine F007: ``migrate_embeddings_e5_to_openai`` ran ``DELETE FROM
# vector_migrations`` — a table created by LangGraph ``AsyncPostgresStore.setup()``
# at RUNTIME, absent on a virgin database — so a from-scratch ``alembic upgrade
# head`` (disaster recovery, a fresh region/environment) failed at the 71st
# migration. The CI unit job builds fixtures via ``create_all()`` and never
# replays the migrations, so only an execution on an EMPTY database exposes this.
#
# This gate replays the whole chain on an empty database and fails if any
# migration is not replayable, exercises a downgrade/upgrade cycle of the last
# revision, asserts STRUCTURAL model↔schema equivalence (audit F042), and finally
# that the standard ``alembic check`` is green — now promotable because the
# env.py hook empties comment-only autogenerate migrations (F042 tail).
#
# Contract:
#   * ``$DATABASE_URL`` points at an EMPTY database that already has the
#     ``vector`` / ``uuid-ossp`` / ``pg_trgm`` extensions (parity with
#     ``infrastructure/database/init/postgres-init.sql``).
#   * Run from ``apps/api`` (where ``alembic.ini`` lives).
#
# The structural-equivalence step (F042) compares the ORM models against the
# from-scratch-migrated schema and fails on any STRUCTURAL drift (tables,
# columns, types, nullability, indexes, constraints). Cosmetic differences
# (``server_default`` — migration-managed here — and comments) are tolerated;
# the exclusion/classification policy is the single source of truth in
# ``src/infrastructure/database/schema_drift.py``, shared with ``alembic/env.py``.
set -euo pipefail

echo "==> [1/6] alembic upgrade head (replay the full chain on an empty database)"
alembic upgrade head

echo "==> [2/6] verify the database is at the single head"
current="$(alembic current 2>/dev/null || true)"
echo "    current: ${current}"
if ! printf '%s' "${current}" | grep -q "(head)"; then
    echo "ERROR: not at head after 'upgrade head' — the chain is not fully replayable." >&2
    exit 1
fi

echo "==> [3/6] downgrade/upgrade cycle of the last revision"
alembic downgrade -1
alembic upgrade head

echo "==> [4/6] re-verify head after the cycle"
if ! alembic current 2>/dev/null | grep -q "(head)"; then
    echo "ERROR: not at head after the downgrade/upgrade cycle." >&2
    exit 1
fi

echo "==> [5/6] assert STRUCTURAL model<->schema equivalence (audit F042)"
python - <<'PY'
import sys

from sqlalchemy import create_engine

from src.core.config import settings
from src.infrastructure.database.schema_drift import structural_diffs

engine = create_engine(settings.database_url_sync)
try:
    with engine.connect() as conn:
        diffs = structural_diffs(conn)
finally:
    engine.dispose()

if diffs:
    print("ERROR: structural model<->schema drift after a from-scratch migrate:", file=sys.stderr)
    for op in diffs:
        print(f"    {op}", file=sys.stderr)
    print(
        "Fix the models or add a migration. Cosmetic (server_default/comment) drift is "
        "already tolerated; see src/infrastructure/database/schema_drift.py.",
        file=sys.stderr,
    )
    sys.exit(1)
print("OK: no structural model<->schema drift.")
PY

echo "==> [6/6] assert 'alembic check' is green (promoted gate, audit F042)"
# Column/table comments are reconciled against the models by migration
# 58ac1d6c32e0, so the STANDARD ``alembic check`` is naturally green after replay
# WITHOUT any comment-stripping hook — the migrated database is the honest source
# of truth. It must agree with the structural gate above (both 0); a future
# unexpected comment drift now fails here like any other schema change.
alembic check

echo "OK: chain replayable from an empty database + structural equivalence + alembic check (F007 + F042)."
