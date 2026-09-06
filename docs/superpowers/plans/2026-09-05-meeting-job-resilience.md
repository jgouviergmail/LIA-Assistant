# Meeting Job Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, inline (owner directive: no subagents). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A recorded meeting is never lost and its owner is never blocked: every job transition persists, the job resumes from what it already acquired, a dead worker is resolved by the reaper, and a valid model answer is never thrown away.

**Architecture:** The meeting row stays the durable job (ADR-258). Three amendments: (1) every enum literal written through a SQL expression carries the column's type, guarded by an AST test and by integration tests on real PostgreSQL; (2) the job writes a CHECKPOINT after each acquired stage (normalized audio, transcript) on the claimed row, and a claim reads the checkpoints before spending anything again; the audio of a non-READY meeting is never purged by retention; (3) a `PROCESSING` row whose lease expired is deletable, and one whose retry budget is exhausted is dead-lettered by the reaper itself. On the LLM side, the model-facing shapes accept `null` where the schema has a default, the structured-output path reads the `parsing_error` it was discarding, and a rejected tool call is retried once with its nulls defaulted, generically.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (asyncpg), Pydantic 2, pytest (unit + integration on real PostgreSQL in `lia-api-dev`), Next.js 16 / vitest.

**Spec:** the incident analysis of 2026-09-05 (meeting `3b7cbbc6`, this conversation) and `docs/architecture/ADR-258-Meeting-Recording-And-Structured-Minutes.md` (amended by Task 12).

## Global Constraints

- Never `git commit`/`push` (owner rule). Every "Commit" step below is replaced by "Run the gate".
- All runtime verification inside the Docker dev containers; unit tests may run on the host venv.
- Integration tests run in `lia-api-dev` with `TEST_DATABASE_URL` pointing at the disposable `lia_test` database (created 2026-09-05).
- File-size ratchet: no file grows past 600 logical SLOC; `structured_output.py` gets no new logic — new logic lives in a new module.
- Backend user-visible strings through i18n; frontend keys in the 6 locales with strict parity.
- Datetimes timezone-aware UTC; lease comparisons on the database clock.
- No cast, no `Any` where a type exists; MyPy strict.

---

### Task 1: Typed enum literals in `fail_or_retry` + AST guard

**Files:**
- Modify: `apps/api/src/domains/meetings/repository.py:229-257`
- Create: `apps/api/tests/unit/test_no_bare_enum_in_sql_case_guard.py`
- Test: `apps/api/tests/unit/domains/meetings/test_repository_statements.py` (new)

**Interfaces:**
- Produces: `MeetingRepository.fail_or_retry` unchanged signature; `_status_literal(status: MeetingStatus) -> BindParameter` module helper.

- [ ] Step 1: unit test compiling the `fail_or_retry` statement against the asyncpg dialect and asserting every `status` bind carries `Enum` type and renders the NAME (`FAILED`, `STOPPED`). Uses `repo.fail_or_retry` with a session double that captures the statement.
- [ ] Step 2: run → FAIL (`NullType`, value `MeetingStatus.FAILED`).
- [ ] Step 3: wrap the two `case()` results with `literal(value, Meeting.status.type)`.
- [ ] Step 4: run → PASS.
- [ ] Step 5: AST guard over `src/`: any `case(` call whose `whens` result or `else_` is an `Attribute` on a name ending in `Status|State|Kind|Type|Provider|Format|Selection|Mode|Source` fails unless wrapped in `literal(`/`cast(`/`type_coerce(`. Test the guard on a synthetic bad snippet too.

### Task 2: Reaper dead-letters an exhausted worker

**Files:**
- Modify: `apps/api/src/domains/meetings/repository.py` (`requeue_expired_leases(max_attempts)` → `tuple[int, int]`), `reapers.py`, `processing.py` (`ERROR_WORKER_LOST = "worker_lost"`)
- Test: `tests/unit/domains/meetings/test_reapers.py`, integration Task 4.

- [ ] Step 1: unit test — reaper passes `settings.meetings_job_max_attempts`, counts `requeued` and `dead_lettered` outcomes separately.
- [ ] Step 2: FAIL. Step 3: one UPDATE with a typed `case()` on attempts, `last_error_code = case(...)`. Step 4: PASS.
- [ ] Frontend key `meetings.errors.worker_lost` ×6 (Task 10).

### Task 3: Checkpoints — write after each acquired stage, read at claim

**Files:**
- Modify: `repository.py` (`heartbeat(..., values: Mapping[str, Any] | None = None)`), `processing.py` (`_normalize`, `_run`, `_transcribe_or_reuse`), `transcription.py` (`outcome_from_row(meeting) -> TranscriptionOutcome | None`)
- Test: `tests/unit/domains/meetings/test_processing_resume.py` (new), `test_transcription.py`

Behaviour:
- After normalization: checkpoint `audio_path`, `audio_duration_seconds`, `audio_gaps`.
- After transcription: checkpoint `transcript_encrypted`, `transcript_deleted_at=None`, `stt_provider/model/detected_language/diarized/audio_seconds/cost_eur`.
- At `_run`: if `meeting.audio_path` and the file exists → reuse (no ffmpeg, no segments); else if no segment on disk → `fail_permanently(code="audio_unavailable")`; else normalize.
- If `meeting.transcript_encrypted` and `transcript_deleted_at is None` → `outcome_from_row`, skip STT, do NOT increment `meeting_stt_audio_seconds_total`.
- `_completion_values` unchanged (writes the same columns again).

