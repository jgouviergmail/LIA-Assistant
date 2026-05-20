# ADR-086: Conversation History Compaction v2 — Hardening, Observability, and User-Visible Truncation

**Status**: ✅ IMPLEMENTED (2026-05-19)
**Author**: Claude Opus 4.7 (with `jgouviergmail`)
**Related**: F4 (Intelligent Context Compaction, 2026-03), ADR-022 (LangGraph State Checkpointing), ADR-018 (SSE Streaming Pattern), ADR-027 (Structured Logging)

---

## Context

### The 2026-05-16 incident

A production user (`08dfb351-…`) could not send any message. Every request hit the conversation-history compaction node, the LLM responded once after ~32 s, then went silent for ~93 s until the SSE stream was cancelled at 125 s with `Erreur de connexion: network error`. Re-tries reproduced the same hang because the partial state was never fully persisted.

Forensic findings ([backend logs](#) + code audit):

| # | Defect | Code |
|---|---|---|
| 1 | `await llm.ainvoke()` had **no timeout** in `_summarize_chunk` | `compaction_service.py:282` |
| 2 | Compaction ran synchronously at the graph entry-point, blocking the whole turn | `graph.py:600` |
| 3 | The router-level `last_heartbeat` only pulsed **between** received chunks, never during a silent `await` (Cloudflare tunnel idle ~100 s closed the connection) | `router.py:541, 598` |
| 4 | Prior `"compaction #N"` SystemMessages were excluded from `to_compact` and accumulated linearly | `compaction_service.py:322` |
| 5 | An `except Exception` branch silently produced `strategy="descriptive_fallback"` with a near-useless stub (`"[Previous conversation compacted — 48 messages…]"`) and was counted as a success | `compaction_service.py:378-397` |
| 6 | No retry on transient errors; no global budget on the whole compaction; no signal to the frontend during the wait | — |
| 7 | The frontend had no `'compacting'` status and no UI hint that a summary was running — the user saw the "sending" state freeze for 2 minutes | — |

The user requested *"rigoureux, méthodique, exhaustif, minutieux et critique"* — a full audit and a 5-day rebuild.

### Product calibration

Three decisions framed the work:
- **Latency budget**: 120 s total before a truncation fallback. Tolerates a slow LLM but still bounded.
- **Failure UX**: explicit user-visible truncation notice ("Older conversation truncated — N messages removed because the automatic summary could not complete (global_timeout). Key identifiers preserved: …"). No HITL modal — adds clicks for a 5-day scope.
- **Delivery**: 5 working days, inline execution, baseline-first, regression discipline at every step.

---

## Decision

### Backend stability (Day 1)

1. **Per-chunk timeout + retry** in `_summarize_chunk` (`compaction_service.py`):
   - `asyncio.wait_for(llm.ainvoke(...), timeout=COMPACTION_PER_CHUNK_TIMEOUT_SECONDS)` (default 35 s).
   - `tenacity.AsyncRetrying` with exponential backoff on `(ConnectionError, TimeoutError)`, up to `COMPACTION_MAX_RETRIES` attempts (default 3).

2. **Global budget + explicit truncation fallback** in `compact()`:
   - `asyncio.wait_for(_compact_impl_llm(...), timeout=COMPACTION_GLOBAL_TIMEOUT_SECONDS)` (default 120 s).
   - On `TimeoutError` or any other unexpected `Exception`, route through `_truncation_fallback()` which produces a `CompactionResult(strategy="truncation", consolidated_previous_summaries=False)` carrying a user-readable notice.

3. **Consolidation of prior summaries** (no more accumulation):
   - When `compaction_include_previous_summaries=True` (default), `_compact_impl_llm` prepends previous `"compaction #N"` SystemMessage contents to the chunk summaries before the merge step. The merge folds them into a single coherent summary.
   - The node emits `RemoveMessage` for the priors **only when** `result.consolidated_previous_summaries=True`. On truncation fallback, priors stay in state — no regression vs v1.

4. **Removal of the silent `descriptive_fallback` branch**: the `except Exception` now re-raises so the outer `compact()` routes through `_truncation_fallback`. The legacy strategy name disappears from new compactions; existing checkpoints with `descriptive_fallback` SystemMessages are unaffected.

5. **New observability metrics** (`metrics_compaction.py`):
   - `compaction_chunk_timeouts_total` — counter
   - `compaction_global_timeouts_total` — counter
   - `compaction_total_duration_seconds` — histogram with buckets {1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 180}

### Backend SSE (Day 2)

6. **Custom-mode stream wiring** so nodes can push UI events:
   - `orchestration/service.py` now calls `graph.astream(..., stream_mode=["values", "messages", "updates", "custom"])` at both call sites.
   - `streaming/service.py` gains `_process_custom_chunk` that translates node-emitted dicts into `ChatStreamChunk`s with `step_type`/`step_label` folded into `metadata` (the schema has no root-level `step_*` fields).

7. **`compaction_start` / `compaction_done` events** emitted by `compaction_node` via `langgraph.config.get_stream_writer`:
   - `compaction_start` is yielded **before** `service.compact(...)` — carries `phase="start"`, `estimated_duration_seconds` (heuristic), and `is_resume`. The frontend uses this to lock the chat input and show the progress banner immediately.
   - `compaction_done` is yielded **after** with `phase="done"`, `strategy`, `tokens_saved`, and `duration_ms`. The frontend dispatches `STREAM_COMPACTION_DONE`, which switches the status back to `'streaming'` for the real assistant response.

8. **Concurrent SSE keepalive** (`apps/api/src/domains/agents/api/sse_keepalive.py`):
   - New `iter_with_keepalive` wraps any async iterable. Uses `asyncio.wait({pending_task}, timeout=keepalive_interval)` with `FIRST_COMPLETED` so a heartbeat sentinel can be emitted **without cancelling** the in-flight `__anext__()` task. No chunk is ever lost.
   - `router.py` SSE generators (both HITL-resume and normal flow) now iterate via this wrapper. The previous inline `last_heartbeat` check is removed. Reuses the existing `settings.sse_heartbeat_interval` (15 s).

### Frontend UX (Day 3)

9. **`ChatStatus 'compacting'` + `CompactionState`** added to `chat-state.ts`. The reducer handles `STREAM_COMPACTION_START` / `STREAM_COMPACTION_DONE`; `SEND_MESSAGE` and `CLEAR_MESSAGES` clear the banner.

10. **SSE handler interception**: `handleExecutionStep` short-circuits when `metadata.step_type === 'compaction'`, dispatching the compaction-specific actions instead of routing into the generic progress accumulator.

11. **`useChat.isTyping`** now includes `'compacting'`, so the existing `disabled={isTyping || isUsageBlocked}` wiring on `ChatInput` automatically locks the textarea while the server summarizes. No new prop needed on `ChatInput`.

12. **`CompactionBanner` component** with two variants:
    - `phase='in_progress'`: blue, spinner, live elapsed timer. ARIA `role="status"` `aria-live="polite"`.
    - `phase='truncated'`: amber, explicit notice.
    - i18n keys `chat.compaction.{in_progress,elapsed,truncated}` for all 6 languages (en, fr, de, es, it, zh).

### Ops & docs (Days 4–5)

13. **SQL recovery script** `scripts/admin/reset_user_checkpoints.sql` — wipes LangGraph checkpoints for a given `thread_id` (= `str(conversation_id)`) inside a transaction with before/after counts. Operator runbook in `docs/technical/COMPACTION_v2.md`.

14. **Grafana dashboard** `14-compaction.json` — 7 panels: strategy mix (5 m rate), latency p50/p95/p99, chunk timeouts, global timeouts, errors by type, skipped reasons, tokens saved p50/p95. Auto-loaded by the existing dashboard provisioner.

---

## Consequences

### Positive
- **No more infinite hangs.** The 2026-05-16 incident class is bounded by `COMPACTION_GLOBAL_TIMEOUT_SECONDS` (120 s default) and surfaces as a user-visible truncation notice.
- **Cloudflare-safe.** The concurrent keepalive emits a heartbeat every 15 s **during** silent awaits — not just between chunks. The tunnel's ~100 s idle cut is no longer reachable.
- **User-visible feedback.** The chat input locks and a banner explains what's happening for the entire compaction window.
- **No more silent summary accumulation.** Prior `"compaction #N"` SystemMessages are folded into the new summary when consolidation succeeds; preserved otherwise.
- **No more silent failure mode.** The `descriptive_fallback` strategy that produced near-useless stubs is gone. The replacement (`truncation`) is explicit and counted in metrics.
- **Observable.** Three new metrics + dashboard. Operators can see the failure rate, latency distribution, and provider error types at a glance.
- **Recoverable.** Stuck conversations have a one-command SQL recovery path.

### Negative / trade-offs
- **`tenacity` is now an explicit dependency** in `requirements.txt` (it was already transitive via `langchain-core`).
- **One additional state field** on `ChatState` (`compaction: CompactionState | null`) and one new `ChatStatus` literal.
- **`stream_mode` now includes `"custom"`** at both `astream` call sites. Any future node that pushes a malformed payload will see a `custom_mode_non_dict_chunk` warning (defensive in `_process_custom_chunk`).
- **The legacy `compaction_duration_seconds` histogram is kept** for backward compatibility with existing Grafana queries even though `compaction_total_duration_seconds` (v2 buckets) is preferred.

### Migration
- **No DB schema change.** Settings are additive (six new env vars with sane defaults in `.env.example` and `.env.prod.example`; `.env.min.prod` intentionally untouched).
- **Existing checkpoints survive.** Conversations that were stuck on a v1 `descriptive_fallback` SystemMessage continue to work; the next compaction will consolidate it if `compaction_include_previous_summaries=true`.
- **No feature flag.** The changes cannot regress v1 behaviour in any meaningful way — timeouts only kick in where there was none; truncation only runs where v1 returned a stub; SSE events are additive. Rollback path: raise `COMPACTION_PER_CHUNK_TIMEOUT_SECONDS=600` and `COMPACTION_GLOBAL_TIMEOUT_SECONDS=600` to effectively disable the new safety net.

---

## Alternatives Considered

1. **Switch the compaction LLM only.** Replacing Qwen-3.5-plus with a faster model would have hidden the immediate symptom but left the architectural defects (no timeout, silent fallback, no UI signal) intact. The next slow provider would have triggered the same incident. **Rejected.**

2. **Full pipeline rewrite** with a Redis lock per thread, an atomic ingress node, pluggable strategies (Protocol), a circuit breaker, an HITL failure modal with 3 choices, chaos and load test suites. Estimated 26 days. The 2026-05-16 incident does not require any of these to be resolved. **Rejected** for v2; some of these may revisit in a future iteration if a new failure class emerges.

3. **Drop compaction entirely** and rely on the `add_messages_with_truncate` reducer's token-based truncation. Cheaper, but produces silent context loss on long conversations — exactly what compaction was introduced to prevent in F4. **Rejected.**

4. **Background async compaction** (run the next turn while compaction completes in the background, persist the summary asynchronously). Architecturally interesting but introduces a state-machine complexity (which turn does the summary belong to? what if the user clears in the meantime?) that the 5-day scope did not justify. **Deferred.**

---

## Metrics of Success

| Indicator | Target | Source |
|---|---|---|
| Hangs > `COMPACTION_GLOBAL_TIMEOUT_SECONDS + 5 s` | **0** | `compaction_total_duration_seconds` histogram p100 |
| `compaction_total_duration_seconds` p99 | **< 90 s** on a typical 65 K-token conversation | dashboard panel 2 |
| `compaction_global_timeouts_total / compaction_executions_total` ratio | **< 1 %** over 24 h | dashboard panel 1 + 4 |
| New `compaction #N` SystemMessages accumulation | **0** (always ≤ 1 at a time) | manual checkpoint inspection / dashboard |
| Frontend banner visible | **within 1 s** of the SSE `compaction_start` event | manual smoke test, Day 5 |
| Truncated-banner shown | **only** when `strategy="truncation"` | reducer + handler unit tests |
| Production user `08dfb351-…` recovery | **can send a new message** without retry loop | next prod deploy |

---

## Self-review

The 17 defects identified during the initial audit map to the resolution as follows:

| # | Defect | Resolution |
|---|---|---|
| 1 | No `wait_for` on `ainvoke` | Day 1 — per-chunk timeout |
| 2 | Multi-chunk has no global budget | Day 1 — global timeout |
| 3 | Heartbeat blind to silent awaits | Day 2 — concurrent keepalive |
| 4 | Prior summaries accumulate | Day 1 — consolidation flag |
| 5 | Silent `descriptive_fallback` | Day 1 — replaced with explicit truncation |
| 6 | No retry | Day 1 — tenacity |
| 7 | No frontend signal | Day 2 + Day 3 — SSE events + banner |
| 8 | No chat-input lock | Day 3 — `isTyping` includes `'compacting'` |
| 9 | No metrics | Day 1 — 3 new + Day 4 dashboard |
| 10 | No recovery path | Day 4 — SQL script |
| 11 | No ADR | Day 5 — this document |

Five defects were considered out of scope for v2 (no Redis lock, no atomic ingress node, no pluggable strategies Protocol, no circuit breaker, no HITL failure modal). They are documented in *Alternatives Considered* with the reasoning for deferral.

---

## Update — 2026-05-19: pivot from in-flow banner to sonner toast

After Day 5, manual repro on a 27 K-token conversation surfaced an UX
defect: the `<CompactionBanner>` was rendered at the top of the scrollable
chat list (`ChatMessageList`) and was therefore invisible once the user
scrolled to the bottom — which is the default state right after sending a
message. A sticky-top variant was attempted (`position: sticky; top: 0`)
but the dual overflow boundary (`overflow-y: auto` on the scroll container
**and** the inner max-width wrapper) made it brittle across responsive
breakpoints.

The decision was to pivot to a `sonner` toast for compaction feedback. The
SSE event contract (`compaction_start` / `compaction_done`) and the
reducer state (`status === 'compacting'` → `isTyping` → input lock) are
**unchanged** — only the rendering layer moved.

Concretely:

1. **`<CompactionBanner>` deleted** along with its test file and its CSS
   rules in `globals.css`.
2. **`handleCompactionStep`** ([`apps/web/src/lib/sse-handlers/handlers.ts`](../../apps/web/src/lib/sse-handlers/handlers.ts))
   now calls `toast.loading(...)` on `compaction_start` and morphs the
   same toast id (`COMPACTION_TOAST_ID`) into `toast.success(...)` or
   `toast.warning(...)` on `compaction_done`, depending on the strategy.
3. **i18n key `chat.compaction.completed`** added in the 6 locales for the
   success toast (`"Conversation summarized — {{tokens}} tokens freed."`).
   The unused `chat.compaction.elapsed` key was removed.
4. **`ChatMessageList`** no longer receives a `compaction` prop. The
   `compaction` field is no longer exported from `useChat` (the in-flight
   state still lives in the reducer to drive the input lock).
5. **A `ContextUsagePill` component** was added to the chat header. It
   displays the current `tokens / threshold` ratio (clamped to 100 % in
   the badge label, real ratio kept in the tooltip), giving the user
   continuous feedback on how close they are to triggering a compaction.

The trade-off is intentional:

| Banner (original) | Toast (current) |
|---|---|
| In-flow, themed, can show inline elapsed timer | Position fixed by sonner — visible no matter the scroll state |
| Coupled to the message list layout | Decoupled, no CSS surface to maintain |
| Required custom CSS + dedicated component | Reuses an existing project library (sonner) already wired |
| Invisible at default scroll position in long conversations | Always visible, auto-dismiss after success/warning |

The 2026-05-16 incident's root cause was **never** the rendering layer —
it was the lack of timeout/retry/keepalive on the backend. The pivot
addresses an UX regression introduced by the v2 banner placement, not the
production blocker that drove this ADR.

The success criteria from §5 are unchanged. Only "Frontend banner visible
within 1 s" is rephrased as "sonner toast appears within 1 s of the SSE
`compaction_start` event" in the runbook.
