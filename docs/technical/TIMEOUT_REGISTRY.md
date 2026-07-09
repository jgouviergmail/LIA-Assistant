# Timeout Registry

Single source of truth for every timeout configurable in LIA (excluding LLM
timeouts which are governed via the `llm_config` table and the Configuration
LLM admin UI).

## Conventions

- **Constant** (in `apps/api/src/core/constants.py`): `<DOMAIN>_<USAGE>_TIMEOUT_<UNIT>_DEFAULT`
  (e.g. `BROWSER_TOOL_TIMEOUT_SECONDS_DEFAULT`). The `_DEFAULT` suffix marks
  values that are configurable defaults — pure invariant constants do not
  carry the suffix. Pre-existing constants (e.g. `HTTP_TIMEOUT_OAUTH`) keep
  their historical name to avoid churn.
- **Pydantic Field** (in `apps/api/src/core/config/<module>.py`): snake_case
  without the `_DEFAULT` suffix (e.g. `browser_tool_timeout_seconds`).
- **Environment variable** (in `.env.example` / `.env.prod.example`):
  SCREAMING_SNAKE without the `_DEFAULT` suffix
  (e.g. `BROWSER_TOOL_TIMEOUT_SECONDS`).
- **Range guidance**: every Pydantic Field that holds a timeout SHOULD declare
  `ge` / `le` bounds. The lower bound prevents pathological values
  (e.g. 0 ms); the upper bound prevents a single misconfiguration from
  silently consuming a worker for hours.
- **Description guidance**: every `Field()` description SHOULD answer two
  questions: *"what does this timeout protect against?"* and *"what symptom
  appears if it is too short / too long?"*.

## Layers (top-down request flow)

```
Cloudflare tunnel → Nginx → FastAPI → LangGraph run → Node → Tool → HTTP outbound → DB / Redis / MCP
```

A child timeout SHOULD always be strictly less than its parent. Cascade
inversions are tracked in section *Known conflicts* below.

## Index

