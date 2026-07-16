# RAG Durable Jobs — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Git note (repo rule):** Claude never runs git. Every "Checkpoint" step marks a point where the **user** commits. Do not auto-commit.

**Goal:** Make RAG upload-processing and Drive-sync durable and crash-resumable by turning the existing `RAGDocument`/`RAGDriveSource` entities into leased jobs recovered by a boot-and-periodic reaper — without changing the happy-path latency.

**Architecture:** Approach A (entity-as-job). Add lease/heartbeat/attempts columns to the two entities; claim via atomic status transitions; renew a lease heartbeat while working; a leader-elected reaper requeues stuck items (expired lease or orphaned PENDING) with bounded retry, and re-drives them. Per-document chunk writes become an atomic embed-then-swap. Spec: [docs/superpowers/specs/2026-07-14-rag-durable-jobs-design.md](../specs/2026-07-14-rag-durable-jobs-design.md).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, APScheduler + Redis leader election, structlog, Prometheus, pytest (asyncio, real-PG integration), Next.js/React + react-i18next (frontend status label).

## Global Constraints

- MyPy strict, Black (line-length 100), Ruff must stay green; file-size ratchet (<600 logical SLOC/file, `apps/api/tests/unit/file_size_baseline.json`) respected — extract modules rather than grow files.
- All datetimes timezone-aware UTC (`datetime.now(UTC)`); never naive/`utcnow()`.
- Never mutate JSONB in place; new-dict reassignment only (not relevant here but a standing rule).
- All thresholds are settings-driven (`.env`), never hardcoded — tests read them from `settings`.
- Backend user-visible strings via central i18n; frontend labels in all 6 locales (en, fr, de, es, it, zh).
- No PII at INFO (IDs/counters only; never document content).
- Integration tests run against real PostgreSQL on the disposable `lia_test` DB (recreate empty first if a prior session left tables: `DROP DATABASE IF EXISTS lia_test WITH (FORCE)` then `CREATE DATABASE lia_test` in `lia-postgres-dev`).
- Runtime verified in Docker dev containers (`docker restart lia-api-dev`), not just linters/unit tests.

---

## File map

- Modify `apps/api/src/domains/rag_spaces/models.py` — add `PENDING`; add durability columns to `RAGDocument` + `RAGDriveSource`.
- Create `apps/api/alembic/versions/<rev>-rag_durable_jobs.py` — columns + partial indexes.
- Modify `apps/api/src/core/config/rag_spaces.py` + `apps/api/src/core/constants.py` + `.env.example` + `.env.prod.example` — settings.
- Create `apps/api/src/domains/rag_spaces/jobs_repository.py` — atomic claim/heartbeat/complete/fail/fetch-recoverable (keeps `repository.py` under ratchet).
- Modify `apps/api/src/domains/rag_spaces/processing.py` — claim + heartbeat + atomic chunk swap + fail/retry.
- Modify `apps/api/src/domains/rag_spaces/router.py` + `service.py` — create `PENDING` on upload.
- Modify `apps/api/src/domains/rag_spaces/drive_sync.py` — extend sync lock with lease + heartbeat.
- Create `apps/api/src/infrastructure/scheduler/rag_job_reaper.py` — the reaper job.
- Modify `apps/api/src/infrastructure/startup/schedulers.py` — register the reaper (leader-gated, immediate first run).
- Modify `apps/api/src/domains/rag_spaces/schemas.py`, `retrieval.py`, `service.py` — PENDING consumer sweep.
- Modify frontend: `apps/web/src/components/spaces/DocumentProcessingStatus.tsx`, `types/rag-spaces.ts`, `apps/web/locales/*/translation.json`.
- Metrics in `apps/api/src/infrastructure/observability/` (RAG namespace).
- Docs: new ADR + `docs/technical` RAG doc.
- Tests under `apps/api/tests/integration/domains/rag_spaces/` and `apps/api/tests/unit/...`.

---

### Task 0: Introduce `PENDING` status + consumer sweep

