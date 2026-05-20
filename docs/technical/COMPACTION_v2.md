# Conversation History Compaction v2 — Technical Reference

**Status**: Implemented (2026-05-19) — see ADR-086.

This document is the operational and developer reference for the v2 compaction
hardening shipped in May 2026. It complements the architectural rationale
([ADR-086](../architecture/ADR-086-Conversation-History-Compaction-v2.md)) and
the original F4 implementation (`compaction_service.py`, 2026-03).

---

## 1. When and why compaction runs

The `compaction_node` is the entry point of the LangGraph agent graph. On each
turn, before any router/planner runs, it asks `CompactionService.should_compact`
whether the conversation has exceeded its token budget. Two settings drive the
trigger:

- `COMPACTION_TOKEN_THRESHOLD` (absolute) — `0` to disable absolute override.
- `COMPACTION_THRESHOLD_RATIO` (dynamic, default `0.4`) — the threshold is then
  `0.4 × context_window(response_model)`. With a 128 K model that gives ~51 K.

If the threshold is exceeded **and** no HITL state would be corrupted (draft
critique pending, entity disambiguation, etc.), compaction runs.

The user can also force a compaction with the slash command `/resume` (handled
by `_is_resume_command`).

## 2. Pipeline (v2)

```
graph entry → compaction_node
  │
  ├─ writer({compaction_start, estimated_duration_seconds, is_resume})  ← custom mode
  │
  ├─ CompactionService.compact(messages, preserve_recent_n, language, config)
  │     │
  │     ├─ asyncio.wait_for(compact_impl_llm, timeout=GLOBAL_TIMEOUT=120s)
  │     │     │
  │     │     ├─ collect prior "compaction #N" SystemMessages (consolidation)
  │     │     ├─ split to_compact into chunks (≤ CHUNK_MAX_TOKENS=20k)
  │     │     ├─ for each chunk: _summarize_chunk()
  │     │     │     ├─ asyncio.wait_for(llm.ainvoke, timeout=PER_CHUNK=35s)
  │     │     │     └─ tenacity retry × MAX_RETRIES=3 on (ConnectionError, TimeoutError)
  │     │     ├─ if multi-chunk OR prior summaries present: merge step (1 more LLM call)
  │     │     └─ return CompactionResult(strategy=single_chunk|multi_chunk,
  │     │            consolidated_previous_summaries=bool)
  │     │
  │     ├─ on TimeoutError  → _truncation_fallback(reason="global_timeout")
  │     ├─ on Exception     → _truncation_fallback(reason=f"unexpected:{type}")
  │     │
  │     └─ _truncation_fallback: LLM-less, deterministic, produces a
  │           user-readable SystemMessage and sets
  │           consolidated_previous_summaries=False so the node leaves
  │           prior "compaction #N" SystemMessages in place.
  │
  ├─ node applies RemoveMessage for compacted messages
  ├─ if consolidated_previous_summaries=True, ALSO RemoveMessage for prior summaries
  ├─ writer({compaction_done, strategy, tokens_saved, duration_ms})  ← custom mode
  │
  └─ continues to router → planner → ... → response
```

## 3. SSE events on the wire

Both events are typed as `execution_step` on the wire (the `ChatStreamChunk`
type union is fixed), but they carry `metadata.step_type === "compaction"`
which the frontend handler `handleCompactionStep` uses to intercept them.

```json
// compaction_start
{
  "type": "execution_step",
  "content": "",
  "metadata": {
    "step_type": "compaction",
    "step_label": "compaction_start",
    "phase": "start",
    "estimated_duration_seconds": 30,
    "is_resume": false
  }
}

// compaction_done — success
{
  "type": "execution_step",
  "content": "",
  "metadata": {
    "step_type": "compaction",
    "step_label": "compaction_done",
    "phase": "done",
    "strategy": "multi_chunk",
    "tokens_saved": 49600,
    "duration_ms": 28734
  }
}

// compaction_done — truncation fallback
{
  "type": "execution_step",
  "content": "",
  "metadata": {
    "step_type": "compaction",
    "step_label": "compaction_done",
    "phase": "done",
    "strategy": "truncation",
    "tokens_saved": 0,
    "duration_ms": 1
  }
}
```

In addition, the SSE generator emits `: keepalive\n\n` comment lines every
`SSE_HEARTBEAT_INTERVAL` (15 s default) **during silent phases**, including
inside the compaction LLM call. The `iter_with_keepalive` wrapper does this
without cancelling the upstream task — see
`apps/api/src/domains/agents/api/sse_keepalive.py`.

## 4. Settings reference

All settings live in `apps/api/src/core/config/agents.py`. Defaults in
`apps/api/src/core/constants.py`. Documented in `.env.example` and
`.env.prod.example` (intentionally **not** in `.env.min.prod` — sane defaults
cover production).

