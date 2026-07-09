# Background Chat Runs — Detached Execution (ADR-117)

Chat generation decoupled from the HTTP connection: a detached producer
executes the run and publishes chunks to a per-run Redis Stream; the SSE
endpoint is a mere subscriber. Navigation, tab close, or a dropped mobile
connection no longer kill the generation — the turn (user message, assistant
response, token records) is always persisted.

**Feature flag**: `BACKGROUND_RUNS_ENABLED` (default `false`). Flag OFF, the
legacy inline SSE path runs unchanged — instant rollback without rebuild.

## Architecture

```mermaid
flowchart LR
    subgraph Browser
        UI[Chat UI / useChat]
    end
    subgraph API worker
        EP["POST /agents/chat/stream<br/>(subscriber)"]
        PROD["Detached producer task<br/>(background_runner)"]
        GEN["stream_chat_response<br/>(LangGraph pipeline)"]
    end
    subgraph Redis
        STREAM[("chat:run:{run_id}<br/>Redis Stream")]
    end
    UI -- "POST message" --> EP
    EP -- "spawn (flag ON)" --> PROD
    PROD -- consumes --> GEN
    PROD -- "XADD chunk JSON" --> STREAM
    STREAM -- "XREAD (short blocks)" --> EP
    EP -- "SSE data: / heartbeats" --> UI
    UI -. "disconnect (navigation)" .-> EP
    PROD -. "unaffected, finishes & archives" .-> STREAM
```

The producer, not the endpoint, owns the run: archiving, token tracking and
HITL bookkeeping all live inside the generator it consumes. The endpoint
only formats stream events as SSE lines. A client disconnect cancels the
subscriber generator; the producer keeps running to completion.

`stream_chat_response` keeps its three other consumers unchanged (legacy
SSE path flag OFF, scheduled actions executor, channels inbound handler).

## Broker protocol (transport-level, invisible to the SSE contract)

| Entry fields | Meaning |
|---|---|
| `{"d": <ChatStreamChunk JSON>}` | One chunk, relayed verbatim to SSE `data:` |
| `{"end": "1", "status": s}` | Terminal marker; `s ∈ completed \| error \| killed` |

- Stream key: `chat:run:{stream_id}` (`REDIS_KEY_RUN_STREAM_PREFIX`).
- **Two identifiers, deliberately distinct**: `stream_id` (transport — the
  stream key suffix, FRESH on every POST) vs `run_id` (billing/correlation —
  reused across HITL interrupt + resumption for token aggregation, passed
  down via the `run_id` kwarg of `stream_chat_response`). On a HITL
  resumption the interrupt phase already wrote a terminal marker on its own
  stream; reusing that stream would make a replay-from-0 subscriber stop at
  the stale marker and never see the resumption content (regression-guarded
  by `test_hitl_resumption_fresh_stream_avoids_stale_end_marker`).
- The stream ALWAYS terminates — subscribers can never hang. On abnormal
  producer death the marker is written under `asyncio.shield`.
- `XADD` uses `MAXLEN ~` (`BACKGROUND_RUNS_STREAM_MAXLEN`); `EXPIRE` is
  armed when the terminal marker is published
  (`BACKGROUND_RUNS_STREAM_TTL_SECONDS`).
- No new `ChatStreamChunk` type: the frontend SSE symmetry test is
  untouched.

## Run lifecycle

1. **Start** (flag ON): endpoint checks auth/usage-limits/pending-HITL as
   before, generates `run_id`, builds the chat generator, spawns the
   producer, subscribes.
2. **Archive-first**: inside the generator, the user message row is
   persisted BEFORE graph execution (metadata: `run_id`, attachments, STT
   costs, `hitl_response` on resumption). End-of-run HITL flags
   (`decision_type`, `hitl_interrupted`) are patched onto that row at
   finalization. An archive failure never blocks the run (best-effort,
   logged `archive_first_user_message_failed`).
3. **Streaming**: every chunk is XADDed; the subscriber relays them with
   the legacy pacing (`agent_stream_sleep_interval`) and emits `: heartbeat`
   on empty XREAD windows.
4. **End**:
   - `completed` — generator finished; assistant row archived by the
     service as before; e2e duration metric observed by the producer.
   - `error` — generator raised after emitting its own error/done chunks;
     marker written best-effort (if Redis itself died, subscribers error
     out on their own XREAD).
   - `killed` — producer task cancelled (shutdown drain timeout, loop
     teardown). Token records were already persisted by
     `TrackingContext.__aexit__` (which now commits on EVERY exit path —
     billing honesty); the accumulated partial assistant content is
     archived flagged `{"interrupted": true, "interrupt_reason": "killed"}`.