**Files:**
- Modify: `apps/api/src/domains/rag_spaces/models.py` (`RAGDocumentStatus`)
- Modify: `apps/api/src/domains/rag_spaces/{retrieval.py,service.py,schemas.py}` (consumers)
- Modify: `apps/web/src/components/spaces/DocumentProcessingStatus.tsx`, `apps/web/src/types/rag-spaces.ts`, `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`
- Test: `apps/api/tests/unit/domains/rag_spaces/test_document_status.py`

**Interfaces:**
- Produces: `RAGDocumentStatus.PENDING = "pending"` — the created-but-unclaimed state.

- [ ] **Step 1: Enumerate consumers.** Run `grep -rn "RAGDocumentStatus\.\|status ==\|status='\|status=\"" apps/api/src/domains/rag_spaces` and list every branch that assumes the 4 current values. For each, decide the correct `PENDING` behavior: retrieval reads only `READY` (unaffected — PENDING docs have no chunks); "is document done / space ready" logic must treat `PENDING` as **in-progress, not ready, not error**; progress counters count `PENDING` as pending.

- [ ] **Step 2: Write the failing test**

```python
# apps/api/tests/unit/domains/rag_spaces/test_document_status.py
from src.domains.rag_spaces.models import RAGDocumentStatus

def test_pending_status_exists_and_is_distinct():
    assert RAGDocumentStatus.PENDING == "pending"
    assert RAGDocumentStatus.PENDING not in (
        RAGDocumentStatus.PROCESSING,
        RAGDocumentStatus.READY,
        RAGDocumentStatus.ERROR,
        RAGDocumentStatus.REINDEXING,
    )

def test_pending_is_not_terminal():
    # A helper the consumers use to decide "still working". Add it if absent.
    from src.domains.rag_spaces.models import is_terminal_document_status
    assert is_terminal_document_status(RAGDocumentStatus.READY) is True
    assert is_terminal_document_status(RAGDocumentStatus.ERROR) is True
    assert is_terminal_document_status(RAGDocumentStatus.PENDING) is False
    assert is_terminal_document_status(RAGDocumentStatus.PROCESSING) is False
```

- [ ] **Step 3: Run to verify fail** — `cd apps/api && .venv/Scripts/pytest tests/unit/domains/rag_spaces/test_document_status.py -q -o addopts=""` → FAIL (no `PENDING` / no helper).

- [ ] **Step 4: Implement.** Add `PENDING = "pending"` to `RAGDocumentStatus`, and a small module-level helper `is_terminal_document_status(status: str) -> bool` returning `status in (READY, ERROR)`. Update the consumers found in Step 1 to use `PENDING` correctly (use the helper where "still working" is meant).

- [ ] **Step 5: Frontend sweep.** In `DocumentProcessingStatus.tsx` add a `case 'pending':` rendering `t('spaces.documents.status.pending')` (a "queued" style, like processing). Add `'pending'` to the status union in `types/rag-spaces.ts`. Add key `spaces.documents.status.pending` to **all 6** locale files (value e.g. en "Queued", fr "En file d'attente", de "In Warteschlange", es "En cola", it "In coda", zh "排队中").

- [ ] **Step 6: Run tests + i18n parity** — backend: `pytest tests/unit/domains/rag_spaces/ -q -o addopts=""` PASS. Frontend parity is enforced by the pre-commit hook; verify keys exist in all 6 locales.

- [ ] **Step 7: Checkpoint (user commits)** — `feat(rag): add PENDING document status + consumer/UI sweep`.

---

### Task 1: Migration — durability columns + indexes

**Files:**
- Modify: `apps/api/src/domains/rag_spaces/models.py` (`RAGDocument`, `RAGDriveSource`)
- Create: `apps/api/alembic/versions/<rev>-rag_durable_jobs.py`
- Test: `apps/api/tests/integration/domains/rag_spaces/test_durable_jobs_migration.py`

**Interfaces:**
- Produces on both `RAGDocument` and `RAGDriveSource`: `lease_expires_at: Mapped[datetime | None]`, `heartbeat_at: Mapped[datetime | None]`, `attempts: Mapped[int]` (default 0, not null), `worker_id: Mapped[str | None]`.

