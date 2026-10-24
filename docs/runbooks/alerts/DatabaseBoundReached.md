# DatabaseBoundReached - Runbook

**Severity**: Warning
**Component**: Database (PostgreSQL)
**Impact**: One operation failed: the statement or the session a bound ended
**SLA Impact**: No — a bound ends one caller's operation so that it cannot pin a connection

---

## 📊 Alert Definition

**Alert Name**: `DatabaseBoundReached` (core tier, `alerts-core.yml` — ADR-119)

**Prometheus Expression**:
```promql
sum by (bound) (increase(db_bound_reached_total[15m])) > 0
```

Every connection of the application engine starts with two PostgreSQL bounds
(audit AC-028, amending [ADR-304](../../architecture/ADR-304-No-Transaction-Across-A-Network-Call.md)),
sent at connect time by `infrastructure/database/server_bounds.py`:

- `lock_timeout` = `DATABASE_LOCK_TIMEOUT_MS` — the longest a statement waits for a lock;
- `idle_in_transaction_session_timeout` = `DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS` — the
  longest a session may sit idle inside a transaction before the server ends it.

The engine counts each statement or session one of them ends, in `handle_error`
(`db_bound_reached_total{bound}`): `lock_timeout` and `statement_timeout` from the
server's SQLSTATE (`55P03`, `57014`), `idle_in_transaction_timeout` from the idle span
the engine kept — asyncpg reports the server's end of an idle transaction as a bare
disconnect with no SQLSTATE (measured on PostgreSQL 16).

**Threshold**: zero. Each one names a caller holding a lock or a transaction too long.

**Labels**:
- `severity`: warning
- `component`: postgresql
- `tier`: core
- `bound`: `lock_timeout` | `idle_in_transaction_timeout` | `statement_timeout`

---

## 🔍 Symptoms

- One operation failed: a request answered with an error, a background job logged a failure.
- The API log carries `database_bound_reached` with `bound` and the failure's facts
  (SQLSTATE, table) — never its text.
- Dashboard 03, PostgreSQL row: « Bounds reached (by bound) », and « Tx Duration P95 / P99.9 »
  for the tail of transaction lengths.

---

## 🎯 Possible Causes

### `idle_in_transaction_timeout`
A session kept its transaction open while it waited on something else — a provider, a
model, an embedding batch. That is exactly what ADR-304 forbids: a session lives no
longer than the queries it serves. Commit the reads before the wait, or move the wait
out of the session (a `DetachedConnectorService`, `open_active_client`, a session of its
own around the write).

### `lock_timeout`
A statement waited for a row, a table or an advisory lock that another transaction held
past the bound — usually a transaction that itself waits on something (see above), or a
lock-order inversion between two paths. A transaction may tighten the bound for itself
with `SET LOCAL lock_timeout` (the OAuth refresh door does); it may not loosen it.

### `statement_timeout`
No global `statement_timeout` is set: a caller set one for itself and its statement
outlived it. Read the caller's own bound.

---

## 🔧 Diagnosis

1. Find the event: `database_bound_reached` in Loki (`container="lia-api-prod"`), with
   its `bound`, `sqlstate` and `table`; correlate with `request_id` for a request.
2. For an idle bound, find what the session waited on between its last statement and the
   failure: the events of the same `request_id` (or job) between the two.
3. Read « Tx Duration P95 / P99.9 » (dashboard 03): a P99.9 near the idle bound means
   more sessions are close to it.

---

## 🛠️ Resolution

- Fix the caller (ADR-304): end the transaction before any network call, or hold the wait
  outside the session.
- Never raise a bound to absorb a caller: a bound that is reached is a defect found. A
  bound may be revisited only on measurements of the tail (P99.9 of
  `db_transaction_duration_seconds`), and is set in `.env` (0 disables it).