| Setting | Default | Range | Effect |
|---|---|---|---|
| `COMPACTION_ENABLED` | `true` | bool | Master switch. |
| `COMPACTION_THRESHOLD_RATIO` | `0.4` | 0.1–0.9 | Dynamic threshold ratio of the response model context window. |
| `COMPACTION_TOKEN_THRESHOLD` | `0` | `0` or ≥1 | Absolute override (`0` = use dynamic ratio). |
| `COMPACTION_PRESERVE_RECENT_MESSAGES` | `10` | 2–50 | Never-compacted recent messages. |
| `COMPACTION_CHUNK_MAX_TOKENS` | `20000` | 1k–100k | Max input tokens per LLM chunk. |
| `COMPACTION_MIN_MESSAGES` | `20` | 5–200 | Fast-path skip below this count. |
| `COMPACTION_PER_CHUNK_TIMEOUT_SECONDS` | `35` | 5–300 | Per-chunk `asyncio.wait_for`. |
| `COMPACTION_GLOBAL_TIMEOUT_SECONDS` | `120` | 10–600 | Whole `compact()` budget. |
| `COMPACTION_MAX_RETRIES` | `3` | 1–10 | Tenacity attempts per chunk. |
| `COMPACTION_RETRY_BACKOFF_BASE_SECONDS` | `1.0` | 0.1–10 | Exponential backoff base. |
| `COMPACTION_INCLUDE_PREVIOUS_SUMMARIES` | `true` | bool | Consolidate prior `"compaction #N"`. |
| `SSE_HEARTBEAT_INTERVAL` | `15` | >0 | Reused for keepalive cadence. |

## 5. Metrics

Defined in `apps/api/src/infrastructure/observability/metrics_compaction.py`.

| Metric | Type | Labels | Use |
|---|---|---|---|
| `compaction_executions_total` | Counter | `strategy` (`single_chunk`/`multi_chunk`/`truncation`/`noop`) | Volume + mix |
| `compaction_skipped_total` | Counter | `reason` | Why threshold/safety blocked |
| `compaction_chunk_timeouts_total` | Counter | — | New v2 — per-chunk timeouts fired |
| `compaction_global_timeouts_total` | Counter | — | New v2 — global budget exceeded → truncation |
| `compaction_total_duration_seconds` | Histogram | — | New v2 — buckets 1..180s |
| `compaction_duration_seconds` | Histogram | — | Legacy (kept for backward-compat) |
| `compaction_tokens_saved` | Histogram | — | Per-compaction savings |
| `compaction_cost_tokens_total` | Counter | `token_type` (prompt/completion) | LLM cost |
| `compaction_errors_total` | Counter | `error_type` (llm_failure/unexpected) | Failures |

Dashboard: **"14 - Compaction v2"** (Grafana, auto-loaded). 7 panels covering
strategy mix, latency percentiles, chunk timeouts, global timeouts (red),
errors by type, skipped reasons, tokens saved.

## 6. Failure modes

| Scenario | Detection | Response |
|---|---|---|
| Single LLM call slow > 35 s | `asyncio.wait_for(per_chunk)` | Tenacity retries up to 3× with backoff |
| Provider down (retries exhausted) | `tenacity.reraise=True` | Re-raised inside `_compact_impl_llm` → caught by outer `compact()` → `_truncation_fallback` |
| Compaction global budget > 120 s | `asyncio.wait_for(global)` in `compact()` | `TimeoutError` → `_truncation_fallback` with `reason="global_timeout"` |
| Cloudflare-style idle cut | `iter_with_keepalive` pulses every 15 s | Stream stays open |
| Unexpected non-LLM exception | `except Exception` in `compact()` | `_truncation_fallback` with `reason="unexpected:<Type>"` |
| Frontend disconnects mid-compaction | `iter_with_keepalive` cancels pending task | Clean shutdown, no leaked task |

The truncation fallback's notice (rendered as a SystemMessage in the
conversation) reads:

```
[Older conversation truncated — N messages removed because the automatic
summary could not complete (global_timeout). Key identifiers preserved:
email_hash_a8f3..., people/c123..., 08dfb351-..., ...]
```

The frontend `toast.warning` (driven by `handleCompactionStep` on
`strategy === "truncation"`) carries the localized equivalent of:

> The older conversation was truncated because the summary could not be generated.

The toast uses a stable id (`COMPACTION_TOAST_ID = "compaction-progress"`)
so the in-flight `toast.loading` morphs in place into the warning instead
of stacking a new notification.

## 7. Operator runbook

### Stuck conversation recovery

If a user reports a conversation they cannot use any more (regardless of
cause), the fastest reset path is:

```bash
# In dev (Docker stack up):
docker exec -i lia-postgres-dev \
  psql -U lia -d lia \
  -v thread_id="'<user-uuid>'" \
  < scripts/admin/reset_user_checkpoints.sql

# In prod (RPi5):
ssh -p 2222 jgo@192.168.0.14
docker exec -i lia-postgres-prod \
  psql -U lia -d lia \
  -v thread_id="'<user-uuid>'" \
  < /path/to/reset_user_checkpoints.sql
```

The script runs inside a transaction, shows before/after counts, and only
touches LangGraph's `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`
tables — application data (messages, conversations) is untouched.

### Threshold tuning during a local repro