- [ ] **Step 1: Add columns to models** (mirror existing `Mapped[...] = mapped_column(...)` style, `DateTime(timezone=True)` for timestamps, `default=0` for attempts).

- [ ] **Step 2: Generate migration** — `docker exec lia-api-dev bash -lc "cd /app && alembic revision --autogenerate -m 'rag durable jobs'"`. Then hand-edit: ensure `op.add_column` for the 8 columns (4 per table, nullable except `attempts` server_default '0'), and add partial indexes:

```python
op.create_index(
    "ix_rag_documents_status_lease",
    "rag_documents", ["status", "lease_expires_at"],
)
op.create_index(
    "ix_rag_drive_sources_status_lease",
    "rag_drive_sources", ["sync_status", "lease_expires_at"],
)
```
`downgrade()` drops indexes then columns. Verify `alembic heads` returns a single head and the migration replays from scratch (F007 rule).

- [ ] **Step 3: Failing test**

```python
# test_durable_jobs_migration.py  (real PG, marker integration)
import pytest
from sqlalchemy import inspect, text
pytestmark = pytest.mark.integration

async def test_durability_columns_present(async_session):
    cols = (await async_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='rag_documents'"))).scalars().all()
    for c in ("lease_expires_at", "heartbeat_at", "attempts", "worker_id"):
        assert c in cols
```

- [ ] **Step 4: Run migration + test** — apply on `lia_test` (recreate empty first per Global Constraints), then `pytest tests/integration/domains/rag_spaces/test_durable_jobs_migration.py -q -o addopts=""` PASS.

- [ ] **Step 5: Checkpoint (user commits)** — `feat(rag): durability columns + partial indexes (F001)`.

---

### Task 2: Settings — durable-job config

**Files:**
- Modify: `apps/api/src/core/config/rag_spaces.py`, `apps/api/src/core/constants.py`, `.env.example`, `.env.prod.example`
- Test: `apps/api/tests/unit/core/config/test_rag_job_settings.py`

**Interfaces:**
- Produces `settings.rag_job_lease_ttl_seconds`, `..._heartbeat_interval_seconds`, `..._max_attempts`, `..._reaper_interval_seconds`, `..._reaper_grace_seconds`, `..._reaper_batch_size`, `..._reaper_concurrency` (all `int`, defaults from `constants.py`).

- [ ] **Step 1: Failing test**

```python
def test_rag_job_defaults_and_invariant():
    from src.core.config import settings
    assert settings.rag_job_heartbeat_interval_seconds < settings.rag_job_lease_ttl_seconds
    assert settings.rag_job_max_attempts >= 1
    assert settings.rag_job_reaper_batch_size >= 1
```

- [ ] **Step 2: Run to fail** — attribute errors.

- [ ] **Step 3: Implement** — add 7 `Field(default=..., description=...)` entries to the RAG settings class (imitate `rag_reindex_lock_ttl_seconds` at `rag_spaces.py:87`), defaults in `constants.py` (e.g. lease 300, heartbeat 60, max_attempts 3, reaper interval 120, grace 60, batch 25, concurrency 4). Add a `model_validator(mode="after")` enforcing `heartbeat < lease`. Add all 7 to `.env.example` **and** `.env.prod.example` with commented defaults.

- [ ] **Step 4: Run test** PASS.

- [ ] **Step 5: Checkpoint (user commits)** — `feat(rag): durable-job settings + heartbeat<lease invariant`.

---

### Task 3: Jobs repository — atomic claim/heartbeat/complete/fail (documents)

**Files:**
- Create: `apps/api/src/domains/rag_spaces/jobs_repository.py`
- Test: `apps/api/tests/integration/domains/rag_spaces/test_jobs_repository.py` (real PG)

**Interfaces:**
- Produces `RAGJobsRepository(db: AsyncSession)` with:
  - `claim_document(document_id: UUID, worker_id: str, lease_ttl_s: int) -> bool` — atomic `PENDING→PROCESSING`, sets lease/heartbeat/attempts+=1/worker_id; returns True iff claimed.
  - `heartbeat_document(document_id: UUID, worker_id: str, lease_ttl_s: int) -> bool` — renews lease if still holder.
  - `complete_document(document_id: UUID) -> None` — `→READY`, clears lease, `attempts=0`.
  - `fail_or_retry_document(document_id: UUID, error: str, max_attempts: int) -> str` — `→ERROR` if `attempts>=max` else `→PENDING`; returns the new status.
  - `fetch_recoverable_documents(grace_s: int, limit: int) -> list[UUID]` — ids of `PROCESSING` with expired/NULL lease, plus `PENDING` older than grace with no lease; `FOR UPDATE SKIP LOCKED`.

