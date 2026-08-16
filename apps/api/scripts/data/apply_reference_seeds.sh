#!/bin/sh
# Atomic reference-seed application (ADR-215, B09).
#
# ONE psql process, ON_ERROR_STOP=1, --single-transaction: the five seed
# files plus the blocking verification file either all commit (marker
# included) or none do. Before touching the database, the wrapper recomputes
# the exact six-record bundle digest and refuses a mismatch — a mutated seed
# can never run under a stale identity.
#
# Digest algorithm (must match scripts/install/seed_bundle.py): for each of
# the six files IN INVOCATION ORDER, one ASCII record of
#   <repo-relative POSIX path> NUL <lowercase sha256 of raw bytes> LF
# hashed together with sha256.
#
# Usage: apply_reference_seeds.sh <expected-64-hex-digest>
# Env:   PSQL_BIN (test indirection, default psql) + the PG* connection vars.
set -eu

SEEDS_DIR="${SEEDS_DIR:-/app/infrastructure/database/seeds}"
PSQL_BIN="${PSQL_BIN:-psql}"

SEED_FILES="google_api_pricing_seed.sql
image_generation_pricing_seed.sql
llm_config_seed.sql
llm_pricing_seed.sql
personalities_seed.sql
verify_reference_seeds.sql"

expected="${1:?usage: apply_reference_seeds.sh <expected-seed-bundle-sha256>}"
case "$expected" in
  *[!0-9a-f]*) echo "ERROR: expected digest must be 64 lowercase hex" >&2; exit 2 ;;
esac
if [ "${#expected}" -ne 64 ]; then
  echo "ERROR: expected digest must be 64 lowercase hex" >&2
  exit 2
fi

for name in $SEED_FILES; do
  if [ ! -f "$SEEDS_DIR/$name" ]; then
    echo "ERROR: missing seed file $name" >&2
    exit 2
  fi
done
# NUL bytes cannot live in a POSIX shell variable (command substitution
# strips them) — stream the records straight into the hashing pipe instead,
# so the digest matches scripts/install/seed_bundle.py byte for byte.
actual="$(
  for name in $SEED_FILES; do
    file_hash="$(sha256sum "$SEEDS_DIR/$name" | cut -d' ' -f1)"
    # Logical repository-relative name, never the absolute container path.
    printf '%s\0%s\n' "infrastructure/database/seeds/${name}" "$file_hash"
  done | sha256sum | cut -d' ' -f1
)"
if [ "$actual" != "$expected" ]; then
  echo "ERROR: seed bundle digest mismatch (expected $expected, got $actual) - refusing to seed" >&2
  exit 3
fi

# Single transaction over all six files; the verifier runs LAST and the
# marker commits with the data or not at all.
"$PSQL_BIN" -X \
  --set ON_ERROR_STOP=1 \
  --single-transaction \
  --set "seed_bundle_version=$expected" \
  -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -f "$SEEDS_DIR/google_api_pricing_seed.sql" \
  -f "$SEEDS_DIR/image_generation_pricing_seed.sql" \
  -f "$SEEDS_DIR/llm_config_seed.sql" \
  -f "$SEEDS_DIR/llm_pricing_seed.sql" \
  -f "$SEEDS_DIR/personalities_seed.sql" \
  -f "$SEEDS_DIR/verify_reference_seeds.sql"
