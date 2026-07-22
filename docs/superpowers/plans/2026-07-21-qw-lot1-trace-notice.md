# Lot 1 (QW-11) — Persisted Execution Trace + Connector-Error Notice at Resolution

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline — user rule:
> no subagents). Checkbox syntax tracks progress. Companion spec:
> `docs/superpowers/specs/2026-07-21-quick-wins-ux-program.md` (Lot 1).

**Goal:** (A) The ⚙ execution trace survives page reload by persisting to `message_metadata` at
archive (ADR-133 V2); (B) a connector in `ERROR` status surfaces the amber "Reconnect" banner on
subsequent runs, at provider resolution time (ADR-134 V2).

**Architecture:** (A) mirrors the ADR-137 widget-persistence pattern — a new
`services/streaming/trace_capture.py` module accumulates `{emoji, i18n_key, category}` per
`execution_step` SSE chunk at the streaming chokepoint, reset on `router_decision`; a
`with_persisted_trace()` helper merges `{steps, duration_ms}` into `assistant_metadata` at the
archive site; frontend hydrates via a pure `executionTraceFromMetadata()` resolving labels from
i18n keys. (B) enriches `ConnectorNotEnabledError` with `error_connector_type` at raise time
(async context, Redis-cached connector list already fetched); the sync
`classify_connector_exception` reads the attribute → `reconnect` notice through the 3 existing
ADR-134 emission points, unchanged.

**Tech stack:** FastAPI/LangGraph streaming, pytest, React/TS, vitest.

## Global constraints
- Ratchet caps: `streaming/service.py` 1335 · `agents/api/service.py` 1052 → wiring lines only;
  all logic in new modules. `runtime_helpers.py` (cap 674) NOT touched beyond what exists.
- PII guard: persist i18n KEYS only; never `detail`, never reasoning. No reasoning block on
  reloaded traces (ADR-133).
- JSONB: `with_persisted_trace` returns a NEW dict (never in-place).
- Settings: `execution_trace_persist_max_steps` (default constant 100 = frontend
  `MAX_TRACE_STEPS`) + `.env.example` + `.env.prod.example`.