To reach the compaction code path without seeding a huge conversation,
temporarily lower the threshold in `apps/api/.env.dev`:

```
COMPACTION_TOKEN_THRESHOLD=2000
```

Restart the backend; 4–5 short messages will trigger compaction on the next
turn. **Don't forget to reset to `0` (dynamic) when finished.**

### Forcing compaction on demand

Send the literal text `/resume` as a chat message. The node detects it
(`_is_resume_command`), forces compaction regardless of the threshold, then
consumes the `/resume` message (it is not forwarded to the router).

### Diagnosing in Grafana

- **"Strategy mix"** showing a red `truncation` line → global timeouts firing.
  Cross-check with **"Global timeouts → truncation"** panel.
- **"Per-chunk timeouts"** consistently > 0 → tune
  `COMPACTION_PER_CHUNK_TIMEOUT_SECONDS` or switch LLM provider.
- **"Latency p99"** drifting above 90 s → compaction LLM is the bottleneck;
  consider a faster model or smaller chunks.
- **"Skipped reasons"** dominated by `hitl_pending_*` → conversations are
  blocked on HITL interactions, not a compaction issue.

### Cloudflare tunnel

The 15 s SSE keepalive (`iter_with_keepalive`) is sufficient to neutralize
the ~100 s idle cut of a default `cloudflared` tunnel. **No `cloudflared`
configuration change is needed.** If the keepalive ever gets disabled (eg
`SSE_HEARTBEAT_INTERVAL` set to 0 — which the Pydantic validation refuses, so
this requires code surgery), `idleTimeout` should be raised to 180 s in
`/etc/cloudflared/config.yml` on the RPi5.

---

## 8. Test coverage

Unit tests (backend):
- `apps/api/tests/unit/agents/services/test_compaction_service.py` — 22 tests
  (existing v1, updated mocks for new settings).
- `apps/api/tests/unit/agents/services/test_compaction_service_v2.py` — 7 new
  tests: per-chunk timeout, retry-then-succeed, retry exhaustion, global
  timeout fallback, unexpected error fallback, truncation preserves
  `consolidated_previous_summaries=False` flag, previous summaries
  consolidated on success.
- `apps/api/tests/unit/agents/nodes/test_compaction_node.py` — 16 tests
  including 2 new (Task 1.5): RemoveMessage emitted iff consolidated;
  RemoveMessage NOT emitted on truncation fallback; and 2 new (Task 2.2):
  compaction_start/done events emitted.
- `apps/api/tests/services/test_streaming_service.py` — 4 new tests
  `TestProcessCustomChunk`: well-formed forward, non-dict rejection,
  missing metadata, root-vs-metadata precedence.
- `apps/api/tests/unit/agents/api/test_sse_keepalive.py` — 8 tests for the
  concurrent keepalive wrapper.
- `apps/api/tests/unit/agents/api/test_custom_stream_mode_integration.py` —
  1 integration test exercising the full LangGraph custom-mode →
  `_process_custom_chunk` path.

Unit tests (frontend):
- `apps/web/src/reducers/__tests__/chat-reducer.compaction.test.ts` — 6 tests.
- `apps/web/src/lib/sse-handlers/__tests__/compaction-handler.test.ts` —
  5 tests (compaction event interception + non-compaction regression guard).
- `apps/web/src/components/chat/__tests__/ContextUsagePill.test.tsx` — 7
  tests including ratio-overshoot clamping on the pill badge.

Manual smoke test (Day 5):
1. Set `COMPACTION_TOKEN_THRESHOLD=2000` in `.env.dev`; restart backend.
2. Open a fresh chat, send 5–6 short messages.
3. On the next message: a sonner `toast.loading` appears < 1 s with the
   localized "Summarizing the conversation…" copy; textarea is disabled
   (driven by `status === 'compacting'` → `isTyping`).
4. The toast morphs into a `toast.success` with token count; real response
   streams in.
5. Test failure path: set `COMPACTION_PER_CHUNK_TIMEOUT_SECONDS=0.5`,
   trigger again; the toast morphs into a `toast.warning` carrying the
   truncated notice, the real response still streams.
6. Test `/resume`: type `/resume` in a small conversation; toast appears
   briefly, assistant confirms the compaction.
7. Reset `.env.dev` to defaults.

---

## 9. References

- [ADR-086](../architecture/ADR-086-Conversation-History-Compaction-v2.md) —
  full architectural rationale and decision log.
- [F4 commit history](#) — original 2026-03 implementation.
- [`compaction_service.py`](../../apps/api/src/domains/agents/services/compaction_service.py)
- [`compaction_node.py`](../../apps/api/src/domains/agents/nodes/compaction_node.py)
- [`sse_keepalive.py`](../../apps/api/src/domains/agents/api/sse_keepalive.py)
- [`handlers.ts → handleCompactionStep`](../../apps/web/src/lib/sse-handlers/handlers.ts)
  — frontend SSE handler that drives the sonner toast lifecycle.
- [`ContextUsagePill.tsx`](../../apps/web/src/components/chat/ContextUsagePill.tsx)
  — discreet progress indicator showing tokens vs the compaction threshold.
