# ADR-111: LangGraph Postgres Connection Pooling — Checkpointer & Store

**Status**: ✅ IMPLEMENTED (2026-07-08)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-022](ADR-022-LangGraph-State-Checkpointing.md) (checkpointing design), [STATE_AND_CHECKPOINT.md](../technical/STATE_AND_CHECKPOINT.md), audit item S2/A7

## Context

The full-codebase audit (S2/A7, re-confirmed on code 2026-07-07) identified the
**LangGraph persistence layer as the #1 scalability bottleneck**: both
`domains/conversations/checkpointer.py` and `domains/agents/context/store.py`
opened a **single persistent `AsyncConnection`** per worker and handed it to
`InstrumentedAsyncPostgresSaver` / `AsyncPostgresStore`. langgraph serializes
all operations of one connection behind an instance-level `asyncio.Lock`
(`aio.py`), so **every concurrent conversation of a worker queued on one mutex
for every checkpoint read and write** (each pipeline invocation performs many:
`aget_tuple` at start, `aput`/`aput_writes` after every node). PostgreSQL is
provisioned with `max_connections=200` in production — headroom existed.

A second, quieter defect: the single connection had **no reconnection logic**.
A connection killed while idle (PostgreSQL restart, network blip) left the
checkpointer and store permanently broken until an API restart.

Incidentally, [STATE_AND_CHECKPOINT.md](../technical/STATE_AND_CHECKPOINT.md)
had documented an `AsyncConnectionPool` for months while the code used a single
connection — a doc/code contradiction this change resolves in the doc's favor.

### The upstream trap

`langgraph-checkpoint-postgres==3.1.0` (pinned; latest on PyPI as of
2026-07-08) officially accepts an `AsyncConnectionPool` in `conn=`
(`Conn = AsyncConnection[DictRow] | AsyncConnectionPool[...]`,
`_ainternal.py`). **But the saver and the store do not treat pools equally**:

| Class | `_cursor` behavior with a pool (v3.1.0) |
|---|---|
| `AsyncPostgresStore` | Pool-aware: `lock = asyncio.Lock() if is_pooled_conn else self.lock` — the shared lock is bypassed, each operation checks out its own connection |
| `AsyncPostgresSaver` | `async with self.lock, get_connection(...)` — the instance lock is held around **every** operation, pool included |

