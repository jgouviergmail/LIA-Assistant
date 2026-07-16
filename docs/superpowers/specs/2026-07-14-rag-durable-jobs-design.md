# RAG durable jobs — design (audit F001)

**Status:** Approved design (2026-07-14). Phase 1 ready for implementation planning.
**Finding:** F001 — "Workflows RAG non durables" (MAJEUR · DONNÉES/FIABILITÉ).
**Scope of this spec:** Phase 1 (durable foundation for upload & Drive sync). Phase 2
(generational reindex) and Phase 3 (exhaustive crash matrix) are outlined only.

---

## 1. Context

The `rag_spaces` domain ingests documents into per-user / system knowledge spaces:
`RAGSpace → RAGDriveSource → RAGDocument → RAGChunk` (embeddings). Retrieval reads
chunks for the agent RAG tools.

**Already fixed (F001 partial, preserved by this design):**
- Drive sync completion ordering and failure counting.
- Reindex lock: Redis TTL flag (`REINDEX_FLAG_KEY`) acquired atomically (SET NX),
  renewed per document (`_renew_reindex_lock` heartbeat).
- Drive sync lock: atomic DB claim `try_acquire_sync_lock`.

**Residual gaps (this spec addresses gap 1; gaps 2–3 phased):**
1. **Process-local tasks** — upload processing (`router.py`), reindex (`reindex.py`)
   and Drive sync run as in-process `safe_fire_and_forget` asyncio tasks. A process
   crash loses the task: the document is stuck in `processing`, the source in
   `syncing`, and nothing resumes them.
2. **Destructive reindex** — `reindex.py` runs `DELETE FROM rag_chunks` up front, then
   re-processes all documents. During reindex the index is empty; a crash mid-reindex
   leaves permanent partial loss until a manual re-run. (Phase 2.)
3. **No recovery worker** at boot. (Addressed by Phase 1's reaper.)

## 2. Goals / Non-goals

**Goals (Phase 1):**
- Upload processing and Drive sync are **persisted, resumable jobs**: durable state,
  lease, heartbeat, bounded retry, recovery after crash/restart.
- No `completed`/`ready` status unless the unit's work actually finished.
- Deterministic resume after restart; no duplicate chunks or documents on retry.
- **Happy path latency unchanged** (fire-and-forget fast path preserved).

**Non-goals (Phase 1):**
- Non-destructive generational reindex (Phase 2).
- Cancellation and the full 7-scenario crash matrix (Phase 3 extends coverage).
- A generic cross-domain job framework — YAGNI. We extend the existing RAG entities.

## 3. Architecture decision — Approach A: entity-as-job

The existing entities already carry lifecycle status (`RAGDocument.status`,
`RAGDriveSource.sync_status`). We make them **durable jobs** by adding lease/heartbeat/
attempts columns and a recovery reaper, rather than introducing a redundant `rag_jobs`
table.

**Rationale:**
- Imitates the repo's sanctioned durability patterns (telephony return inbox + reaper,
  `scheduled_actions` `FOR UPDATE SKIP LOCKED` + atomic status transition) instead of
  inventing a new framework.
