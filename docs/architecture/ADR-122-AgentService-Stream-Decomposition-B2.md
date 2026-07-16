# ADR-122: AgentService Stream Decomposition (B2) — Voice/TTS Coordination Extraction

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Author**: Claude Code (Fable 5)
**Related**: v1.21.15 B1 decomposition (method precedent — CHANGELOG entry, no dedicated ADR), [ADR-117](ADR-117-Background-Chat-Runs.md) (listener gating, detached producer), file-size ratchet guard (`test_file_size_ratchet_guard.py`, 2026-07-10)

## Context

`AgentService._stream_with_new_services` (`apps/api/src/domains/agents/api/service.py`)
was the largest function of the backend — **1,135 logical SLOC** (1,674 raw
lines) on the most critical path (every chat turn). The 2026-07 audit flagged
it under finding B1 ("monoliths"); the v1.21.15 release decomposed
`response_node` and `stream_sse_chunks` with the same finding but left the
AgentService generator untouched. Since ADR-117 the surrounding router had
grown as well (tracked separately as R2-03 — legacy-path removal; **only one
of the two work streams in flight at a time**).

A phase/variable coupling map (step 0 of this series) showed the function
spans ~26 phases and that its densest coupling is the **voice/TTS state
machine**: 11 local variables (`chat_voice_streamer`, `chat_voice_drain_task`,
`chat_voice_service`, `voice_service_parallel`, `voice_parallel_task`,
`voice_chunk_queue`, `voice_start_emitted`, `voice_complete_emitted`,
`voice_chunk_count`, `voice_needs_finalization`, `tts_snapshot_for_done`)
crossing 8 phases plus 3 error/exit paths. No other part of the function reads
that state — the natural first seam.

## Method (Feathers, characterization-first — B1 precedent)

A golden-master net was written and verified green **before** any cut:
`tests/agents/test_agent_service_stream_characterization.py` — 11 scenarios
pinning the ordered SSE chunk sequence (types + structural metadata, never LLM
content) and the persistence side effects of `stream_chat_response`:

1. simple conversation, 2. actionable turn with `content_replacement`
(REPLACE semantics), 3. HITL interrupt (no `done` chunk), 4. HITL resumption
(pending-interrupt cleanup + `decision_type` patch), 5. voice PATH 2A (direct
TTS), 6. voice PATH 2B (Voice-LLM sync fallback), 7. voice PATH 1 (chat
progressive drain), 8. parallel progressive voice mid-stream
(`source=parallel_progressive`, backfill pass 1), 9. GraphInterrupt fallback,
10. mid-stream exception (`error` chunk + re-raise), 11. voice synthesis
failure (`voice_error`, stream completes).

ADR-117 note: the tests freeze `background_runs_enabled=False` and drive the
AgentService generator directly — they pin the **producer**, upstream of the
run-stream broker transport. The net passed **identically, unmodified**, after
the extraction.

## Decision

Extract the voice/TTS coordination verbatim into two new modules under
`services/streaming/` (the B1 package):