Passing a pool to the saver alone therefore buys resilience but **zero
concurrency**. The issue is known upstream
([langchain-ai/langgraph#7259](https://github.com/langchain-ai/langgraph/issues/7259),
March 2026) and unfixed on `main` at decision time.

## Decision

1. **Replace both single connections with `psycopg_pool.AsyncConnectionPool`**
   (`psycopg-pool==3.3.0`, now pinned explicitly in `requirements.txt` since it
   became a direct import). Connection kwargs are strictly identical to the
   former single connections and to upstream `from_conn_string`:
   `autocommit=True`, `prepare_threshold=0`, `row_factory=dict_row`.
2. **Override `_cursor` in `InstrumentedAsyncPostgresSaver`** to apply the
   store's pool-aware lock pattern to the saver: a fresh no-op lock when
   `conn` is a pool, the upstream shared lock otherwise. The method body is
   copied verbatim from upstream v3.1.0 — only the lock choice changes, so
   single-connection behavior stays bit-for-bit identical.

   **Safety argument** — the instance lock cannot be load-bearing for data
   consistency: production already runs 4 uvicorn workers whose savers write
   concurrently to the same checkpoint tables with no cross-process lock. From
   PostgreSQL's perspective, an intra-process pool of 8 connections is
   indistinguishable from 8 more workers. The lock only guards
   single-connection exclusivity, which the pool checkout already guarantees —
   the exact reasoning the langgraph authors wrote into the store's `_cursor`.

   **Bounded override risk**: versions are pinned to the patch; the canary
   test `test_upstream_cursor_still_locks_pools` fails loudly on the first
   bump that fixes #7259, ordering the override's removal; the codebase has an
   accepted precedent for pinned upstream patches (`_deepseek_patched.py`).
3. **Pool sizes are Pydantic settings** (`DatabaseSettings`), env-driven with
   defaults in `core/constants.py` next to the documented connection budget:
   `LANGGRAPH_CHECKPOINT_POOL_MIN_SIZE=1` / `MAX_SIZE=8`,
   `LANGGRAPH_STORE_POOL_MIN_SIZE=1` / `MAX_SIZE=4` — all per worker.
   `min=1` keeps the persistent baseline at parity with the former single
   connections (8 total across 4 workers). The store max is lower because
   `AsyncBatchedBaseStore` processes batches sequentially in a single
   background task: the store gains resilience and headroom from the pool,
   not much intra-worker concurrency — the concurrency win is on the
   checkpointer side.
4. **Lifecycle**: the lazy singleton factories are kept (unchanged contract).
   They are already invoked during the FastAPI lifespan startup, so the pool
   opens at boot with fail-fast semantics (`open=False` then
   `await pool.open(wait=True, timeout=database_pool_timeout)` — the
   deprecated implicit async constructor open is avoided; boot aborts if
   `min_size` connections cannot be established). `setup()` / migrations run
   once per process, guaranteed by the singleton guard, and a `setup()`
   failure closes the pool instead of leaking it. Shutdown goes through the
   existing `cleanup_*` hooks in `main.py`, now `await pool.close()`
   (graceful). `check=AsyncConnectionPool.check_connection` validates
   connections on checkout — parity with SQLAlchemy's `pool_pre_ping=True`
   and the fix for the no-reconnection defect.
5. **Prometheus metrics unchanged**: the instrumented wrapper's `aput`/`aget`
   overrides are orthogonal to the connection type; the 5 `checkpoint_*`
   metrics and the custom msgpack serde are untouched.

## Connection budget (documented in `core/constants.py`)

Production: `max_connections=200`, `uvicorn --workers 4`.

| Consumer | Persistent | Worst-case burst |
|---|---|---|
| Superuser reserved | — | 3 |
| SQLAlchemy (4 × 30 + 4 × 30 overflow) | 120 | 240 |
| Checkpointer pools (4 × 1..8) | 4 | 32 |
| Store pools (4 × 1..4) | 4 | 16 |
| postgres-exporter | ~2 | ~2 |
| **Total** | **≈130 ≤ 197** ✅ | **≈290 > 197** ⚠️ |

The worst-case overcommit **predates this change** and is dominated by the
per-worker SQLAlchemy overflow (the old compose comment "SQLAlchemy pool (60)"
missed the ×4 workers). The LangGraph pools add at most +40 vs the former 8
fixed connections. **Follow-up** (out of scope here): right-size the
SQLAlchemy pool.

## Rollback

`LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE=1` (and/or the store equivalent)
reproduces the former fully-serialized single-connection behavior without a
redeploy — the pool checks out its lone connection per operation and the
per-call lock is a no-op. Full rollback = revert the release.

## Alternatives considered

- **Pool without the `_cursor` override**: resilience only, zero concurrency
  gain on the checkpointer — does not lift the audited bottleneck. Rejected.
- **Wait for the upstream fix of #7259**: latest release (3.1.0, 2026-05-12)
  and `main` both unfixed at decision time; timeline unknown. Rejected.
- **Per-request saver instances sharing the pool** (each instance gets its own
  lock): requires recompiling the graph per request or rewiring the
  `AgentRegistry` singleton — far more invasive than a 30-line override, for
  the same result. Rejected.

## Validation evidence

- Unit: factory tests (pool config from settings, singleton, cleanup, setup
  failure handling), behavioral lock tests (pooled `_cursor`s overlap;
  single-connection `_cursor`s stay serialized), upstream canary —
  `tests/unit/domains/conversations/test_checkpointer_pool.py`,
  `tests/unit/domains/agents/context/test_store.py`.
- Integration (real PostgreSQL): 20 concurrent compiled-graph invocations,
  every checkpoint persisted and resumable; 20 concurrent store put/get —
  `tests/integration/test_langgraph_pool_concurrency.py`.
- Benchmark (real PostgreSQL): 20 concurrent tasks × 5 rounds of
  aput+aget_tuple, single connection vs pool —
  `tests/integration/test_checkpointer_pool_benchmark.py`. Measured in the
  dev container (PG on the same Docker network, sub-ms operations — the
  *least* favorable setting for a pool):
  **4 KB payload: 0.115s → 0.104s (×1.10)** ·
  **64 KB payload: 0.180s → 0.127s (×1.42)**.
  The speedup grows with the I/O-bound share of each operation (payload size,
  database latency); the remaining serial share is the per-process CPU cost of
  serde/instrumentation, which no pool can parallelize inside one event loop.
- Non-regression: full `tests/unit` + `tests/agents` suites, HITL replay tests,
  Docker dev boot healthy, `checkpoint_*` metrics present on `/metrics`.

## Consequences

- Checkpoint operations of concurrent conversations no longer serialize on a
  per-worker mutex; concurrency ceiling becomes the pool `max_size` (8/worker).
- Dead idle connections are detected at checkout and replaced (no more
  restart-to-recover).
- **Behavioral nuance (accepted)**: waiting is now bounded. Before, an
  operation queued behind the instance lock indefinitely; with the pool, a
  checkout beyond `max_size` concurrent operations waits at most the pool
  timeout (psycopg default 30 s) then raises `PoolTimeout` — surfaced by the
  existing error taxonomy as `checkpoint_errors_total{error_type="timeout"}`.
  A wait that long was already pathological for the SSE path; failing loudly
  with a metric beats queueing invisibly.
- Two structured upgrade tripwires: the #7259 canary (remove the override when
  upstream ships the fix) and the store-pattern canary (re-audit the override
  if the store's `_cursor` changes shape).