- Leaves the happy path untouched → minimal regression risk (project priority #1).
- Avoids a jobs table that would merely mirror entity status + a job↔entity mapping.

**Alternatives rejected:**
- **B — dedicated `rag_jobs` table:** more uniform and matches the audit's literal
  "jobs" wording, but adds a table + mapping and makes entity status redundant.
- **C — Redis Streams queue:** off-spec — the audit requires **PostgreSQL** persisted
  jobs; Redis is not the system of record (weaker recovery/audit).

## 4. Phase 1 design

### 4.1 States (reuse existing vocabulary — no renames)

- `RAGDocument` (upload work unit): add **`PENDING`** to `RAGDocumentStatus`
  (`PROCESSING`/`READY`/`ERROR`/`REINDEXING`) → cycle
  `PENDING → PROCESSING[lease] → READY | ERROR`.
  Maps the audit's pending/running/completed/failed.
- `RAGDriveSource` (sync job): existing `IDLE → SYNCING[lease] → COMPLETED | ERROR`.

**Mandatory pre-implementation sweep (primary regression risk).** Introducing `PENDING`
ripples to every consumer that filters/counts/renders documents by status. Before any
model change, enumerate and update ALL `RAGDocumentStatus` consumers:
- retrieval (must keep reading only `READY` chunks — `PENDING`/`PROCESSING` docs have no
  chunks yet, so retrieval is unaffected, but verify no query assumes "not-error =
  ready");
- "space ready?" / document-count / progress computations (a `PENDING` doc is not
  ready and not failed — ensure it is counted as in-progress, never as ready);
- any status-completeness assert/registry (ADR-085 boot guard style);
- the frontend status mapping (render `PENDING` as "queued", not "unknown").
This sweep is a discrete task in the implementation plan and must be done first.

### 4.2 Durability columns (migration — non-blocking, nullable/defaulted)

On **`rag_documents`** and **`rag_drive_sources`**:
- `lease_expires_at TIMESTAMPTZ NULL` — current claim expiry.
- `heartbeat_at TIMESTAMPTZ NULL` — last heartbeat during work.
- `attempts INT NOT NULL DEFAULT 0` — bounded-retry counter.
- `worker_id TEXT NULL` — lease holder (observability).
- Partial index `(status, lease_expires_at)` for the reaper scan.

**Backfill semantics:** documents already in `PROCESSING` at deploy time have
`lease_expires_at IS NULL` → the reaper treats NULL-lease `PROCESSING` as recoverable
(they are genuinely stuck from before the change).

### 4.3 Claim / lease / heartbeat protocol (atomic transitions)

- **Claim** (document): `UPDATE rag_documents SET status='processing',
  lease_expires_at=now()+ttl, heartbeat_at=now(), attempts=attempts+1, worker_id=:wid
  WHERE id=:id AND status='pending'`. `rowcount=0` ⇒ already claimed (double-launch
  safe).
- **Claim** (sync): extend the existing `try_acquire_sync_lock` UPDATE with the same
  columns (reconcile, no duplicate lock).
- **Heartbeat**: every `heartbeat_interval` seconds during work, renew
  `lease_expires_at=now()+ttl, heartbeat_at=now() WHERE id=:id AND worker_id=:wid`
  (generalizes the existing reindex heartbeat).
- **Complete**: success → `READY`/`COMPLETED`, clear lease.
- **Fail/retry**: failure → `ERROR` if `attempts >= max_attempts`, else back to
  `PENDING` (lease cleared) for a bounded retry.

**Happy path unchanged:** upload creates the document as `PENDING`, then
fire-and-forgets a claim+process (millisecond transition). Persistence is the safety
net, not the nominal path.

### 4.4 Recovery reaper (`rag_job_reaper`)

Periodic scheduler job, leader-elected, registered in `startup/schedulers.py`, interval
settings-driven, using `FOR UPDATE SKIP LOCKED`:
- Documents `status='processing' AND (lease_expires_at IS NULL OR lease_expires_at <
  now())` → stuck:
  - `attempts < max` → reset to `PENDING` (clear lease) + re-drive (fire-and-forget
    claim+process).
  - `attempts >= max` → `ERROR` with `error_message="max attempts exceeded"`
    (dead-letter, surfaced in UI).
- Orphaned `PENDING` (crash right after creation, before claim) older than
  `reaper_grace_seconds` → re-driven.
- Sources `sync_status='syncing'` with expired lease → reset to `IDLE` + re-sync if
  `attempts < max`, else `ERROR`.
- **Bounded work per tick**: the reaper processes at most `rag_job_reaper_batch_size`
  recoverable items per tick and re-drives them with a bounded concurrency
  (`rag_job_reaper_concurrency`) so a large backlog cannot saturate the scheduler
  process. Remaining items are picked up on the next tick. Log when the batch is
  capped (no silent truncation).
- **Session discipline**: each re-driven reprocess acquires its own `AsyncSession` via
  `get_db_context()` (AsyncSession is not safe for concurrent use).
- **Boot recovery**: implemented as the scheduler job's first run (gated by leader
  election — never a raw startup step that would run on every instance), scheduled to
  fire immediately after election, then periodically. Satisfies "worker de reprise au
  démarrage" deterministically on the elected leader only.

### 4.5 Idempotency + atomic per-document chunk swap

- Reprocessing a document must NOT leave a transient window with zero chunks (that is
  the space-level "destructive reindex" flaw at document granularity, and it degrades
  retrieval). Therefore: **embed first (slow, outside any transaction), then in ONE
  short transaction delete the document's old chunks + insert the new chunks + set
  `READY`.** The swap is atomic — retrieval never sees a reprocessed document with zero
  chunks, and the transaction stays short (no embedding held open). This supersedes the
  current reindex's "delete then rebuild" ordering.
- For a first-time upload there are no old chunks, so the delete is a no-op and the
  insert+`READY` is atomic.
- Re-sync re-lists Drive files and skips already-synced ones
  (`drive_file_id` + `drive_modified_time`) — no duplicate documents.
- `attempts` is reset to 0 on successful completion, so a later reprocess (recovery or
  reindex) starts with a fresh retry budget.

### 4.6 Settings (parameterizable → `.env`, never hardcoded)

Add to `core/config/rag_spaces.py` (+ `core/constants.py` defaults + `.env.example` +
`.env.prod.example`):
- `rag_job_lease_ttl_seconds`
- `rag_job_heartbeat_interval_seconds`
- `rag_job_max_attempts`
- `rag_job_reaper_interval_seconds`
- `rag_job_reaper_grace_seconds`
- `rag_job_reaper_batch_size` — max recoverable items re-driven per reaper tick.
- `rag_job_reaper_concurrency` — max concurrent re-drives within a tick.

**Invariant:** `rag_job_heartbeat_interval_seconds < rag_job_lease_ttl_seconds` (the
lease must be renewed before it expires, otherwise the reaper would requeue a live
job). Validate this at settings load / boot and document it on the fields.

Tests must read thresholds from `settings`, never hardcode them.

### 4.7 Repository methods

On the RAG repository (or a focused `rag_jobs_repository`): `claim_document`,
`heartbeat_document`, `complete_document`, `fail_or_retry_document`,
`fetch_recoverable_documents` (+ sync equivalents), all as atomic UPDATEs. Keep files
under the 600-SLOC ratchet — extract a cohesive module if needed.

### 4.8 Observability

- Metrics: `rag_jobs_recovered_total{job_type, outcome}` (outcome ∈ requeued|failed),
  gauge `rag_jobs_in_flight`.
- Structured logging (IDs/counters only — no PII; document content stays out of logs).

### 4.9 Runtime integration points (CLAUDE.md checklist)

1. Alembic migration (columns + partial indexes; single head).
2. Models already registered — new columns only.
3. Settings module + `.env.example` + `.env.prod.example` + constants.
4. Scheduler registration in `startup/schedulers.py::init_scheduler` (feature-flag
   guard, job ID from constants, `replace_existing=True`, before `leader_elector.start()`).
5. No new router — upload/sync endpoints unchanged (they now create `PENDING`).
6. `PENDING` added to `RAGDocumentStatus` + completeness asserts + frontend mapping.
7. ADR (entity-as-job durability decision) + RAG technical doc updated; `docs/INDEX.md`
   + ADR index cross-referenced.

### 4.10 Testing (Phase 1) — imitates `tests/integration/domains/telephony/test_return_inbox.py`

Integration (real PostgreSQL, disposable `lia_test` DB):
- Claim atomicity: two concurrent claims → exactly one wins (double-launch).
- Heartbeat extends the lease.
- Recovery: document stuck in `PROCESSING` with expired lease → reaper requeues →
  reprocessed to `READY`, **zero duplicate chunks** (idempotency).
- Bounded retry: `attempts` reaches `max` → `ERROR` (dead-letter), no infinite loop.
- Orphaned `PENDING` → re-driven.
- Source stuck in `SYNCING` (expired) → reset to `IDLE` + re-sync, zero duplicate
  documents.

Unit:
- Reaper decision logic (requeue vs fail); thresholds read from `settings`.

### 4.11 Crash-scenario coverage (audit's 7)

Phase 1 covers: crash-before-processing (orphaned `PENDING`), mid-document (expired
lease → requeue), double-launch (atomic claim), expired lease (requeue), partial
success (per-document idempotency + status), after-commit (`READY` stays `READY`).
**Cancellation** and the full crash matrix are Phase 3.

## 5. Phase 2 — generational, non-destructive reindex (outline)

Represent an index **generation** on `RAGSpace` (e.g. `active_generation INT`); tag
chunks with the generation they belong to. Reindex builds `generation+1` in parallel
(retrieval keeps reading the active generation), then an **atomic swap** bumps the
active pointer, and only after full success are the old generation's chunks purged. A
crash mid-reindex leaves the active generation intact — no loss. Reuses the Phase 1
durable-job substrate (a reindex is a space-level job over document work-units).

## 6. Phase 3 — exhaustive crash matrix + cancellation (outline)

Add cancellation (cooperative, via a durable cancel flag checked at unit boundaries) and
the remaining crash-injection tests (after-commit ordering, lease-steal races, partial
generational swap).

## 7. Success criteria (from the audit)

- No `completed`/`ready` status if a work unit failed.
- No loss of valid chunks.
- Deterministic resume after restart.
- Ruff / MyPy strict / targeted tests green; file-size + coverage ratchets respected.