1. [HTTP outbound — external APIs](#1-http-outbound--external-apis)
2. [HTTP outbound — connector platform layer](#2-http-outbound--connector-platform-layer)
3. [HTTP outbound — internal infrastructure](#3-http-outbound--internal-infrastructure)
4. [Tool execution — orchestration](#4-tool-execution--orchestration)
5. [Sub-agent / browser / MCP delegated runs](#5-sub-agent--browser--mcp-delegated-runs)
6. [Graph / Node level](#6-graph--node-level)
7. [Database / Cache](#7-database--cache)
8. [SSE / WebSocket / streaming](#8-sse--websocket--streaming)
9. [Scheduler / background jobs](#9-scheduler--background-jobs)
10. [Locks / concurrency](#10-locks--concurrency)
11. [Lifecycle (startup / shutdown)](#11-lifecycle-startup--shutdown)
12. [LLM-related (out-of-scope)](#12-llm-related-out-of-scope)

---

## 1. HTTP outbound — external APIs

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `HTTP_TIMEOUT_OAUTH` | `http_timeout_oauth` | 10.0 s | 1.0–60.0 | `base_oauth_client.py` | OAuth authorization redirects |
| `HTTP_TIMEOUT_TOKEN` | `http_timeout_token` | 5.0 s | 1.0–60.0 | `base_oauth_client.py` | Token exchange endpoint |
| `HTTP_TIMEOUT_EXTERNAL_API` | `http_timeout_external_api` | 5.0 s | 1.0–60.0 | OAuth fallback | Generic external HTTP fallback |
| `HTTP_TIMEOUT_ROUTES_API` | `http_timeout_routes_api` | 30.0 s | 1.0–60.0 | `google_routes_client.py` | Connect splitted: `connect=10.0` |
| `HTTP_TIMEOUT_PLACES_API` | `http_timeout_places_api` | 10.0 s | 1.0–60.0 | `google_places_client.py` | |
| `HTTP_TIMEOUT_GEOCODING_API` | `http_timeout_geocoding_api` | 5.0 s | 1.0–60.0 | `google_geocoding.py` | |
| `HTTP_TIMEOUT_PERPLEXITY` | `http_timeout_perplexity` | 60.0 s | 1.0–180.0 | `web_search_tools.py` | High because deep-search queries are slow |
| `HTTP_TIMEOUT_WEATHER` | `http_timeout_weather` | 10.0 s | 1.0–60.0 | `weather_tools.py` | OpenWeatherMap |
| `HTTP_TIMEOUT_WIKIPEDIA` | `http_timeout_wikipedia` | 15.0 s | 1.0–60.0 | `wikipedia_tools.py` | |
| `HTTP_TIMEOUT_BRAVE_SEARCH` | `http_timeout_brave_search` | 5.0 s | 1.0–60.0 | brave search service | Per single HTTP request |
| `BRAVE_SEARCH_ENRICHMENT_TIMEOUT_SECONDS` | `brave_search_enrichment_timeout_seconds` | 8.0 s | 2.0–60.0 | brave enrichment service | Job-level wrapper. **Was 3.0s — raised to fix cascade inversion (see G2)**. |
| `CURRENCY_API_TIMEOUT_SECONDS` | `currency_api_timeout_seconds` | 5.0 s | 1.0–60.0 | `currency_api.py` | Replaces deprecated `http_timeout_currency_api` (see G1) |
| `HUE_BRIDGE_TIMEOUT_SECONDS` | `hue_bridge_timeout_seconds` | 10.0 s | 1.0–60.0 | `philips_hue_client.py` | Hue Bridge HTTP API |
| `HUE_PAIRING_TIMEOUT_SECONDS` | `hue_pairing_timeout_seconds` | 30.0 s | 5.0–120.0 | `philips_hue_client.py` | Pairing handshake (long-poll) |
| `OLLAMA_DISCOVERY_TIMEOUT_SECONDS` | `ollama_discovery_timeout_seconds` | 5.0 s | 1.0–60.0 | `ollama_discovery.py` | `/api/tags` + `/api/show` |
| `WEB_FETCH_TIMEOUT_SECONDS` | `web_fetch_timeout_seconds` | 15.0 s | 1.0–120.0 | `web_fetch_tools.py` | Single fetch (readability extraction) |
| `APPLE_CONNECTION_TIMEOUT` | `apple_connection_timeout` | 30.0 s | 1.0–120.0 | apple connector | |

## 2. HTTP outbound — connector platform layer

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `HTTP_TIMEOUT_CONNECTOR_STANDARD` | `http_timeout_connector_standard` | 15.0 s | 1.0–120.0 | `connectors/router.py` (×4) | Standard read paths |
| `HTTP_TIMEOUT_CONNECTOR_LONG` | `http_timeout_connector_long` | 30.0 s | 1.0–300.0 | `connectors/router.py`, `base_api_key_client.py` | Bulk / attachments |

## 3. HTTP outbound — internal infrastructure

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `HTTP_TIMEOUT_CONDITIONAL_EVAL` | `http_timeout_conditional_eval` | 5.0 s | 1.0–30.0 | `parallel_executor.py:1727` | Jinja conditional evaluation |
| `HTTP_TIMEOUT_SSE_POLLING` | `http_timeout_sse_polling` | 30.0 s | 5.0–120.0 | `notifications/router.py:271` | SSE long-polling |
| `MCP_OAUTH_HTTP_TIMEOUT_SECONDS` | `mcp_oauth_http_timeout_seconds` | 10 s | 1–60 | `mcp/auth.py`, `mcp/oauth_flow.py` (×3) | OAuth discovery + token exchange |

## 4. Tool execution — orchestration

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `DEFAULT_TOOL_TIMEOUT_SECONDS` | `default_tool_timeout_seconds` | 30.0 s | 5.0–300.0 | `parallel_executor.py:1627` | Floor for generic tools |
| `MAX_TOOL_TIMEOUT_SECONDS` | `max_tool_timeout_seconds` | 120.0 s | 30.0–600.0 | `parallel_executor.py:1638` | Hard ceiling for generic tools |
| `DEFAULT_TOOL_TIMEOUT_MS` | `default_tool_timeout_ms` | 30000 ms | 5000–300000 | catalogue manifests | Per-tool default in catalogue |
| `BROWSER_TOOL_TIMEOUT_SECONDS` | `browser_tool_timeout_seconds` | 300.0 s | 30.0–900.0 | `parallel_executor.py:1625` | Floor for `browser_task_tool` |
| `MAX_BROWSER_TOOL_TIMEOUT_SECONDS` | `max_browser_tool_timeout_seconds` | 600.0 s | 60.0–1800.0 | `parallel_executor.py:1634` | Hard ceiling for `browser_task_tool` |
| `BROWSER_DEFAULT_TIMEOUT_MS` | `browser_default_timeout_ms` | 120000 ms | 30000–600000 | `catalogue_loader.py:417` | Catalogue default for browser steps |
| `IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS` | `image_generation_tool_timeout_seconds` | 90.0 s | 10.0–600.0 | `parallel_executor.py:1609` | Was inline magic number `90.0` |
| `DEVOPS_CLAUDE_TOOL_TIMEOUT_SECONDS` | `devops_claude_tool_timeout_seconds` | 120.0 s | 30.0–900.0 | `parallel_executor.py:1610` | Was inline magic number `120.0` (`claude_server_task_tool`) |
| `MCP_REACT_STEP_TIMEOUT_SECONDS` | `mcp_react_step_timeout_seconds` | 300 s | 30–900 | `parallel_executor.py` + `smart_planner_service.py` | Floor for MCP iterative `*_task` steps (ReAct sub-agent loop). Raised 120→300 (ADR-100/D1): one diagram-generation LLM call alone ≈ 105 s. |
| `MCP_REACT_STEP_MAX_TIMEOUT_SECONDS` | `mcp_react_step_max_timeout_seconds` | 600 s | 60–900 | `parallel_executor.py` | Hard ceiling for MCP iterative `*_task` steps — dedicated family so the generic 120 s ceiling no longer kills legitimate multi-iteration work (ADR-100/D1). |

## 5. Sub-agent / browser / MCP delegated runs

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `SUBAGENT_TOOL_TIMEOUT_SECONDS` | `subagent_tool_timeout_seconds` | 180.0 s | 30.0–600.0 | `parallel_executor.py:1607` | Sub-agent step floor |
| `SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS` | `subagent_tool_max_timeout_seconds` | 300.0 s | 60.0–900.0 | `parallel_executor.py:1635` | Sub-agent step ceiling |
| `MCP_TOOL_TIMEOUT_SECONDS` | `mcp_tool_timeout_seconds` | 120 s | 5–120 | mcp client | Per MCP tool call |
| `REACT_AGENT_TIMEOUT_SECONDS` | `react_agent_timeout_seconds` | 120 s | 10–600 | `routing.py:724` | ReAct loop hard wall-clock guard |

## 6. Graph / Node level

LLM-call timeouts (router, planner, response, semantic validator, …) are
managed in the `llm_config` table and the Admin > Configuration LLM UI.
They are NOT listed here. See section 12.

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `TASK_ORCHESTRATOR_EXECUTION_TIMEOUT_SECONDS` | `task_orchestrator_execution_timeout_seconds` | 600.0 s | 30.0–1800.0 | `parallel_executor.py` (wave executor) | Wired in Vague 5. Soft plan-wide budget. Raised 120→600 (ADR-100/D1) so it dominates the longest per-step family ceilings (MCP react / browser / sub-agent up to 600 s). |
| `HITL_MAX_WAIT_SECONDS` | `hitl_max_wait_seconds` | 900 s | 60–3600 | (orphan — see Vague 5 decision section) | Max HITL response wait |
| `CONTEXT_RESOLUTION_TIMEOUT_MS` | `context_resolution_timeout_ms` | 500 ms | 50–10000 | `analysis/memory_resolver.py` | |
| `MEMORY_REFERENCE_RESOLUTION_TIMEOUT_MS` | `memory_reference_resolution_timeout_ms` | 5000 ms | 100–30000 | `memory_reference_resolution_service.py` | |
| `PLAN_PATTERN_SUGGESTION_TIMEOUT_MS` | `plan_pattern_suggestion_timeout_ms` | 100 ms | 10–5000 | `plan_pattern_learner.py` | Redis lookup, fail-open |
| `SEMANTIC_VALIDATION_TIMEOUT_SECONDS` | `semantic_validation_timeout_seconds` | 20.0 s | 0.5–30.0 | `orchestration/semantic_validator.py` | |
| `HEALTH_METRICS_HEARTBEAT_FETCH_TIMEOUT_SECONDS` | `health_metrics_heartbeat_fetch_timeout_seconds` | 2.0 s | 0.5–30.0 | `heartbeat/context_aggregator.py:1029` | Safety wrapper |

## 7. Database / Cache

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `DATABASE_POOL_TIMEOUT` | `database_pool_timeout` | 30 s | 1–300 | sqlalchemy session | Pool acquire timeout |
| `REDIS_SOCKET_TIMEOUT` | `redis_socket_timeout` | 30 s | 1–300 | redis client | Idle close |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `redis_socket_connect_timeout` | 5 s | 1–60 | redis client | Connect handshake |
| `CIRCUIT_BREAKER_TIMEOUT_SECONDS` | `circuit_breaker_timeout_seconds` | 10 s | 1–600 | `resilience/circuit_breaker.py` | Time before half-open retry |

## 8. SSE / WebSocket / streaming

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `SSE_HEARTBEAT_INTERVAL` | `sse_heartbeat_interval` | 15 s | 5–120 | `agents/api/router.py` | Backend → frontend heartbeat |
| `VOICE_WS_IDLE_TIMEOUT_SECONDS` | `voice_ws_idle_timeout_seconds` | 120 s | 30–600 | `voice/router.py` | STT WebSocket idle close |
| `VOICE_PARALLEL_TIMEOUT_SECONDS` | `voice_parallel_timeout_seconds` | 15.0 s | 1.0–120.0 | `voice/sentence_streamer.py` | Per parallel TTS chunk |
| `USAGE_LIMIT_WS_IDLE_TIMEOUT_SECONDS` | `usage_limit_ws_idle_timeout_seconds` | 120 s | 30–600 | `usage_limits/websocket.py:163` | Usage limit live-stream WS idle close |
| `BACKGROUND_RUNS_XREAD_BLOCK_MS` | `background_runs_xread_block_ms` | 2000 ms | 250–15000 | `infrastructure/streaming/run_stream_broker.py` | XREAD BLOCK window for run-stream subscribers (ADR-117). MUST stay well below `REDIS_SOCKET_TIMEOUT`×1000 — redis-py raises `TimeoutError` past it (POC-proven). Doubles as the subscriber keepalive cadence |
| `BACKGROUND_RUNS_STREAM_TTL_SECONDS` | `background_runs_stream_ttl_seconds` | 3600 s | 60–86400 | `infrastructure/streaming/run_stream_broker.py` | EXPIRE armed on the run stream at the terminal marker; must exceed the longest window during which a reload may still replay the run |
| `BACKGROUND_RUNS_LISTENER_TTL_SECONDS` | `background_runs_listener_ttl_seconds` | 30 s | 5–300 | `infrastructure/streaming/run_stream_broker.py` | TTL of the subscriber-presence counter gating voice synthesis; re-armed on INCR/DECR and touched ~TTL/3 by attached subscribers |
| `BACKGROUND_RUNS_CANCEL_POLL_SECONDS` | `background_runs_cancel_poll_seconds` | 1 s | 1–10 | `agents/api/background_runner.py` | Producer-side poll of the cancel signal — bounds the stop-button latency |
| `BACKGROUND_RUNS_CANCEL_TTL_SECONDS` | `background_runs_cancel_ttl_seconds` | 600 s | 30–3600 | `infrastructure/streaming/run_stream_broker.py` | Self-cleaning TTL of the cancel-signal key (producer already gone → nothing to cancel) |

## 9. Scheduler / background jobs

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS` | `scheduled_actions_execution_timeout_seconds` | 300 s | 30–1800 | `scheduled_action_executor.py:222` | Per-action wall-clock |
| `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` | `scheduled_actions_stale_timeout_minutes` | 10 min | 1–120 | `scheduled_action_executor.py:402` | Recovery threshold for stuck `executing` rows |
| `DEVOPS_SSH_TIMEOUT` | `devops_ssh_timeout` | 30 s | 5–300 | `devops_ssh_service.py` | SSH connect timeout |
| `DEVOPS_COMMAND_TIMEOUT` | `devops_command_timeout` | 300 s | 30–1800 | `devops_ssh_service.py` | Remote command exec timeout |
| `SKILLS_SCRIPT_TIMEOUT_SECONDS` | `skills_script_timeout_seconds` | 30 s | 5–120 | `skills/runner` | Skill script exec |

## 10. Locks / concurrency

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `OAUTH_LOCK_TIMEOUT_SECONDS` | `oauth_lock_timeout_seconds` | 10 s | 1–120 | `infrastructure/locks/oauth_lock.py` | Distributed lock acquisition |
| `BACKGROUND_RUNS_ACTIVE_TTL_SECONDS` | `background_runs_active_ttl_seconds` | 15 s | 5–120 | `infrastructure/streaming/run_stream_broker.py` | TTL of the per-conversation active-run lock (ADR-117 Lot 2); a killed producer frees the conversation in at most this many seconds |
| `BACKGROUND_RUNS_HEARTBEAT_SECONDS` | `background_runs_heartbeat_seconds` | 5 s | 1–60 | `agents/api/background_runner.py` | Producer heartbeat refreshing the active-run lock; boot-time validator enforces `heartbeat <= active_ttl / 2` (a single missed beat must not expire a healthy run's lock) |

## 11. Lifecycle (startup / shutdown)

| Env var | Field | Default | Range | Used in | Notes |
| --- | --- | --- | --- | --- | --- |
| `BACKGROUND_RUNS_DRAIN_TIMEOUT_SECONDS` | `background_runs_drain_timeout_seconds` | 45 s | 5–300 | `main.py` lifespan / `agents/api/background_runner.py` | Max wait for in-flight chat producers on shutdown (ADR-117). Drain + generic-task timeouts must stay below the compose `stop_grace_period` (90 s) |
| `SHUTDOWN_BACKGROUND_TASKS_TIMEOUT_SECONDS` | `shutdown_background_tasks_timeout_seconds` | 15 s | 1–120 | `main.py` lifespan / `infrastructure/async_utils.py` | Max wait for generic fire-and-forget tasks (memory/interest extraction, warmups) after chat producers are drained |

> *Remaining candidates flagged in audit V3 — Vague 6: PostgreSQL*
> *`statement_timeout`, FastAPI lifespan startup wrap, MCP `session.close()`*
> *shutdown wrap, sub-agent / browser / MCP ReAct loop temporal guards.*

## Annex A — LLM-related (out-of-scope)

These timeouts are managed via the `llm_config` table (database) and exposed
in the Admin > Configuration LLM UI. **Do not migrate these to environment
variables**: per-LLM-type tuning (router vs planner vs response vs query
analyzer …) requires per-row granularity that env vars cannot offer.

| Constant | Default | Owner |
| --- | --- | --- |
| `ROUTER_LLM_TIMEOUT_SECONDS_DEFAULT` | 30.0 s | llm_config row `router` |
| `RESPONSE_LLM_TIMEOUT_SECONDS_DEFAULT` | 60.0 s | llm_config rows `response_*` |
| `PLANNER_TIMEOUT_SECONDS` | 30 s | llm_config row `planner` |
| `INITIATIVE_LLM_TIMEOUT_SECONDS` | 30 s | llm_config row `initiative` |
| `MEMORY_REFERENCE_EXTRACTION_TIMEOUT_SECONDS` | 30 s | llm_config row `memory_reference` |
| `query_analyzer_llm_timeout_seconds` | (Field in llm.py) | llm_config row `query_analyzer` |
| All `timeout_seconds` rows in `llm_config/constants.py` | 20–180 s | `llm_config` BDD |

The applicative `asyncio.wait_for` wrapper around every node still reads
from `agents.py` Settings — those values cap the LLM call regardless of the
SDK timeout. Reconciliation between the two layers is a separate task (audit
V3 — section 9 recap).

## Annex B — Frontend-side timeouts

The frontend has its own timing constants in `apps/web/src/constants/timing.ts`.
They are **not part of the backend `Settings` surface** but are mirrored here
so operators have a single map of every wall-clock budget at any layer of the
stack.

| Constant | Default | Module / role |
| --- | --- | --- |
| `REFRESH_INTERVALS.USER_STATISTICS` | 30 000 ms | Polling cadence for the user-stats card |
| `REFRESH_INTERVALS.CHAT_RECONNECT` | 5 000 ms | Backoff between chat-stream reconnect attempts |
| `REFRESH_INTERVALS.HEARTBEAT` | 15 000 ms | SSE keepalive (must match backend) |
| `REFRESH_INTERVALS.CONVERSATIONS` | 60 000 ms | Conversation-list polling fallback |
| `TIMEOUTS.OAUTH_REDIRECT` | 3 000 ms | UX delay after successful OAuth |
| `TIMEOUTS.API_REQUEST` | 30 000 ms | `fetch` per-request abort budget — paired with backend `DEFAULT_TOOL_TIMEOUT_MS` |
| `TIMEOUTS.SSE_RECONNECT` | 5 000 ms | Delay before reconnecting a dropped SSE stream |
| `TIMEOUTS.TOOL_APPROVAL` | 300 000 ms | Inactivity timer on the HITL approval modal |
| `TIMEOUTS.SEARCH_DEBOUNCE` | 300 ms | Per-keystroke debounce on search inputs |
| `SSE_CONFIG.RETRY_INTERVAL` | 5 000 ms | EventSource `retry` field |
| `SSE_CONFIG.MAX_RETRIES` | 3 | Reconnect cap before surfacing an error |
| `SSE_CONFIG.HEARTBEAT_INTERVAL` | 15 000 ms | Must match backend `SSE_HEARTBEAT_INTERVAL` |
| `DURATIONS.TOAST` | 5 000 ms | Toast auto-dismiss |
| `DURATIONS.MIN_LOADING` | 200 ms | Anti-flash floor on loading indicators |
| `DURATIONS.MODAL_TRANSITION` | 150 ms | Modal open/close transition |

Cross-stack pairs to keep in sync when tuning either side:
- Backend `HTTP_TIMEOUT_SSE_POLLING` (30 s) ↔ frontend `SSE_CONFIG.HEARTBEAT_INTERVAL` (15 s)
  — backend MUST send the keepalive at least twice per client retry window.
- Backend `DEFAULT_TOOL_TIMEOUT_MS` (30 000) ↔ frontend `TIMEOUTS.API_REQUEST` (30 000)
  — frontend should match or slightly exceed the backend tool floor.
- Backend `hitl_max_wait_seconds` (900) ↔ frontend `TIMEOUTS.TOOL_APPROVAL` (300 000 = 300 s)
  — currently mismatched (frontend = 5 min, backend orphan = 15 min); see *Pending decisions*.

## Annex C — Known gaps deferred to a future Vague 6

The following timeouts are known to exist (or be missing) but were
intentionally left untouched by Vagues 1–5 because they require either a
schema migration, cross-layer coordination, or a product decision. Tracking
them here so the next wave can pick them up explicitly.

| # | Gap | Where it lives | Why deferred |
|---|-----|----------------|--------------|
| C1 | `postgres_statement_timeout` | PostgreSQL session-level setting (asyncpg `server_settings`) | Requires a connection-string change + per-pool tuning; out of `.env` scope today. |
| C2 | `app_startup_timeout_seconds` / `app_shutdown_timeout_seconds` | `main.py` lifespan context | No clean Pydantic surface yet; needs a small `LifecycleSettings` module. |
| C3 | `mcp_session_close_timeout_seconds` | `infrastructure/mcp/client_pool.py` | Currently inlined; ADR-079 follow-up. |
| C4 | Sub-agent / browser / MCP nested-ReAct temporal guards | `subagent_runner.py`, `browser_react_loop.py`, `mcp_react_loop.py` | Inner-loop wall-clock caps (per-iteration) distinct from the outer step timeout. Warrants a dedicated nested-ReAct timeout family. |
| C5 | Frontend chat SSE watchdog | `apps/web/src/hooks/useChatStream.ts` | A long-running SSE without a server keepalive currently waits indefinitely. Needs a client-side dead-stream detector tied to `SSE_CONFIG.HEARTBEAT_INTERVAL`. |
| C6 | APScheduler per-job timeout | `infrastructure/scheduler/registry.py` | APScheduler natively supports `misfire_grace_time` but not a per-job hard timeout. Workaround would wrap the job callable in `asyncio.wait_for`. |
| ~~C7~~ | ~~`parallel_execution_global_timeout_total{plan_outcome}` regression test~~ | `tests/unit/domains/agents/orchestration/test_parallel_executor_global_timeout.py` | **Resolved in v1.20.6**: 2 unit tests (`test_global_timeout_fires_immediately_with_zero_budget`, `test_global_timeout_does_not_fire_with_generous_budget`) cover both increment and no-false-positive paths. |

## Known conflicts

### G1 — Currency API duplicate (resolved in Vague 4)

Two Settings fields used to point at the same constant:

- `http_timeout_currency_api` (`connectors.py`) — never read.
- `currency_api_timeout_seconds` (`advanced.py`) — actually used in
  `currency_api.py:65`.

`http_timeout_currency_api` and the env line `HTTP_TIMEOUT_CURRENCY_API` were
removed in Vague 4. Operators MUST use `CURRENCY_API_TIMEOUT_SECONDS`.

### G2 — Brave search cascade inversion (resolved in Vague 1)

The job-level wrapper `BRAVE_SEARCH_ENRICHMENT_TIMEOUT` (3.0 s) used to fire
**before** the per-request HTTP timeout `HTTP_TIMEOUT_BRAVE_SEARCH` (5.0 s),
so the HTTP-level value was mathematically unreachable. The job-level
default was raised to **8.0 s** (`> HTTP * 1.5`) and made tunable via
`BRAVE_SEARCH_ENRICHMENT_TIMEOUT_SECONDS`. Both env vars MUST stay in the
relation `enrichment_timeout >= http_timeout * 1.5`; operators changing
either one should verify the relation.

### G3 — `MCP_DEFAULT_TIMEOUT_SECONDS` overload

The constant `MCP_DEFAULT_TIMEOUT_SECONDS` is used both as the default for
the global Pydantic Field `mcp_tool_timeout_seconds` AND as the default for
the per-server DB column `user_mcp.timeout_seconds`. Not a duplicate, but
the dual usage is documented inline in `constants.py` to avoid future
confusion.

### G4 — Context resolution vs memory reference (latent)

`context_resolution_timeout_ms` (500 ms) is 10× shorter than
`memory_reference_resolution_timeout_ms` (5000 ms). If both are in the same
call chain, the parent will fire first. Documented for awareness; not
breaking today (the call paths are independent).

## Wave-by-wave changelog

### Vague 1 — HTTP external timeouts migration

Migrated to `Settings` + `.env`:

- `http_timeout_perplexity`, `http_timeout_weather`, `http_timeout_wikipedia`,
  `http_timeout_brave_search`, `brave_search_enrichment_timeout_seconds`,
  `ollama_discovery_timeout_seconds`, `web_fetch_timeout_seconds`.

Bug fix: G2 (Brave cascade inversion) — enrichment timeout raised from 3.0 s
to 8.0 s. Behavior change is intentional but conservative (operators losing
hits at 3.0 s today will see them succeed; nothing slower than 8.0 s gets
through where it didn't before).

### Vague 2 — Connectors / locks / SSE / scheduler

Migrated:

- `http_timeout_connector_standard`, `http_timeout_connector_long`,
  `http_timeout_conditional_eval`, `http_timeout_sse_polling`,
  `oauth_lock_timeout_seconds`, `mcp_oauth_http_timeout_seconds`,
  `hue_pairing_timeout_seconds`, `usage_limit_ws_idle_timeout_seconds`,
  `health_metrics_heartbeat_fetch_timeout_seconds`,
  `scheduled_actions_execution_timeout_seconds`,
  `scheduled_actions_stale_timeout_minutes`.

New Pydantic modules introduced: `LocksSettings` (`config/locks.py`),
`SchedulerSettings` (`config/scheduler.py`). Both registered in the Settings
MRO.

### Vague 3 — Tools

Migrated: `default_tool_timeout_seconds`, `max_tool_timeout_seconds`,
`default_tool_timeout_ms`, `browser_tool_timeout_seconds`,
`max_browser_tool_timeout_seconds`, `browser_default_timeout_ms`.

Magic numbers extracted: `image_generation_tool_timeout_seconds` (was inline
`90.0` at `parallel_executor.py:1609`), `devops_claude_tool_timeout_seconds`
(was inline `120.0` at `parallel_executor.py:1610`).

### Vague 4 — Hygiene

Removed dead code: `HTTP_TIMEOUT_PROMPT_REGISTRY`,
`BACKGROUND_TASK_TIMEOUT_DEFAULT`.

Resolved G1: removed `http_timeout_currency_api` Field +
`HTTP_TIMEOUT_CURRENCY_API` env line; the surviving setting is
`currency_api_timeout_seconds` / `CURRENCY_API_TIMEOUT_SECONDS`.

### Vague 5 — Orphan wiring

Wired `task_orchestrator_execution_timeout_seconds` as a
wall-clock cap around the wave gather in `parallel_executor.py`.
Behavior change: multi-step plans now abort cleanly past the configured
budget instead of running forever. Default value (120 s) unchanged from
prior — the field was previously inert.

`hitl_max_wait_seconds` decision: see *Pending decisions* below.

## Pending decisions

- **HITL max wait** — `hitl_max_wait_seconds` (900 s) is declared in
  Settings + `.env.*` but never read in runtime. Two options:
  - **(a) Wire** as a hard cap on HITL pending state: a HITL session left
    pending past `hitl_max_wait_seconds` is auto-cancelled (state moved
    back to a graceful "abandoned" terminal). Preserves resources, predictable
    UX. Requires touching the HITL resumption flow (`hitl/resumption_strategies`)
    plus a probable migration to persist the deadline.
  - **(b) Remove** if the product position is "HITL stays pending until the
    user acts, no auto-timeout". Then drop the Field, the constant, the
    env lines, and document the decision.
  Wiring is non-trivial; until a decision is taken, the orphan stays. See
  audit V3 for context.