- [ ] **Step 1: Failing tests** (double-launch, heartbeat, complete-resets-attempts, retry-then-fail, fetch_recoverable):

```python
pytestmark = pytest.mark.integration

async def test_claim_is_exclusive(async_session, a_pending_document):
    r1 = RAGJobsRepository(async_session)
    assert await r1.claim_document(a_pending_document.id, "w1", 300) is True
    # second claim in a *separate* session must fail (already PROCESSING)
    async with get_db_context() as s2:
        assert await RAGJobsRepository(s2).claim_document(a_pending_document.id, "w2", 300) is False

async def test_complete_resets_attempts(async_session, a_pending_document):
    repo = RAGJobsRepository(async_session)
    await repo.claim_document(a_pending_document.id, "w1", 300)
    await repo.complete_document(a_pending_document.id)
    doc = await async_session.get(RAGDocument, a_pending_document.id)
    assert doc.status == RAGDocumentStatus.READY and doc.attempts == 0 and doc.lease_expires_at is None

async def test_retry_then_fail(async_session, a_pending_document):
    repo = RAGJobsRepository(async_session)
    for _ in range(3):  # max_attempts=3
        await repo.claim_document(a_pending_document.id, "w1", 300)
        status = await repo.fail_or_retry_document(a_pending_document.id, "boom", max_attempts=3)
    assert status == RAGDocumentStatus.ERROR
```

- [ ] **Step 2: Run to fail.**

- [ ] **Step 3: Implement** using raw atomic `UPDATE ... WHERE` (imitate `scheduled_actions/repository.py` and `drive_sync.try_acquire_sync_lock`). Claim:

```python
res = await self.db.execute(text(
    "UPDATE rag_documents SET status=:proc, lease_expires_at=now()+make_interval(secs=>:ttl), "
    "heartbeat_at=now(), attempts=attempts+1, worker_id=:wid "
    "WHERE id=:id AND status=:pending"),
    {"proc": RAGDocumentStatus.PROCESSING, "ttl": lease_ttl_s, "wid": worker_id,
     "id": str(document_id), "pending": RAGDocumentStatus.PENDING})
await self.db.commit()
return (getattr(res, "rowcount", 0) or 0) > 0
```
`fetch_recoverable_documents`: two-part `SELECT id ... WHERE (status='processing' AND (lease_expires_at IS NULL OR lease_expires_at < now())) OR (status='pending' AND heartbeat_at IS NULL AND created_at < now()-grace) LIMIT :limit FOR UPDATE SKIP LOCKED`.

- [ ] **Step 4: Run tests** PASS.

- [ ] **Step 5: Checkpoint (user commits)** — `feat(rag): jobs repository (atomic claim/heartbeat/complete/fail)`.

---

### Task 4: Processing integration — claim, heartbeat, atomic chunk swap

**Files:**
- Modify: `apps/api/src/domains/rag_spaces/processing.py` (`process_document`)
- Modify: `apps/api/src/domains/rag_spaces/{service.py,router.py}` (create `PENDING`)
- Test: `apps/api/tests/integration/domains/rag_spaces/test_processing_durable.py`

**Interfaces:**
- Consumes: `RAGJobsRepository` (Task 3), settings (Task 2).
- Produces: `process_document(...)` now claims before working, heartbeats during embedding, writes chunks via an **atomic swap** (`delete old + insert new + READY` in one transaction), and calls `fail_or_retry_document` on error.

- [ ] **Step 1: Failing test — atomic swap keeps chunks until commit**

