# ADR-116: Frontend Test Foundation — Ratcheted Coverage Gate & SSE Contract Symmetry

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Author**: Claude Code (Fable 5)
**Related**: `apps/web/vitest.config.ts`, `apps/web/src/lib/sse-handlers/__tests__/sse-symmetry.test.ts`, [GUIDE_TESTING.md](../guides/GUIDE_TESTING.md) §Tests Frontend, `apps/api/src/domains/agents/api/schemas.py`

## Context

The frontend's most critical state machine — chat SSE streaming + HITL
approval flows + voice mode — was protected only by `tsc` and `eslint`:
19 test files covered 448 source files (~86k LOC), and the chat reducer,
the SSE handler pipeline, the zustand stores and the three central hooks
(`useChat`, `useConversation`, `useVoiceMode`) had little to no coverage.

Worse, the coverage tooling itself was fictional: `@vitest/coverage-v8`
was not installed (`pnpm test:coverage` crashed on a missing dependency),
and the CI step ran `pnpm test -- --coverage` — pnpm forwards the literal
`--` to vitest, which silently ignores the flag, so **no coverage report
had ever been produced or uploaded** (the Codecov step was masked by
`fail_ci_if_error: false`).

A related class of silent drift lived in the SSE wire contract: the backend
`ChatStreamChunk` Literal declared 27 chunk types, of which 8 had **no
emission site at all** (`planner_metadata`, `planner_error`,
`hitl_clarification_*`, `hitl_question`, `hitl_rejection*`); the frontend
carried a zombie handler for one of them, five phantom types that never
existed in the contract, and one genuinely emitted event
(`hitl_streaming_fallback`) that no handler processed — it had been falling
into a debug log as "unknown event type" for months.

## Decision

1. **Three-layer test foundation** (434 vitest tests, +234):
   - *Pure logic at 100%*: `chat-reducer(-errors)`, all 19 SSE handlers,
     `psycheStore`/`voiceModeStore` — 100% statements/branches/functions/
     lines, with deep-frozen input states proving reducer immutability.
   - *Hooks with scripted I/O*: `useChat` driven by scripted SSE chunk
     sequences through the real `processSSEChunk`→reducer pipeline
     (including the full HITL interrupt→resume cycle), `useVoiceMode`
     driven through fake `AudioContext`/`AudioWorkletNode`/`getUserMedia`
     and captured KWS/VAD/WebSocket callbacks — no real audio, no MSW.
   - *Ratcheted thresholds* in `vitest.config.ts`: the fully-covered
     directories are locked at 100 via per-glob thresholds, the three hooks
     at their measured values, plus a low global floor. Thresholds are set
     just under the measured value, only ever go up, and never down —
     lowering one to make CI pass is a regression to fix, not a knob.
     (Verified empirically on vitest 4.1: the global floor is computed over
     the whole `include` set; glob-matched files are NOT subtracted.)

2. **SSE contract symmetry as an executable invariant**
   (`sse-symmetry.test.ts`): the backend Literal is pinned in the test and
   re-parsed from `apps/api/.../schemas.py` whenever the file is reachable
   (host checkouts and CI; the web dev container only mounts `apps/web`).
   Every contract type must have a frontend handler or an explicitly
   documented entry in `ACKNOWLEDGED_UNHANDLED` (empty as of this ADR).
   Pydantic already enforces the Literal at runtime on every emission path
   — including the LangGraph custom-mode passthrough — so the pinned list
   covers everything that can reach the wire.

3. **Contract cleanup**: the 8 never-emitted types were removed from the
   backend Literal together with their dead consumer branches (router e2e
   metrics extraction, Prometheus event-type mapping); the frontend lost its
   phantom `SSEChunkType` entries, the zombie `planner_metadata` handler,
   ~60 lines of dead log branches in the SSE client, and four dead symbols
   (`PlannerMetadata`, `OrchestrationMetadata`, `SSE_CHUNK_TYPES`,
   `SSE_STATUS`). `hitl_streaming_fallback` gained an awareness handler
   (structured warn, no UX change).

4. **CI truthfulness**: the CI step now runs `pnpm test:coverage` (the
   dedicated script), so the thresholds gate every push and Codecov
   receives a real report for the first time.

## Consequences

- Any coverage regression in the locked areas fails `pnpm test:coverage`,
  and therefore CI. New backend SSE event types fail the symmetry test
  until the frontend takes an explicit decision (handler or documented
  non-handling).
- Four user-facing bugs were found and fixed by writing the tests
  (RED→GREEN): a zustand `setError` that corrupted the voice state key,
  a stale closure that swallowed WebSocket drops during voice transcription
  (infinite "processing" spinner), an orphaned setup-timeout promise firing
  unhandled rejections after every wake-word recording, and chat stream
  errors rendered with a hardcoded French prefix instead of the (already
  shipped but never wired) `ChatStreamError.i18nKey` mechanism.
- The e2e metric `agents_count` (router) was found to have been frozen at 0
  since `planner_metadata` stopped being emitted — its dead extraction
  branch is removed; re-feeding the metric from `execution_step` events (or
  retiring the complexity dimension) is left as follow-up.

## Alternatives considered

- **MSW for hook tests** — rejected: the SSE client is a hand-rolled
  fetch-stream parser; a scripted chunk driver at the `chatSSEClient`
  boundary is simpler, faster and already consistent with the repo's
  module-level `vi.mock` style.
- **Keeping the dead contract entries** ("they might come back") — rejected
  per the systemic dead-code rule: an unwired contract entry costs
  maintenance and fakes coverage; re-adding a type is trivial and now
  forces the frontend decision via the symmetry test.
- **A snapshot test of the handler map** — rejected: snapshots pin the
  frontend against itself; the invariant that matters is frontend ↔ backend
  symmetry, which requires reading the backend source of truth.