## Shutdown & worker recycling

Proven by POC (2026-07): without a drain, uvicorn worker recycling
(`--limit-max-requests`) kills in-flight producers (1/30 chunks survived);
with the lifespan drain, uvicorn waits (30/30). Wiring:

1. Lifespan shutdown FIRST drains chat producers
   (`BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS`, 45 s), THEN generic
   fire-and-forget tasks (`SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS`,
   15 s) — before any infrastructure teardown (checkpointer, DB, Redis).
2. Compose `stop_grace_period: 90s` on the api service (dev + prod): the
   docker default 10 s would SIGKILL mid-drain.
3. Logs: `chat_producers_drain_started/finished`,
   `chat_producers_drain_incomplete` (pending > 0 → those runs end
   `killed`).

## Settings

| Env var | Default | Notes |
|---|---|---|
| `BACKGROUND_RUNS_ENABLED` | `false` | Master switch / instant rollback |
| `BACKGROUND_RUNS_STREAM_MAXLEN` | `10000` | ~122 KB per 1000 token chunks (measured) |
| `BACKGROUND_RUNS_STREAM_TTL_SECONDS` | `3600` | Bounds Redis memory; must cover the Lot 2 reattach window |
| `BACKGROUND_RUNS_XREAD_BLOCK_MS` | `2000` | **Must stay well below `REDIS_SOCKET_TIMEOUT`×1000** — redis-py raises `TimeoutError` past it (POC-proven). Also the SSE keepalive cadence |
| `BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS` | `45` | Drain + generic-task timeout must stay below `stop_grace_period` (90 s) with margin |
| `SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS` | `15` | Generic fire-and-forget drain (memory/interest extraction…) |

## Observability

- `chat_background_producers_active` (Gauge, per worker)
- `chat_background_runs_total{status="completed|error|killed"}` (Counter)
- Events: `chat_run_producer_started/completed/error/killed`,
  `run_stream_end_published`, `archive_first_user_message_failed`,
  `hitl_user_response_flag_patched`, `hitl_interrupted_flag_patched`.
- Redis inspection: `redis-cli --scan --pattern 'chat:run:*'`, `XLEN`,
  `XRANGE <key> - +`, `TTL`.

## Lot 2 — Live reattachment, concurrency lock, listener-gated voice

Delivered 2026-07-09 (same ADR). Everything below is flag-gated by the same
`BACKGROUND_RUNS_ENABLED`.

