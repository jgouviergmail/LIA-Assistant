# ADR-113: Backend Test Suite Rehabilitation — Integration CI Job, Quarantine Removal, Coverage Ratchet

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Author**: Claude Code (Fable 5)
**Related**: `.github/workflows/ci.yml`, `apps/api/tests/conftest.py`, `apps/api/tests/integration/conftest.py`, [GUIDE_TESTING.md](../guides/GUIDE_TESTING.md), [CI_CD.md](../technical/CI_CD.md), audit 2026-07 (§3.12, recommendation #4)

## Context

The 2026-07 codebase audit surfaced four related test-infrastructure defects:

1. **`tests/integration/` ran in NO CI job** — 250 tests with zero gate,
   while the `test-backend` job already provisioned PostgreSQL (pgvector)
   and Redis service containers it never used for them. Running the suite
   locally proved it had silently rotted (18 failed / 35 errors out of 243
   selected), exactly like the agents suite before it (83 failures, wired
   into CI 2026-07).
2. **13 Testcontainers-backed test files were misfiled under `tests/unit/`**
   (the audit found 10; inventory found 3 more: `test_messages_search.py`,
   `test_feedback_persistence.py`, `test_checkpointer.py` — the last one ran
   NOWHERE: win32-skipped locally, `-m`-deselected in CI). Ten of them were
   additionally quarantined by a `--ignore` list in `ci.yml` that was **100 %
   redundant**: all carry `pytestmark = pytest.mark.integration`, and CI
   collection is byte-identical with and without the list (8916 tests both
   ways, measured).
3. **Coverage gate stuck at 43 %** while actual coverage measured 52.31 % on
   the Linux CI runner (52.13 % locally) — the gate protected nothing.
4. **6 `llm_cache` tests skipped as "implementation changed"** — dead tests
   pinning nothing, violating the no-dead-code rule.

Root-cause taxonomy of the 53 integration failures (measured, one full local
run against the dev PostgreSQL + Redis):

- ~35 setup errors from ONE cause: the auth rate limiter (10 logins/min/IP,
  Redis-backed, not gated by `RATE_LIMIT_ENABLED`) trips as soon as the
  `authenticated_client`/`admin_client` fixtures chain real logins.
- 3×500: the `unaccent` PostgreSQL extension (used by admin user search) is
  created by Alembic migrations but was missing from the conftest engines.
- ~4 i18n assertion failures: tests asserted hardcoded English while the API
  now returns localized messages.
- ~10 genuinely obsolete tests (renamed service methods, changed schemas).

## Decision

**Reclassify, gate, ratchet, repair — and ban `--ignore` quarantines.**

1. **Reclassification**: the 13 files (222 tests) moved to
   `tests/integration/` (subpaths preserved). The `--ignore` list is deleted.
   Pre-commit impact: zero, proven — the hook's `-m "not integration"` filter
   already deselected every one of them (identical 8916-test selection
   before/after). Quarantining tests via `--ignore` without a marker or a
   ticket is now explicitly forbidden (a quarantined test never comes back;
   it also hides suite rot).

2. **New CI job `test-backend-integration`** (needs: lint-backend), same
   PostgreSQL/Redis services, running
   `pytest tests/integration/ -m "not e2e and not benchmark and not multiprocess" --no-cov`
   (465 tests; `slow` included — those tests run nowhere else; heavy markers
   stay out of PR CI; `--no-cov` because the coverage gate belongs to the
   unit job).
   Plumbing decision: the job sets **`TEST_DATABASE_URL`** — the only DB
   variable that survives the conftest's `load_dotenv(".env.test",
   override=True)` — and `tests/conftest.py::_detect_environment` now honors
   it explicitly (external DB) with the Testcontainers fallback unchanged.
   The service credentials (`test:test@localhost:5432/test_db`) deliberately
   mirror `.env.test` so tests reading `settings.database_url` directly
   (LangGraph checkpointer) reach the same database. The dead "localhost
   optimization" branch in `_detect_environment` (computed but never
   consumed) is deleted per the docstring-honesty rule.

3. **Test-infra repairs** (no product-code changes):
   - `tests/integration/conftest.py` purges `auth:*` rate-limit buckets
     through the limiter's own Redis client before each test (production
     semantics of "a fresh client per test"); the limiter singleton is also
     reset alongside the Redis singletons (same loop-affinity hygiene).
   - Conftest engines create `unaccent` alongside `vector`, mirroring the
     migrations.
   - Obsolete tests rewritten against the current API; i18n assertions made
     locale-aware.

4. **Coverage ratchet doctrine**: gate raised 43 → **45** (pyproject addopts
   + ci.yml, kept in sync), then **+2 points per release, never lowered**,
   toward the audit's 75 % target. Raising requires ≥2 points of measured
   headroom in CI. Documented in GUIDE_TESTING.md.

5. **`llm_cache` skipped tests repaired, not deleted**: the code under test
   is alive; the 2 serialization tests now trigger the real failure path
   (str() raising — the safe conversion never calls `__reduce__` anymore)
   and the 4 metrics tests patch the real import site
   (`metrics_agents`, in-function import) with an async `estimate_cost_usd`.

## Consequences

- `tests/integration/` (472 tests) is gated on every PR; suite rot is now
  visible within one CI run instead of accumulating for months.
- Zero test loss: unit 9169 → 8947, integration 250 → 472 (Σ constant);
  CI unit selection unchanged at 8916.
- Local equivalent: `TEST_DATABASE_URL=...lia_test task test:backend:integration`
  (disposable database REQUIRED — fixtures drop/recreate all tables), with
  Testcontainers as the no-config fallback.
- `task ci` now mirrors the full pipeline (unit + agents + integration).
- Known debt, deliberately out of scope: `test_metrics_langgraph_state.py`
  (whole module skipped "metrics not implemented") and
  `tests/unit/infrastructure/test_database_session.py:66` (skip "needs fix")
  — same disease as the llm_cache skips, to be repaired or deleted in a
  follow-up; the agents suite's 209 API-key skips (strategy: deterministic
  fake-LLM provider for plumbing tests + nightly `llm_live` tier for the
  small real-LLM core).
