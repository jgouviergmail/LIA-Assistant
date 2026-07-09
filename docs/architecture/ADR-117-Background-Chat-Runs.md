# ADR-117: Background Chat Runs — Detached Execution Surviving Client Disconnects (Lots 1-3)

**Status**: ✅ IMPLEMENTED (2026-07-09) — all three lots, flag-gated OFF by
default. Lot 1: durability. Lot 2: live reattachment, 409 concurrency lock,
listener-gated voice — active-run lock (SET NX EX + heartbeat +
conditional-release Lua, POC-L2-1), `GET /runs/active` +
`GET /runs/{stream_id}/stream` (replay + `: replay-end` transport
boundary), frontend silent auto-resume with `isReplay` side-effect
suppression; E2E-proven (322-chunk backlog replayed then live tail after a
10s-detached run). Lot 3: user cancellation — stop button →
`POST /runs/active/cancel` → cross-worker cancel signal polled by a
producer-side watcher (~1s latency), terminal status `cancelled` distinct
from `killed`, synthesized `done` chunk with `metadata.cancelled` (contract
untouched), partial kept and badged `interrupted`, tokens stay billed
(E2E-proven), plus the POC-3 checkpoint sanitation:
`sanitize_stale_dangling_tool_calls` repairs unanswered `AIMessage`
tool_calls AT TURN START in router_node (never in the reducer, where they
are a legitimate mid-run state; HITL resumptions bypass the router via
`Command(resume)`). Full details:
[BACKGROUND_RUNS.md](../technical/BACKGROUND_RUNS.md).
**Author**: Claude Code (Fable 5)
**Related**: `apps/api/src/infrastructure/streaming/run_stream_broker.py`, `apps/api/src/domains/agents/api/background_runner.py`, [BACKGROUND_RUNS.md](../technical/BACKGROUND_RUNS.md), [ADR-092 (HITL replay-safe)](ADR_INDEX.md), [ADR-063 (cross-worker Redis pub/sub)](ADR_INDEX.md)

## Context

Chat generation was coupled to the lifetime of the HTTP connection. The SSE
endpoint (`POST /agents/chat/stream`) consumed the
`AgentService.stream_chat_response` generator inline: when the client
disconnected — SPA navigation unmounting `useChat` (which aborts the fetch),
tab close, mobile OS dropping the connection — Starlette cancelled the
generator and the LangGraph run died mid-flight. Consequences, all verified
in code before the change:

1. **The whole turn was lost.** Both the user message and the assistant
   response were archived only AFTER graph completion, inside the same
   generator. Any disconnect before that point → nothing in
   `conversation_messages` → the turn vanished on reload.
2. **Billing leak.** `TrackingContext.__aexit__` only persisted token
   records when `exc_type is None`. LLM calls already billed by the
   provider were silently dropped from `message_token_summaries` on every
   disconnect or error.
3. **Cancellation existed only as an accident.** Closing the page WAS a
   cancellation — implicit, dirty, with no finalization. No explicit
   user-facing cancel exists (that is Lot 3).

The product requirements: (a) generation must continue in the background
when the user navigates away or closes the page; (b) the user must be able
to cancel an in-flight response. Both reduce to the same architectural
change: **decouple execution from transport**.

### De-risking study (2026-07, POCs executed in `lia-api-dev`)

Four POCs on the exact production stack (uvicorn 0.48.0 / starlette 1.3.1 /
redis-py 8.0.1 / Redis 7.4 / LangGraph 1.2.4, Python 3.12.13):

- **POC-1 (target architecture)**: a detached asyncio producer publishing
  to a Redis Stream survives client disconnect (30/30 chunks + guaranteed
  finalization after the subscriber aborted at chunk 8); cross-request
  cancellation via a Redis key works from any worker; a cold subscriber
  replays the full stream contiguously from entry 0. PASS 3/3.