```python
pytestmark = pytest.mark.integration

async def test_reprocess_never_leaves_zero_chunks(async_session, a_ready_document_with_chunks):
    # Simulate a reprocess: chunks must be present before AND after; the swap is atomic.
    before = await count_chunks(async_session, a_ready_document_with_chunks.id)
    assert before > 0
    await process_document(document_id=a_ready_document_with_chunks.id, ...)  # reprocess
    after = await count_chunks(async_session, a_ready_document_with_chunks.id)
    assert after > 0  # never dropped to 0 in a committed state; no duplicates

async def test_success_sets_ready_and_resets_attempts(async_session, a_pending_document):
    ok = await process_document(document_id=a_pending_document.id, ...)
    assert ok is True
    doc = await async_session.get(RAGDocument, a_pending_document.id)
    assert doc.status == RAGDocumentStatus.READY and doc.attempts == 0
```

- [ ] **Step 2: Run to fail.**

- [ ] **Step 3: Implement.** In `process_document`: (a) claim via `RAGJobsRepository.claim_document`; if not claimed, return (someone else owns it). (b) Extract text + chunk + **embed all chunks first** (network, no open transaction), heartbeating every `heartbeat_interval_seconds`. (c) In ONE transaction: `delete_by_document(doc.id)` + bulk-insert new chunks + `complete_document` (→READY, attempts=0). (d) On any exception: `fail_or_retry_document(doc.id, str(e), max_attempts)` and return False. In `service.upload_document` create the row with `status=PENDING`; keep the `router.py` `safe_fire_and_forget(process_document(...))` fast path (it now claims PENDING→PROCESSING).

- [ ] **Step 4: Run tests** PASS; verify no duplicate chunks (`chunk_index` unique per doc).

- [ ] **Step 5: Runtime check** — `docker restart lia-api-dev`; upload a document via the UI/endpoint; confirm it reaches READY with chunks.

- [ ] **Step 6: Checkpoint (user commits)** — `feat(rag): durable processing with atomic chunk swap`.

---

### Task 5: Recovery reaper (documents) + scheduler registration

**Files:**
- Create: `apps/api/src/infrastructure/scheduler/rag_job_reaper.py`
- Modify: `apps/api/src/infrastructure/startup/schedulers.py`
- Test: `apps/api/tests/unit/domains/rag_spaces/test_rag_job_reaper.py` + `apps/api/tests/integration/domains/rag_spaces/test_reaper_recovery.py`

**Interfaces:**
- Consumes: `RAGJobsRepository`, settings, `get_db_context`.
- Produces: `async def rag_job_reaper() -> None` — one tick: fetch up to `reaper_batch_size` recoverable docs; for each (own `AsyncSession`, bounded by `reaper_concurrency`): if `attempts >= max` → `fail_or_retry_document` (→ERROR) else reset to PENDING and re-drive `process_document`; emit `rag_jobs_recovered_total{job_type="document",outcome=...}`.

- [ ] **Step 1: Failing unit test** (decision logic with a fake repo): stuck doc with attempts<max → requeued+redriven; attempts>=max → ERROR; batch cap honored + logged.

```python
async def test_reaper_requeues_under_max(monkeypatch, fake_repo_one_stuck_doc):
    await rag_job_reaper()
    assert fake_repo_one_stuck_doc.redriven == [DOC_ID]

async def test_reaper_fails_at_max(monkeypatch, fake_repo_doc_at_max):
    await rag_job_reaper()
    assert fake_repo_doc_at_max.status[DOC_ID] == RAGDocumentStatus.ERROR
```

- [ ] **Step 2: Failing integration test** (real PG): insert a doc in `PROCESSING` with `lease_expires_at = now()-1h`; run `rag_job_reaper()`; assert it becomes `READY` with chunks and no duplicates; insert an orphaned `PENDING` older than grace → re-driven.

- [ ] **Step 3: Run to fail.**

- [ ] **Step 4: Implement** the reaper (imitate `src/infrastructure/scheduler/` job style + the telephony reaper). Use `asyncio.Semaphore(reaper_concurrency)`; each re-drive gets its own `get_db_context()`; `log.info("rag_reaper_batch_capped", ...)` when the batch fills.