- **`voice_coordinator.py`** — `VoiceStreamCoordinator`, the stateful machine.
  One instance per run, owner of the 11 former locals. Explicit typed
  interface (no grab-bag dicts): `VoiceStreamContext` (frozen per-run inputs:
  run/user ids, language, timezone, message, lia_gender, personality,
  `user_obj`, `has_listeners` probe, start_time) + driving points called by
  the generator: `on_router_decision`, `feed_token`, `maybe_start_parallel`,
  `drain_progressive_nowait` (non-blocking, returns chunks to yield),
  `close_input`, `finalize(...)` (async generator: PATH 1 drain / PATH 2A
  direct TTS / PATH 2B Voice-LLM + `voice_complete`), `backfill_tts_pass1/2`,
  `tts_snapshot_for_done` property, and two teardown entry points that mirror
  the pre-extraction exits exactly: `cleanup_chat_pipeline()` (GraphInterrupt
  fallback — parallel service intentionally NOT closed there, as before) and
  `cleanup(log_close_failure=)` (nominal path logs a close failure; the
  generator's `except` path lets it propagate into `contextlib.suppress`,
  preserving the old skip-remaining-cleanup semantics).
  - **Follow-up (F005, 2026-07 audit):** the PATH 2A/2B direct-TTS and
    sync-fallback `VoiceCommentService` locals created inside `finalize()` are
    now closed in a `try/finally` (`_close_voice_service_safely`) on success,
    exception, cancellation and early generator `aclose`. The pre-extraction
    code leaked them — `cleanup()`/`cleanup_chat_pipeline()` only cover the chat
    and parallel services — so their OpenAI/ElevenLabs httpx clients were
    retained until process restart (the default Edge provider closes as a
    no-op). Closure is idempotent and never masks the primary error or the SSE
    contract; the two `closed is False` characterizations were inverted to
    `closed is True`.
- **`voice_stream_helpers.py`** — the stateless primitives, moved verbatim:
  `ListenerProbe`, TTS text sanitization (`_looks_like_html`,
  `_sanitize_text_for_tts`, `_sanitize_and_truncate_for_tts`),
  `_format_voice_audio_chunk`, `_should_start_voice` (ADR-117 gate),
  `_stream_voice_chunks_to_queue`, `_cleanup_chat_voice_pipeline`. Split from
  the coordinator to respect the 600-logical-SLOC ratchet cap for new files
  (the single-module version measured 634).

Function-local import style is preserved (`VoiceCommentService`,
`generate_text_summary_for_llm`, `get_db_context`) — same lazy-import
behavior, and test patches at the source modules keep working.

**Invariants held** (hard constraints of the series): SSE event order and
content unchanged (golden net green unmodified); structlog **event names**
unchanged; no LangGraph state key added or touched; no opportunistic
extraction outside the validated perimeter. Only the `logger` field of the
moved log lines changes (module path), as in B1's `DebugMetricsBuilder` —
dashboards keying on `event` are unaffected.

**Numbers**: `service.py` 1,585 → **1,031 logical SLOC** (−35 %; ratchet cap
lowered 1,617 → 1,052 via `task ratchet:update`); `voice_coordinator.py` 532
and `voice_stream_helpers.py` 118 logical SLOC (both under the 600 cap). Two
consumer test files repointed (`test_voice_gating.py`,
`test_tts_text_sanitization.py`).

## Pinned observation (not fixed here)

The sync-path `VoiceCommentService` locals of PATH 2A/2B are **never closed**
by the generator (cleanup only covers the chat-progressive and parallel
services) — a potential keep-alive httpx pool leak. The golden net pins this
behavior as-is (`PINNED CURRENT BEHAVIOR` markers); fixing it is a deliberate
behavior change to be made separately, now trivially localized in
`finalize()`.

## Next seams (planned, one per delivery)

1. **Finalization/archiving** (HITL flag patching, assistant-row archiving,
   token aggregation, stats, done-chunk assembly) → dedicated collaborator.
2. **Setup** (conversation/personality/user/MCP/state-load/attachments/
   archive-first phases) → typed preparation context.

Each follows the same protocol: golden net green before and after, no event
renames, Docker boot + manual pipeline/ReAct/voice check.

## Consequences

- The SSE generator reads as orchestration again; the voice machine is
  independently testable (the golden net exercises it through the real
  generator, the moved unit tests directly).
- The characterization harness (fake collaborator seams for
  ConversationOrchestrator / OrchestrationService / StreamingService /
  TrackingContext / voice services) is reusable as-is for seams #2 and #3.
- Risk accepted: three unpinned micro-branches (chat/parallel start failures,
  PATH 1 timeout) — pure verbatim moves covered by warning logs and the
  manual voice checklist.