- **POC-2 (Redis Streams)**: XADD ≈ 0.09 ms/chunk; full replay of 2000
  chunks in 20 ms; live delivery latency median 0.4 ms; ~122 KB per 1000
  chunks; `EXPIRE` works on stream keys. **Trap proven**: a blocking XREAD
  whose block window reaches the client `socket_timeout` raises
  `TimeoutError` on redis-py 8 → subscribers must poll with SHORT block
  windows (settings-enforced: block 2 s vs socket_timeout 30 s).
- **POC-3 (LangGraph cancellation)**: cancelling mid-node leaves NO partial
  write (state stays at the previous checkpoint); cancelling between
  `call_model` and `execute_tools` leaves a dangling
  `AIMessage(tool_calls)` in the checkpoint; a NEW turn on the same thread
  restarts cleanly from START (the conversation is never bricked) but the
  dangling message stays in history and poisons the sequence for strict
  providers (unique tool_call ids proven unanswered). The sanitation filter
  is Lot 3 scope (cancel feature).
- **POC-4 (worker recycling)**: with `--limit-max-requests` (prod: 10000)
  and NO shutdown drain, an in-flight producer was killed after 1/30 chunks
  when its worker recycled. With a lifespan drain
  (`asyncio.wait(producers, timeout)`), uvicorn waited: 30/30 chunks,
  status `completed`, across 7 worker recycles. **The drain is mandatory.**

Also load-bearing: `stream_chat_response` already had two non-HTTP
consumers running in production daily (scheduled actions executor, channels
inbound handler) — the generator was already transport-agnostic; this
change adds a third consumer, not a refactor of the pipeline.

## Decision

**Detached producer + per-run Redis Stream broker + archive-first, behind
`BACKGROUND_RUNS_ENABLED` (default false).**

1. **Broker** (`infrastructure/streaming/run_stream_broker.py`): one Redis
   Stream per invocation (`chat:run:{stream_id}`), entries = serialized
   `ChatStreamChunk` JSON in an envelope field, terminated by a
   broker-level end marker (`end=1`, `status=completed|error|killed`). The
   end marker is transport-level — **no new ChatStreamChunk type**, the
   SSE contract and its frontend symmetry test are untouched. `XADD` capped
   by `MAXLEN~`, `EXPIRE` armed at end-publish. Subscribers XREAD in a
   short-block loop; empty windows surface as keepalive events (→ SSE
   heartbeats).
2. **Producer** (`domains/agents/api/background_runner.py`): the SSE
   endpoint, flag ON, spawns a detached task that consumes
   `stream_chat_response` and publishes every chunk. The stream ALWAYS
   terminates (completed / error / killed — shielded on hard kill). On
   kill, a best-effort `finalize_partial` callback archives the partial
   assistant content flagged `interrupted` (product decision: partial
   content is KEPT, never silently dropped). Producers register in a
   module set; `drain_chat_producers(timeout)` awaits them at lifespan
   shutdown (POC-4b mitigation). Two identifiers, deliberately distinct:
   `stream_id` (transport — stream key, FRESH per POST) vs `run_id`
   (billing — reused across HITL interrupt + resumption via the new
   `run_id` kwarg on `stream_chat_response`). Reusing the billing id as
   stream key would break HITL resumptions: the interrupt phase's stream
   already carries a terminal marker, so a replay-from-0 subscriber would
   stop there and never see the resumption content (regression-guarded by
   a dedicated producer test).
3. **Archive-first** (`service.py`): the user message is archived BEFORE
   graph execution (with run_id, attachments, STT costs, and
   `hitl_response` when resuming); end-of-run HITL flags (`decision_type`,
   `hitl_interrupted`) are **patched** onto the row at finalization via the
   existing `patch_message_metadata`. Best-effort: an archiving failure
   degrades to legacy behavior, never blocks the run. Scheduled-action
   retries pass `archive_user_message=(attempt == 1)` to avoid duplicate
   user rows.
4. **Billing honesty** (`TrackingContext.__aexit__`): pending token records
   are now persisted on EVERY exit path (normal, exception, cancellation —
   shielded). Safe by construction: the UPSERT commit is incremental and
   idempotent (records cleared after persist), already exercised by
   multi-invocation HITL flows.