- [ ] Steps: one failing test per behaviour above, then the minimal code, then the whole meetings unit suite.

### Task 4: Integration tests on real PostgreSQL

**Files:**
- Create: `apps/api/tests/integration/domains/meetings/__init__.py`, `test_repository_jobs.py`

Cases: claim → fail_or_retry ×3 yields `STOPPED, STOPPED, FAILED` and the row really carries `STOPPED` (the incident); `release_unprocessed` gives the attempt back; `heartbeat` refuses a foreign worker; `heartbeat(values=)` persists a checkpoint; `complete` resets the budget; `requeue_expired_leases` requeues below the budget and dead-letters at the budget; `fetch_audio_to_purge` never returns a FAILED row; `delete_unless_leased` (Task 5) refuses a live lease and accepts an expired one; `requeue_for_retry` keeps the checkpoints.

Run: `docker exec lia-api-dev sh -c 'export TEST_DATABASE_URL=... LIA_REQUIRE_DB=1; pytest tests/integration/domains/meetings -m integration'`.

### Task 5: Never blocked — delete on an expired lease, retention never purges a failed meeting

**Files:**
- Modify: `repository.py` (`delete_unless_leased(meeting_id) -> bool`, `fetch_audio_to_purge` READY only), `service.py::delete`, `bulk.py` (shared predicate `is_deletable_now`), `schemas.py` (`attempts`, `max_attempts`, `worker_stale` on the detail), `service.to_detail`.
- Test: `test_service_guards.py`, `test_bulk.py`, `test_service_projection.py` (new for the detail fields).

- [ ] Detail exposes `attempts`, `max_attempts` (settings), `worker_stale` (PROCESSING and lease NULL or past, computed with `datetime.now(UTC)`).
- [ ] `delete`: PROCESSING with a live lease → `meeting_in_progress`; otherwise the row is deleted by the conditional statement; a rowcount of 0 after the projection step → `meeting_in_progress`.

### Task 6: `process_meeting` never raises, background failures carry their traceback

**Files:**
- Modify: `processing.py::process_meeting`, `src/infrastructure/async_utils.py::_on_task_done`
- Test: `test_processing_flow.py`, `tests/unit/infrastructure/test_async_utils_background.py` (new or existing)

- [ ] `_fail` raising → `meeting_failures_total{reason="transition_failed"}`, `logger.exception("meeting_transition_failed")`, no propagation.
- [ ] `background_task_failed` logs `exc_info=<the exception>`.

### Task 7: Model-facing shapes tolerate `null`

**Files:**
- Modify: `apps/api/src/domains/meetings/synthesis.py` (`SynthesizedSection`, `SynthesizedMinutes`)
- Test: `tests/unit/domains/meetings/test_synthesis.py` — the exact payload DeepSeek returned on 2026-09-05 validates; `None` in every list field becomes `[]`; a wrong type still fails.

### Task 8: Structured output reads `parsing_error`, defaults nulls generically

**Files:**
- Create: `apps/api/src/infrastructure/llm/payload_defaults.py` (`drop_nulls_with_defaults(schema, payload) -> tuple[dict, int]`, `validate_with_defaulted_nulls(schema, payload) -> tuple[T | None, int]`)
- Modify: `structured_output.py::_buffered_invoke` and `_rescue_structured_from_text` (minimal lines)
- Test: `tests/unit/infrastructure/llm/test_payload_defaults.py` (new), `test_structured_output_rescue.py` (new)

Rules: a `None` under a key whose field has a default (or default_factory) and whose annotation does NOT admit `None` is removed (recursively through nested models and lists of models); a `None` on an Optional field stays; a required field stays (validation still fails). The message distinguishes `tool call rejected by schema (N errors: paths)` from `no tool call`; the log `structured_output_tool_call_rejected` carries schema + paths; a successful defaulting logs `structured_output_nulls_defaulted` with the count.

### Task 9: Frontend — attempts, stale worker, delete while stale

**Files:**
- Modify: `apps/web/src/types/meetings.ts` (`attempts`, `max_attempts`, `worker_stale` on `MeetingDetail`), `MeetingDetailPanels.tsx::ProcessingPanel` (attempt counter when `attempts > 1` with the previous error, stale hint + delete button when `worker_stale`), `[id]/page.tsx` (pass `actions`), test builders.
- Test: `src/components/meetings/__tests__/MeetingDetailPanels.processing.test.tsx` (new)
- i18n ×6: `meetings.detail.attempt_of`, `meetings.detail.previous_error`, `meetings.detail.worker_stale_hint`, `meetings.errors.worker_lost`.

### Task 10: Docs, ADR amendment, memory, ratchets

- `docs/technical/MEETINGS.md` lifecycle (checkpoints, dead-letter by the reaper, delete on an expired lease, retention never purges a failed meeting).
- `docs/architecture/ADR-258-...md` — "Amendment 2026-09-05" section.
- Coverage ratchets: measure the fast unit subset in the container; raise `--cov-fail-under` (pyproject + ci.yml) only with ≥ 2 pts margin; frontend thresholds likewise.
- Gates: `task lint`, `task test:backend:unit:fast`, integration suite (Task 4), `task test:frontend`, `task test:frontend:coverage`, `task lint:docs:preview`.
