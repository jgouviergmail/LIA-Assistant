# ADR-129: RAG Durable Jobs — crash-resumable upload & Drive sync

**Status**: ✅ IMPLEMENTED (Phase 1, 2026-07-14 · V7 residuals closed same day, see follow-up)
**Deciders**: JGO
**Technical Story**: Audit F001 — "Workflows RAG non durables" (MAJEUR · DONNÉES/FIABILITÉ).
**Related Documentation**: `docs/architecture/ADR-055-RAG-Spaces-Architecture.md`,
`docs/architecture/ADR-056-RAG-Drive-Sync.md`, `docs/architecture/ADR-127*` (telephony
durability, the pattern imitated), `docs/superpowers/specs/2026-07-14-rag-durable-jobs-design.md`.

---

## Context and Problem Statement

RAG ingestion (upload processing, Google Drive sync, reindex) ran as in-process
`safe_fire_and_forget` asyncio tasks. A process crash lost the task with no persisted
state to resume: a document was left stuck in `PROCESSING`, a source in `SYNCING`, and
nothing recovered them. Reindex additionally deleted all chunks up front
(`DELETE FROM rag_chunks`) before rebuilding, so a crash mid-reindex caused permanent
partial loss. There was no recovery worker.

The audit required upload / Drive sync / reindex to be modelled as **persisted,
idempotent, resumable PostgreSQL jobs** with `pending/running/failed/completed` states,
lease, heartbeat and bounded retry; a **recovery worker at startup**; a **non-destructive
generational reindex**; and real crash tests. Exit criteria: no `completed` status if a
unit failed, no loss of valid chunks, deterministic resume after restart.

## Decision

**Approach A — entity-as-job.** Rather than a redundant `rag_jobs` table, the existing
entities become leased jobs (imitates the sanctioned telephony/`scheduled_actions`
durability patterns; leaves the happy path untouched → minimal regression risk):

- `RAGDocument` (upload/processing work unit) and `RAGDriveSource` (sync job) gain
  `lease_expires_at`, `heartbeat_at`, `attempts`, `worker_id` columns + a
  `(status, lease_expires_at)` reaper-scan index. Documents gain a **`PENDING`** status
  (`PENDING → PROCESSING[lease] → READY | ERROR`).
- **Atomic claim** (`UPDATE ... WHERE status = 'pending'`) — only one worker flips a row
  out of PENDING (double-launch safe). The Drive `try_acquire_sync_lock` was extended
  with the same lease columns.
- **Heartbeat** renews the lease before each slow embedding batch / file download
  (invariant `heartbeat_interval < lease_ttl`, enforced at settings load).