- `FIELD_EXECUTION_TRACE = "execution_trace"` in `core/field_names.py`.
- REVOKED status excluded from the notice (arbitration #4). Typed exceptions only.
- i18n: no new UI strings (reuses `execution.steps.*` and `chat.connector_notice.*`).

---

## Task 1: backend `trace_capture.py` (TDD)
**Files:** Create `apps/api/src/domains/agents/services/streaming/trace_capture.py`;
Create `apps/api/tests/unit/domains/agents/services/streaming/test_trace_capture.py`;
Modify `core/field_names.py` (FIELD_EXECUTION_TRACE), `core/constants.py`
(EXECUTION_TRACE_PERSIST_MAX_STEPS_DEFAULT = 100), `core/config/agents.py`
(`execution_trace_persist_max_steps`, ge=10 le=1000), `.env.example`, `.env.prod.example`.

**Interfaces produced:**
- `class TraceCapture:` `__init__(self, max_steps: int)`, `observe(self, chunk_type: str,
  metadata: dict[str, Any] | None) -> None`, `snapshot(self) -> list[dict[str, str]]`.
- `def with_persisted_trace(message_metadata: dict, steps: list, *, duration_ms: int | None,
  run_id: str) -> dict` — same-object passthrough when `steps` empty, else new dict with
  `{FIELD_EXECUTION_TRACE: {"steps": steps, "duration_ms": duration_ms}}`.

**Behavior (locked by tests):**
- `observe("router_decision", …)` resets and seeds `{emoji:"🧭", i18n_key:"router_decision",
  category:"system"}` (mirrors frontend seed at `handlers.ts:356-362`).
- `observe("execution_step", md)` appends `{emoji, i18n_key, category}` iff `md.i18n_key` truthy
  and `md.step_type not in ("reasoning", "tool_error")`; emoji defaults `⚙️`; category validated
  against `{system, agent, tool, context}` else `system` (mirrors `buildTraceStep`).
- Steps without `i18n_key` (e.g. compaction custom events) are skipped — a persisted step must be
  translatable at rehydration without PII (`detail` is never persisted).
- Cap keeps the TAIL. Other chunk types are no-ops.

## Task 2: streaming + archive wiring
**Files:** Modify `services/streaming/service.py` (init: `self.trace_capture = TraceCapture(
max_steps=settings.execution_trace_persist_max_steps)` next to `persistable_widgets`; one
`self.trace_capture.observe(sse_chunk.type, sse_chunk.metadata)` per emit branch: values
router_decision, updates, custom); Modify `agents/api/service.py` regular-response archive branch,
next to `with_persisted_widgets` (line ~1280):
```python
assistant_metadata = with_persisted_trace(
    assistant_metadata,
    streaming_service.trace_capture.snapshot(),
    duration_ms=int(duration * 1000),
    run_id=run_id,
)
```
NOT applied to the HITL-question archive branch (ADR-133: no trace on HITL cards).
**Test:** `tests/unit/domains/agents/services/streaming/test_trace_capture.py` covers the module;
scope test mirrors `test_persistable_widgets_scope.py` if instance-wiring is testable cheaply.

## Task 3: frontend hydration (TDD)
**Files:** Create `apps/web/src/lib/execution-trace-hydration.ts`
(`executionTraceFromMetadata(metadata: Record<string, unknown> | undefined, t): ExecutionTrace |
undefined` — parses `metadata.execution_trace`, resolves `label = t('execution.steps.'+key,
{defaultValue:''})`, drops unresolvable steps, category default `system`, `reasoning: ''`,
`durationMs` from `duration_ms`, `undefined` when no resolvable step); Create
`apps/web/src/lib/__tests__/execution-trace-hydration.test.ts`; Modify
`hooks/useConversation.ts` (`useTranslation()` + one `executionTrace:` line in `toUiMessage`).
**Contract note:** `ExecutionTrace`/`ExecutionTraceStep` types unchanged (label resolved at
hydration — live and hydrated traces share one render path, `ExecutionTraceDisclosure` untouched).

## Task 4: connector notice at resolution (TDD)
**Files:** Modify `agents/tools/exceptions.py` (`ConnectorNotEnabledError` gains optional
`functional_category`, `error_connector_type` kwargs — backward compatible); Modify
`connectors/provider_resolver.py`: pure helper
`find_category_connector_in_error(connectors, functional_category) -> str | None` (ERROR only,
REVOKED excluded, legacy aliases resolved) + async factory
`build_connector_not_enabled_error(functional_category, user_id, connector_service) ->
ConnectorNotEnabledError` (fetches cached list, enriches); Modify the "resolved None for
category" raise sites to use the factory — audit each: `provider_resolver.py:124`,
`agents/tools/base.py:~265`, `tasks_tools.py:~1502`, `google_contacts_tools.py:~1964`,
`telephony_tools.py:~125`, `labels_tools.py:~958`, `drive_tools.py:~1229` (enrich only the
no-active-connector raises; credentials-missing raises stay untouched); Modify
`services/connector_error_notice.py` — `classify_connector_exception` new branch:
```python
if isinstance(exc, ConnectorNotEnabledError) and exc.error_connector_type:
    return ConnectorNotice(connector_type=exc.error_connector_type, action="reconnect")
```
**Tests:** extend the ADR-134 classification/emission test files: enriched error → reconnect;
non-enriched → None; helper: ERROR match / no match / REVOKED excluded / legacy alias / wrong
category; factory integration with a stubbed connector_service.

## Task 5: gates + docs + review
- `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents -q` then full
  `task test:backend:unit:fast`; `task lint`.
- `cd apps/web && pnpm test` + `pnpm exec tsc --noEmit --incremental false` + ratchets.
- Deep code review pass (self), ADR-133 + ADR-134 addendum ("V2 delivered"), spec tracker update.