5. **Lifecycle**: lifespan shutdown drains chat producers
   (`BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS`, 45 s) then generic
   fire-and-forget tasks (`SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS`,
   15 s) — wiring the previously dead `wait_all_background_tasks`
   (Systemic Rule: dead code is wired or removed; this also fixes the
   latent kill of memory-extraction tasks at every deploy). Compose
   `stop_grace_period: 90s` on the api service (docker default 10 s would
   SIGKILL mid-drain).
6. **Observability**: `chat_background_producers_active` (Gauge),
   `chat_background_runs_total{status}` (Counter); structured events
   `chat_run_producer_started/completed/error/killed`,
   `chat_producers_drain_*`. The e2e duration metric moves to the producer
   on the flag path (the endpoint no longer sees the whole run).

Multi-worker correctness (prod = 4 uvicorn workers): the producer lives on
the worker that received the POST; subscribers XREAD from any worker; Lot 2
reattach and Lot 3 cancel signal go through Redis (per ADR-063 convention).

## Alternatives rejected

- **External task queue (ARQ/Celery/Dramatiq)**: a dedicated worker process
  would survive API recycling, but adds a new process on the RPi5 (memory),
  dispatch latency, and porting of the full request context (ContextVars
  for MCP/skills, ToolDependencies). The codebase already settled this
  question for scheduled actions (in-process execution). Reconsider only if
  the in-process producer shows its limits.
- **Archive-first alone (no detached execution)**: fixes "message lost" but
  not "continue in background" — a third of the requirement.
- **Redis pub/sub (like `user_notifications:{user_id}`)**: no replay — a
  reattaching client would miss everything already emitted. Streams give
  replay + live tail for free.
- **New `cancelled`/`end` ChatStreamChunk type**: would ripple through the
  frontend symmetry test and the 6-language contract for zero user value;
  the end marker is transport, not content.

## Consequences

- **Flag ON**: navigation/tab-close no longer kills generation; on return,
  the completed turn is in history (via existing reload paths). Errors and
  disconnects always persist the user message and the token records.
- **Voice**: `voice_audio_chunk` entries flow through the stream like any
  chunk (they are NOT replayed usefully and TTS is still synthesized for
  absent listeners) — accepted Lot 1 cost, optimized in Lot 2
  (listener-presence check → skip TTS, product decision already made).
- **Lot 2 (reattach)**: active-run registry (`conversation_id → run_id`,
  TTL + heartbeat), strict one-run-per-conversation lock (409), reattach
  endpoint reading the same stream, frontend `isReplay` handler mode
  (suppress toasts/audio side effects during replay).
- **Lot 3 (cancel)**: cancel endpoint + stop button; checkpoint sanitation
  for dangling `AIMessage(tool_calls)` (POC-3 proof test first); no
  rollback of already-executed tools (documented semantics).
- **Legacy path removal**: the flag-OFF inline path (and
  `iter_with_keepalive` usage in the router) is removed in a follow-up
  release once the flag has been proven in production.
- The `hitl_user_response_archived` / `hitl_interrupted_message_archived`
  log events are replaced by `hitl_user_response_flag_patched` /
  `hitl_interrupted_flag_patched` (same signal, patch semantics).

## Verification

- TDD throughout: 5 settings tests, 5 broker envelope unit tests, 2 broker
  integration tests (real Redis: replay, live tail, keepalive, TTL), 4
  producer integration tests (completed/error/killed/content_replacement,
  real Redis), 5 TrackingContext exit tests, 4 archive-first unit tests,
  1 SSE-formatting integration test.
- Full backend non-regression: 8951 unit tests + integration suite green
  with the feature code merged (flag OFF default), ruff/black/mypy strict.
- Docker E2E (flag ON, dev): nominal streaming UX unchanged; the original
  bug scenario (send → navigate away → return → full turn present, tokens
  billed); HITL interrupt/resume with disconnects; scheduled action without
  duplicate user rows; restart mid-run drains gracefully. See
  [BACKGROUND_RUNS.md](../technical/BACKGROUND_RUNS.md) for the operational
  runbook.