- **Atomic chunk swap**: reprocessing embeds first (outside any transaction), then
  deletes old chunks + inserts new + sets `READY` in ONE transaction — retrieval never
  sees a reprocessed document with zero chunks (supersedes reindex's delete-then-rebuild).
- **Bounded retry**: transient failures return the row to `PENDING`/`SYNCING`;
  `ERROR` (dead-letter) once `attempts` reach `rag_job_max_attempts`.
- **Recovery reaper** (`rag_job_reaper`, `domains/rag_spaces/reapers.py`): a leader-elected
  scheduler job (`max_instances=1`) with an **immediate first run at boot**, then periodic.
  It requeues stuck `PROCESSING`/expired-lease documents + orphaned `PENDING`, and stuck
  `SYNCING` sources (re-leased, kept SYNCING so a re-crash stays recoverable), re-driving
  each with bounded batch size + concurrency. Emits `rag_jobs_recovered_total{job_type,outcome}`.

All thresholds are settings-driven (`RAG_JOB_*` in `.env`). No `Any`/`cast`/blanket ignore.

**Scope.** Phase 1 (this ADR): durable upload + Drive sync + recovery reaper. Phase 2:
generational, non-destructive reindex (a `generation` pointer on `RAGSpace`, build
`generation+1` in parallel, atomic swap, purge old only after full success). Phase 3:
cancellation + the full crash-injection matrix.

## Consequences

**Positive**: crash-resumable ingestion; no lost chunks; deterministic resume; happy-path
latency unchanged; the `(module,code)` surface and file-size ratchets respected;
recovery is observable (`rag_jobs_recovered_total`).

**Negative / residual**: reindex is now durable and non-destructive for same-dimension
model changes (see V7 follow-up below); only an embedding-**dimension** change remains
destructive-but-resumable (pgvector single-column constraint). A crash in the
microsecond between the source reclaim and its re-lease is avoided by keeping the
source SYNCING throughout; `worker_id` is per-process (observability only, not fenced).

**Testing**: real-PostgreSQL integration tests cover claim exclusivity, heartbeat,
recovery→READY (no duplicate chunks), bounded-retry→ERROR, orphaned PENDING, and stuck
sync recovery.

## Follow-up — audit V7 residuals closed (2026-07-14)

The blind counter-audit (V7) proved two residual holes in Phase 1; both are closed:

- **Drive/reaper interleaving race.** Drive sync created documents directly
  `PROCESSING` **without a lease** — indistinguishable from a crashed job, so the reaper
  could requeue a document the live sync still owned (double owner, duplicated chunks).
  Drive documents are now born `PENDING` and flow through the same atomic claim as
  uploads, and `fetch_recoverable_documents` **excludes PENDING documents whose Drive
  source holds a live SYNCING lease** (a live sync's backlog is a live job; a crash
  expires the source lease and everything becomes recoverable within one TTL). Proven by
  real-PG interleaving tests (mid-sync scan, concurrent claim → single owner, crash →
  recoverable, finished-source documents not shielded).
- **Reindex durability (Phase 2, rescoped).** `start_reindexation` now **durably requeues
  every target document READY/ERROR → PENDING in one committed UPDATE before any
  processing** — the document statuses ARE the persistent job state; after any crash the
  regular reaper resumes the remainder through the same claim pipeline (no
  reindex-specific recovery machinery, Redis demoted to single-flight flag + progress
  cache). The destructive pre-delete/`REINDEXING` transition is gone: the atomic
  per-document chunk swap keeps **old chunks served until each document's new embedding
  commits** (service continuity during reindex). Legacy `REINDEXING` rows from pre-durable
  crashes are reaper-recoverable. The orphan-PENDING predicate moved to
  `COALESCE(heartbeat_at, created_at)` — also fixing a latent hole where a
  claimed-then-requeued document (heartbeat stamped) could never be re-recovered.
  **Deliberate residual boundary**: an embedding-**dimension** change still drops all
  chunks up front — a pgvector column has one fixed dimensionality, so side-by-side
  generations require a parallel column/table + retrieval switch (the remaining Phase 2
  item). That path is destructive but fully resumable (chunks regenerable, documents
  already durably PENDING when the deletion happens).
- **Drive telemetry exactness (audit F053).** `synced` (log), the
  `rag_drive_sync_files_total{result="synced"}` series and the persisted
  `synced_file_count` now all move **after the embedding oracle** (a downloaded file is
  not a synced file); failures are split `failed_download`/`failed_embedding`, each
  counted exactly once. Pinned by structlog+Prometheus-delta tests (2 downloaded / 1 ok /
  1 failed, gather-exception, zero-document).

## Follow-up — audit V8: the inter-commit crash window is closed (2026-07-15)

The V8 blind counter-audit demonstrated (by transactional inspection) a residual
failure window the V7 fix had left open: on a dimension change, the destructive
reset (`DELETE FROM rag_chunks` + column `ALTER` + index rebuild) was committed
in ONE transaction and the durable `READY/ERROR → PENDING` requeue in a SECOND
one. A crash between the two commits left documents `READY` **with zero
chunks** — invisible to the reaper (which only scans PROCESSING/REINDEXING/
PENDING), i.e. unrecoverable loss until a manual re-run.

Closed TDD-first: a real-PostgreSQL crash-injection test
(`test_reindex_transactional.py`) reproduced the unrecoverable state RED on the
pre-fix code, then the setup was made atomic — `_persist_reindex_intent` runs
the dimension-change DDL (PostgreSQL DDL is transactional) **and** the requeue
in one transaction with ONE commit; `_alter_vector_dimensions_if_needed` and
`requeue_documents_for_reindex` no longer commit (caller-managed transaction).
Crash before the commit → full rollback, the old index stays intact and
servable. Crash after → chunks are gone but every target document is durably
PENDING, so the drain loop / reaper rebuild through the standard claim
pipeline. Pinned by three PG tests (crash-between-steps → nothing lost,
nominal → both effects land together + reaper-visible, requeue failure → DDL
rolled back) and a unit ordering test (requeue → commit → launch).

**Remaining, deliberate residual** (unchanged from the V7 boundary): during a
dimension-change rebuild the vector index is empty until documents are
re-embedded — global search availability is reduced for the duration. Removing
that window needs a side-by-side generation (parallel column/table + the
query-embedding model pinned to the OLD generation until an atomic switch) —
the remaining Phase 2 item, deliberately out of scope here. The failure/loss
component of F001 is closed; the availability component stays documented.