- **Active-run lock**: `chat:active_run:{conversation_id}` (SET NX EX
  `BACKGROUND_RUNS_ACTIVE_TTL_SECONDS`), value `{run_id, stream_id}`.
  Acquired by the POST endpoint BEFORE the SSE response starts (a second
  concurrent POST answers **HTTP 409** with the active run info); kept
  alive by a producer heartbeat (`BACKGROUND_RUNS_HEARTBEAT_SECONDS`,
  conditional-refresh Lua so a zombie can never touch a newer run's lock);
  released on every producer exit path. A killed producer frees the
  conversation in at most the lock TTL (POC-L2-1).
- **Reattach endpoints**: `GET /agents/runs/active` (is a run in flight?)
  and `GET /agents/runs/{stream_id}/stream` (full replay + live tail;
  ownership = the CURRENT active run of the caller's conversation, 404
  hide-existence otherwise — finished runs are reloaded via history).
- **Replay semantics**: the broker snapshots the stream tail at subscribe
  time; backlog entries are flagged `is_replay` → relayed without pacing,
  `voice_audio_chunk` payloads dropped server-side (stale audio), and the
  transport comment ``: replay-end`` marks the replay→live boundary
  (legacy SSE parsers ignore it; the chunk contract is untouched).
- **Frontend auto-resume** (product decision): at chat-page mount and on
  visibility return, `useChat.checkAndResumeActiveRun()` silently
  reattaches; the backlog replays through the normal handler pipeline with
  `SSEHandlerContext.isReplay = true` (reducer state rebuilds; toasts and
  voice playback suppressed until `: replay-end`). A 409 on send triggers
  the same resume (toast `chat.resume.in_progress`).
- **Listener-gated voice**: subscribers INCR/DECR
  `chat:listeners:{stream_id}` around their read AND re-arm the counter TTL
  every ~TTL/3 while attached (without the periodic touch, a subscriber
  attached longer than `BACKGROUND_RUNS_LISTENER_TTL_SECONDS` would silently
  drop out of the count and voice would be wrongly skipped mid-run —
  regression-guarded by `test_presence_ttl_survives_long_attachment`).
  Every voice-synthesis start point in the service consults the injected
  `has_listeners` probe — with nobody attached, TTS is skipped
  (`voice_skipped_no_listeners`); a listener attaching MID-run makes voice
  start for the remaining content. Fail-open on probe errors; paths without
  presence tracking (legacy, scheduled actions, channels) are unchanged.
  Boot-time guard: `BACKGROUND_RUNS_HEARTBEAT_SECONDS` must stay ≤
  `BACKGROUND_RUNS_ACTIVE_TTL_SECONDS / 2` (the app refuses to boot with a
  lock that would flap between heartbeats).

## Lot 3 — User cancellation (stop button)

Delivered 2026-07-09 (same ADR, same flag).

- **Signal path**: `POST /agents/runs/active/cancel` resolves the caller's
  own active run server-side (no stream id needed, ownership trivial) and
  sets `chat:cancel:{stream_id}` (TTL
  `BACKGROUND_RUNS_CANCEL_TTL_SECONDS`). A watcher task next to the
  producer polls it every `BACKGROUND_RUNS_CANCEL_POLL_SECONDS` (stop
  latency ≈ that period) and cancels the producer cooperatively — the
  signal may be set from ANY worker, the asyncio cancel stays local.
- **Terminal semantics**: status `cancelled` (distinct from `killed` in
  metrics and archive metadata); the producer synthesizes a standard
  `done` chunk with `metadata.cancelled` so subscribers close their normal
  SSE lifecycle and badge the partial bubble; the partial content is
  archived flagged `{interrupted, interrupt_reason: "cancelled"}`; already
  billed tokens stay billed (E2E-proven: 1348/748 tokens persisted for a
  cancelled run). **Cancellation is not a rollback** — tools that already
  ran have acted; it stops what remains.
- **Frontend**: the send button morphs into a stop button while streaming
  (`isGenerating` + `onStopGeneration` on ChatInput). Flag ON, the server
  cancels the detached run; with no detached run (flag OFF), the client
  falls back to the legacy local abort — pre-ADR-117 behavior. The
  `interrupted` badge renders on both live bubbles (synthesized done) and
  reloaded history rows (same metadata flag).
- **Checkpoint sanitation** (the POC-3 poisoning): a cancelled/killed run
  can leave an `AIMessage` with UNANSWERED `tool_calls` in the LangGraph
  checkpoint, which strict providers reject on the next turn.
  `sanitize_stale_dangling_tool_calls` repairs it AT TURN START in
  router_node (same-id replacement / RemoveMessage through the messages
  reducer) — never in the reducer itself, where dangling tool_calls are a
  legitimate mid-run state. HITL resumptions resume the interrupted node
  via `Command(resume)` and never re-enter the router: pending approvals
  are unaffected.

## Known limits (by design)

- **First-ever message edge**: when no conversation exists yet at POST
  time, there is no lock (and no partial finalizer) for that first run —
  it is created during the run; subsequent messages are fully covered.
- **409 optimistic bubble**: the rejected message's optimistic bubble stays
  visible until the next history reload reconciles it (rare multi-tab
  race; the input lock and auto-resume make it hard to hit).
- **A started TTS is not cut** when the last listener detaches mid-run —
  only the START of synthesis is gated.

## Rollback

Set `BACKGROUND_RUNS_ENABLED=false` and **recreate** the api service. The
legacy inline path is byte-identical to pre-ADR-117 behavior (it will be
removed in a follow-up release once the flag is proven in production).

⚠️ `docker restart` does NOT re-read compose `env_file` values — they are
baked into the container at creation. To toggle the flag, recreate the
container: `docker compose -f docker-compose.<env>.yml up -d api`
(verified during the 2026-07 E2E gate: a restart after editing `.env` left
the old value active).

Known dev-environment caveat (pre-existing, NOT caused by this feature):
the dev container runs uvicorn with `--reload`, whose reloader process
never executes the lifespan shutdown on SIGTERM — `application_shutdown`
has never been logged in dev and `docker stop` ends in SIGKILL after the
grace period. The shutdown drain is therefore only exercised on the prod
topology (exec-form uvicorn, no reload — where the de-risking POC proved
it: 30/30 chunks survive worker recycling with the drain vs 1/30 without).
