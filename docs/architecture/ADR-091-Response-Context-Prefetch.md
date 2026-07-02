# ADR-091: Response-Context Prefetch — Initiative ∥ Response Latency Overlap

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-062](ADR-062-Agent-Initiative-Phase.md) (Initiative phase), [ADR-070](ADR-070-ReAct-Execution-Mode.md) (ReAct mode)

## Context

On tool-using turns, the initiative node's LLM evaluation takes several seconds
(measured ~12s with the reference model). Only after it completes does the
response node start, and its FIRST step is a batch of user-context injections —
user-message embedding, long-term memory profile, user RAG, system RAG,
journal, portrait, psyche — that are I/O-bound and depend ONLY on the user
message, never on tool or initiative results. They were paid serially on the
critical path (~0.5–2s of avoidable latency per enriched turn).

A graph-level fan-out (`[react_finalize ∥ initiative]`) was evaluated and
rejected: `react_finalize` runs in milliseconds (no LLM), so the overlap gain
would be ~0, while unequal branch lengths around the pipeline initiative loop
risk double-executing the response node (LangGraph super-step semantics).

## Decision

Extract the response node's context-injection block verbatim into
`src/domains/agents/services/response_context.py`:

- `fetch_response_context(state, config, run_id) -> ResponseContextBundle` —
  the embedding + six injections (briefing pattern: each acquires its OWN
  `AsyncSession`; every injection keeps its historical failure-to-neutral
  semantics).
- A **process-local, bounded prefetch registry** keyed by `run_id`:
  `start_response_context_prefetch()` (idempotent per run, launches an
  `asyncio.Task`, evicts + cancels beyond
  `RESPONSE_CONTEXT_PREFETCH_MAX_ENTRIES`) and `pop_response_context()`
  (consume-once, `RESPONSE_CONTEXT_PREFETCH_AWAIT_TIMEOUT_SECONDS` cap).

Flow: the **initiative node starts the prefetch on entry** (it then overlaps
the initiative LLM call in BOTH execution modes, with no graph topology
change); the **response node pops the bundle** and, on any miss (conversation
turns, initiative disabled or skipped early, timeout, failure), runs the exact
same `fetch_response_context()` inline — zero behavioural delta on non-covered
paths.

Process-locality is safe: no HITL interrupt exists between initiative and
response (draft interrupts happen BEFORE initiative; a resume executes
initiative + response in one process/request).

Settings (all in `.env`): `RESPONSE_CONTEXT_PREFETCH_ENABLED` (kill switch,
default true), `RESPONSE_CONTEXT_PREFETCH_MAX_ENTRIES` (64),
`RESPONSE_CONTEXT_PREFETCH_AWAIT_TIMEOUT_SECONDS` (20).

Accepted side effects: psyche temporal decay commits ~seconds earlier (still
pre-response); embedding trace attribution moves from the response node to the
initiative node (cosmetic).

## Related latency optimizations (same 2026-07 campaign, no ADR each)

Documented here as pointers — each carries its own kill switch and in-code
rationale:

- **LLM instance cache** (`infrastructure/llm/factory.py`): `get_llm()` reuses
  client instances keyed by the fully resolved config (httpx pool keep-alive —
  no TCP/TLS handshake per call). Invalidation: config changes change the key;
  API-key/capability reloads call `clear_llm_instance_cache()`.
  `LLM_INSTANCE_CACHE_ENABLED`.
- **Reasoning-stream negative cache**
  (`infrastructure/llm/structured_output.py`): buffered structured-output
  paths that silently paid a SECOND full LLM call when the reasoning stream
  yielded no terminal output are learned at runtime per (provider, model,
  path) — at most one double call per combination per worker; Prometheus
  `llm_reasoning_stream_double_call_total`. `query_analyzer` is permanently
  excluded from reasoning streaming (one guaranteed call per turn).
- **Non-blocking contacts warmup** (`agents/api/service.py`): the 300–800ms
  People API warmup no longer blocks the request path (fire-and-forget with a
  dedicated DB session; cache-miss fallback makes it always-correct).
- **RAG query-embedding cache + single-flight** (`rag_spaces/embedding.py`):
  user-RAG and system-RAG retrievals of the same turn share one Gemini call.
- **Reducer token-count memoization** (`agents/models.py`): the truncation
  reducer no longer re-encodes the full history through tiktoken on every
  messages-channel update (per-message-id cache, content-length guarded).
- **Frontend token batching** (`apps/web/src/lib/sse-handlers/index.ts`): SSE
  tokens coalesced per animation frame (was O(N²) remark/rehype re-parsing);
  ordering preserved (any non-token chunk flushes first).
- **HTML display-mode CSS externalized** (`apps/web/src/styles/
  lia-components.css` + `html_response_directive.txt`): the LLM no longer
  emits a ~550-token inline `<style>` block per rich-HTML reply (~3–4s of
  generation); rules now ship once in the app stylesheet (identical rendering,
  old messages with the inline block unaffected).

## Consequences

- Positive: ~0.5–2s taken off the critical path of every initiative-enriched
  turn, in both pipeline and ReAct modes, with inline fallback keeping every
  other path byte-identical; the shared module ends the duplication of the
  injection block.
- Negative / accepted: a run cancelled between initiative and response leaves
  its task in the registry until eviction (bounded at 64, cancelled on evict);
  a pathological >20s prefetch is abandoned and re-done inline (double work,
  never wrong results).
