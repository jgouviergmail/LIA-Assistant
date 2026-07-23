# Security Program — Lot 0: Corrective Bedrock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline execution mandated by the user — no subagents). Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Close the four pre-existing defects that Lots 1–6 would otherwise inherit: account-deletion purge gaps (`open_loops`, `phone_calls`), the absent user-data completeness guard, the dead `refresh_session` + false "auto-refresh" documentation, and the duplicated O(N) session-invalidation path.

**Architecture:** No new feature. One new module (`user_data_map.py`) becomes the single source of truth classifying every SQLAlchemy table and every `users` column; a CI guard cross-checks it against the metadata AND against the purge statements (made introspectable via a module-level `build_purge_statements`). Dead code is deleted; duplicated invalidation delegates to the indexed `SessionStore` implementation.

**Tech Stack:** SQLAlchemy 2.x metadata introspection, pytest (asyncio auto), existing Redis SessionStore.

## Global Constraints

- Master doc: `docs/superpowers/specs/2026-07-23-security-account-program.md` (facts F4, F5, F13).
- No behavior change beyond: 2 additional purged tables, invalidation via index instead of SCAN.
- MyPy strict, Black 100, Google docstrings, structlog only, UTC datetimes.
- Gates: `task lint` + `task test:backend:unit:fast` green before lot closure.

---

### Task 1: Purge gaps + introspectable purge statements

**Files:**
- Modify: `apps/api/src/domains/users/account_deletion_service.py` (imports; extract `build_purge_statements(user_id) -> list[tuple[str, Delete]]` module-level; loop over it in `_purge_user_data_tables`; append `open_loops` and `phone_calls` deletes to Group 2 before `connectors`)
- Test: `apps/api/tests/unit/domains/users/test_account_deletion_service.py`

**Interfaces:**
- Produces: `build_purge_statements(user_id: UUID) -> list[tuple[str, Delete]]` — consumed by Task 2's guard and by the service itself. Table-name keys keep the existing count-dict names.

- [x] **Step 1: Failing test** — `TestPurgeStatements::test_covers_open_loops_and_phone_calls` asserts `{"open_loops", "phone_calls"}` ⊆ statement names, and `TestPurgeStatements::test_statement_names_match_target_tables` asserts each declared name equals `stmt.table.name` (self-consistency oracle). Run: fails (`ImportError: build_purge_statements`).
- [x] **Step 2: Implement** — extract the existing group1+group2 literal into `build_purge_statements`, add `OpenLoop`/`PhoneCall` imports and deletes. Run: passes.

### Task 2: `user_data_map.py` + total completeness guard

**Files:**
- Create: `apps/api/src/domains/users/user_data_map.py`
- Create: `apps/api/tests/unit/domains/users/test_user_data_map_guard.py`
- Modify: `apps/api/tests/unit/domains/users/test_account_deletion_service.py` (parametrized scrub oracle)

**Interfaces:**
- Produces: `TableDataClass` (USER_PURGED | USER_CASCADE | USER_ROW_SCRUBBED | BILLING_RETAINED | GLOBAL), `ExportPolicy` (FULL | EXCLUDED), `TableRule(data_class, export, reason)`, `TABLE_RULES: dict[str, TableRule]`, `UserColumnClass` (SCRUBBED | RETAINED_IDENTITY | RETAINED_LIFECYCLE | RETAINED_PREFERENCE), `USER_COLUMNS: dict[str, UserColumnClass]`, `EXTERNAL_TABLES: frozenset[str]` (LangGraph + alembic, out-of-band). Lot 5 consumes `ExportPolicy.FULL` entries.

**Guard assertions (each its own test):**
1. `Base.metadata.tables` keys == `TABLE_RULES` keys (both directions, diff in message).
2. `{name for name, _ in build_purge_statements(uuid4())}` == `{t for t, r in TABLE_RULES.items() if r.data_class is USER_PURGED}`.
3. Every `USER_CASCADE` table has ≥ 1 FK with `ondelete="CASCADE"` targeting a `USER_PURGED` table.
4. `User.__table__.columns` keys == `USER_COLUMNS` keys.
5. Every `EXCLUDED`/retained rule carries a non-empty `reason`; `users` is `USER_ROW_SCRUBBED`.
6. (in deletion tests) For every `SCRUBBED` column: sentinel value → `_mark_user_deleted` → attribute is `None`.

- [x] **Step 1:** Write the guard tests → red (module missing).
- [x] **Step 2:** Write `user_data_map.py` with the full classification (≈48 tables, ≈75 columns; canonical table in module docstring cites ADR-067 + program doc) → iterate until guard green. Any surprise table found by assertion 1 gets classified deliberately, never blindly.
- [x] **Step 3:** Parametrized scrub test from `USER_COLUMNS` → green (characterizes existing scrub; fails on future unscrubbed additions).

### Task 3: Dead `refresh_session` + false auto-refresh docs

**Files:**
- Modify: `apps/api/src/infrastructure/cache/session_store.py` (delete method, lines 338-374)
- Modify: `apps/api/src/domains/auth/router.py` (claims at 215, 226, 250-252, 277 → "Sessions have a fixed lifetime — 7 days, or 30 days with remember-me; re-authenticate via /auth/login when a session expires.")
- Modify: `apps/api/src/domains/auth/service.py` (comment block ~163)
- Modify: `apps/api/tests/unit/test_session_store.py` (delete the 2 `refresh_session` tests)

- [x] **Step 1:** Remove tests + method + fix all 5 claim sites in the same change (doc-contradiction rule: never leave the contradiction). Run session-store + auth unit tests: green; grep `refresh_session|automatically refreshed|auto-refresh` in `src/` returns only MCP OAuth (legitimate).

### Task 4: Consolidate `_invalidate_all_user_sessions`

**Files:**
- Modify: `apps/api/src/domains/users/service.py` (body → `SessionStore(await get_redis_session()).delete_all_user_sessions(str(user_id))` inside the existing try/except fail-soft envelope; docstring rewritten — no more "Future Phase" claim)
- Modify: `apps/api/tests/unit/users/test_user_service.py`, `apps/api/tests/unit/test_users_service.py` (SCAN-specific tests → delegation + error-swallow tests)

**Interfaces:**
- Consumes: `SessionStore.delete_all_user_sessions(user_id: str) -> int` (existing, indexed O(M)).
- Unchanged signature: callers (deactivation, GDPR delete, `AccountDeletionService`) untouched.

- [x] **Step 1:** Rewrite tests: asserts `delete_all_user_sessions` awaited with `str(user_id)`; SessionStore exception → logged, not raised → red (SCAN still in place).
- [x] **Step 2:** Swap implementation → green.

### Task 5: Lot gates + review

- [x] `task lint` clean; `task test:backend:unit:fast` green (fresh counts recorded).
- [x] Deep self-review (systemic rules checklist) + program doc tracker/session-log update.