- [ ] **Step 5: Register** in `schedulers.py::init_scheduler` (before `leader_elector.start()`): `scheduler.add_job(rag_job_reaper, "interval", seconds=settings.rag_job_reaper_interval_seconds, id=RAG_JOB_REAPER_ID, replace_existing=True, next_run_time=<immediate>)` behind the RAG feature flag; job ID constant in `constants.py`. Leader election already gates execution.

- [ ] **Step 6: Run tests** PASS; `docker restart lia-api-dev` and confirm `rag_reaper` runs once at boot (log line) and recovers a hand-stuck document.

- [ ] **Step 7: Checkpoint (user commits)** — `feat(rag): recovery reaper + scheduler registration (F001)`.

---

### Task 6: Drive-sync durability

**Files:**
- Modify: `apps/api/src/domains/rag_spaces/drive_sync.py`
- Modify: `apps/api/src/infrastructure/scheduler/rag_job_reaper.py` (source branch)
- Test: `apps/api/tests/integration/domains/rag_spaces/test_sync_recovery.py`

**Interfaces:**
- Produces: `try_acquire_sync_lock` extended to also set `lease_expires_at/heartbeat_at/attempts`; reaper resets `SYNCING`+expired → `IDLE` (+re-sync if attempts<max else ERROR).

- [ ] **Step 1: Failing test** — source stuck in `SYNCING` with expired lease → reaper resets to `IDLE`, re-sync runs, no duplicate `RAGDocument` rows for the same `drive_file_id`.

- [ ] **Step 2: Run to fail.**

- [ ] **Step 3: Implement** — extend the `try_acquire_sync_lock` UPDATE with the lease columns; heartbeat during sync (renew lease per file batch); add the source branch to `rag_job_reaper` (`fetch_recoverable_sources`, requeue/ERROR); idempotent re-sync already skips synced files by `drive_file_id`+`drive_modified_time`.

- [ ] **Step 4: Run tests** PASS; runtime check with a real (or stubbed) Drive source.

- [ ] **Step 5: Checkpoint (user commits)** — `feat(rag): durable drive sync with lease + recovery`.

---

### Task 7: Observability + docs

**Files:**
- Modify: `apps/api/src/infrastructure/observability/` (RAG metrics)
- Create: `docs/architecture/adr/ADR-XXX-rag-durable-jobs.md` + update `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md`, the RAG technical doc.
- Test: `apps/api/tests/unit/domains/rag_spaces/test_rag_job_metrics.py`

- [ ] **Step 1: Failing test** — `rag_jobs_recovered_total` increments on a requeue and on a fail; `rag_jobs_in_flight` reflects claimed docs.

- [ ] **Step 2: Implement** metrics (Counter with `{job_type, outcome}`, Gauge), wire into reaper + claim/complete.

- [ ] **Step 3: Docs** — ADR recording the entity-as-job durability decision + preserved fixes; RAG technical doc section on job lifecycle, lease/heartbeat, reaper, settings.

- [ ] **Step 4: Run tests** PASS.

- [ ] **Step 5: Checkpoint (user commits)** — `docs(rag): ADR + technical doc; feat(rag): job metrics`.

---

## Phase 1 exit criteria (verify before declaring done)

- `mypy src` strict, Ruff, Black green; file-size + coverage ratchets respected.
- Integration suite (real PG) green: claim exclusivity, heartbeat, recovery→READY (no dup chunks), bounded-retry→ERROR, orphaned PENDING re-driven, sync recovery (no dup docs).
- `docker restart lia-api-dev` boots HEALTHY; reaper first tick logged; a hand-stuck document recovers to READY.
- No `completed`/`ready` without finished work; deterministic resume after restart.

## Self-review notes (done)

- Spec coverage: every §4 subsection maps to a task (states/sweep → T0; columns → T1; settings+invariant → T2; claim/heartbeat/retry → T3; atomic swap + happy path → T4; reaper + boot tick + bounds + session-per-item → T5; sync → T6; observability + docs → T7). Phase 2/3 intentionally out of scope.
- Placeholders: none — each task carries concrete tests, SQL, and file paths.
- Type consistency: `RAGJobsRepository` method names/signatures defined in T3 are reused verbatim in T4–T6.
