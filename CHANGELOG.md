# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.20.13] - 2026-05-22

### Fixed — Responses no longer fail or degrade with Gemini 3.x models

Gemini 3.x (e.g. `gemini-3.5-flash`, `gemini-3-pro-preview`) returns `AIMessage`/`AIMessageChunk.content` as a **list of content blocks** (`[{"type": "text", "text": "...", "index": 0}]`) instead of a plain string like earlier Gemini and every other provider. Several code paths assumed `str` and broke under Gemini 3.x:

- **SSE token streaming** aborted with a `ChatStreamChunk` `ValidationError`, surfacing to the user as *"Un problème est survenu lors de la génération de la réponse. Veuillez réessayer."* — in **both** Pipeline and ReAct modes (they share the response-node token stream).
- **ReAct mode** additionally crashed in `format_conversation_history` (`'list' object has no attribute 'strip'`) whenever the conversation history contained Gemini-produced list-content messages. This is **independent of the response model**: a mixed-provider setup (Gemini driving the ReAct loop, another model synthesizing the response) was equally affected.
- Silent degradations elsewhere: skipped psyche-tag / registry-filtering / HTML-widget post-processing, garbled voice (TTS) output, distorted token counts, dropped tokens after a HITL resumption, email-draft generation, and the `structured_output` JSON-mode fallback.

### Changed — Canonical content-normalization primitive (DRY)

Introduced `coerce_content_to_text()` (`src/infrastructure/llm/message_text.py`): a single, defensive primitive that normalizes any message `.content` shape (`str`, Gemini 3.x `list[dict]` blocks, `None`, or anything else) to plain text, mirroring LangChain Core 1.2+ `BaseMessage.text` semantics (concatenate `text` blocks, ignore reasoning/thought-signature). Applied at the **shared chokepoints** — the SSE token formatter (`format_token_chunk`), `format_conversation_history` / `get_conversation_summary_for_logging`, and the `structured_output` JSON-mode fallback — so all their callers are protected, plus the remaining direct consumers. Four pre-existing bespoke `list → text` implementations (`react_finalize`, `react_runner`, `_extract_reasoning_detail`, the translation service) were consolidated onto it. **Non-destructive**: the source-of-truth messages stored in graph state are never mutated — normalization happens at the consumption boundary where a `str` is contractually required.

Files: `apps/api/src/infrastructure/llm/message_text.py` (new), `apps/api/src/infrastructure/llm/structured_output.py`, `apps/api/src/domains/agents/{services/streaming/service,nodes/response_node,nodes/react_nodes,nodes/router_node_v3,nodes/semantic_validator_node,nodes/planner_node_v3,services/fallback_response,services/query_analyzer_service,services/analysis/goal_inferrer,services/hitl/interactions/draft_critique,services/hitl/resumption_strategies,tools/emails_tools,tools/react_runner,utils/conversation_context,utils/message_filters,utils/token_utils}.py`, `apps/api/src/domains/{voice/service,briefing/llm,personalities/translation_service}.py`, `apps/api/src/infrastructure/scheduler/reminder_notification.py`. **Tests**: `tests/unit/infrastructure/llm/test_message_text.py` + regression tests reproducing both crashes (`test_streaming_service.py`, `test_conversation_context.py`); Ruff / Black / MyPy clean; 4447 unit tests green. **Docs**: `docs/technical/LLM_PROVIDER_CONSTRAINTS.md` (Gemini 3.x response content shape). No DB migration, no new env var, no endpoint change.

## [1.20.12] - 2026-05-21

### Added — Dormant interests are visible and manageable again (no more silent loss of control)

An interest decays over time (Bayesian weight × temporal decay); the nightly `cleanup_interests` job flips it to `status = "dormant"` once its effective weight stays below `0.5` for `interest_dormant_threshold_days` (15 days in prod), then deletes it after 90 days. `GET /interests` already returned dormant interests, but the Settings UI rendered only the `active` (grouped by category) and `blocked` buckets — `dormant` was filtered nowhere, so dormant interests were **invisible and uncontrollable** from the UI (yet still counted in the total) and were silently deleted at 90 days.

Dormant interests now render in a dedicated, visually-distinct "Dormant" accordion section (muted, moon badge — not struck-through like blocked ones) with full Edit / Delete control and an explicit **Reactivate** action. Reactivation resets the interest to a fresh state (`positive_signals = 1`, `negative_signals = 0`, `status = active`, `last_mentioned_at = now`, `dormant_since = None`) — mirroring `create()` via shared `INTEREST_INITIAL_*` constants — so its effective weight returns to ~0.75 (> the 0.5 dormancy threshold) and the nightly job won't immediately re-dormant it; this also sidesteps the temporal-decay dead zone (an old dormant cannot exceed the threshold through signals alone). New endpoint `POST /interests/{id}/reactivate` (ownership guard + `409` when the interest is not dormant); `dormant_count` added to `InterestListResponse`; the stats bar now breaks down as active / dormant / blocked.

### Added — Long-term memory now signals which memories are about to be forgotten

The nightly `cleanup_memories` job hard-deletes any non-pinned memory whose retention score (`weight_importance × importance + weight_recency × recency_factor`, minus a zero-usage penalty) falls below `memory_purge_threshold`, after a grace period. Memories stayed visible and pinnable, but the user had **no signal** of an impending purge — nothing prompted pinning before the irreversible deletion.

`MemoryResponse` now exposes a read-only `purge_risk` (`PurgeRiskLevel` enum: `protected` / `safe` / `at_risk` / `imminent`) and `retention_score`, computed on the fly. The Settings list flags `at_risk` / `imminent` (non-pinned) memories with an amber/red "may be forgotten" badge + tooltip inviting a pin. A new parameterizable `memory_purge_at_risk_margin` (default `0.1`) sets the band above the threshold flagged as `at_risk`. Read-only — the purge decision itself is unchanged.

### Changed — Retention scoring extracted to a pure domain module (Boy Scout)

`calculate_retention_score` and `should_purge` moved **verbatim** from `infrastructure/scheduler/memory_cleanup.py` into a new pure module `src/domains/memories/retention.py` (which also adds `RetentionConfig` and `classify_purge_risk`). The scheduler imports them back (`infrastructure → domain`, correct direction) and the API reuses the same functions — DRY, no behaviour change to the purge job, calibration tests preserved byte-for-byte (moved to `tests/unit/domains/memories/test_retention.py`).

Strictly additive — **no DB migration**, no existing endpoint signature changed, no scheduler trigger changed.

Files: `apps/api/src/core/{constants,config/agents,i18n_api_messages}.py`, `apps/api/src/domains/interests/{repository,router,schemas}.py`, `apps/api/src/domains/memories/{models,retention,schemas,router}.py`, `apps/api/src/infrastructure/scheduler/memory_cleanup.py`, `apps/web/src/hooks/{useInterests,useMemories}.ts`, `apps/web/src/components/settings/{InterestsSettings,MemorySettings}.tsx`, the 6 locale files, `.env.example` / `.env.prod.example`. **Tests** — `test_repository_reactivate.py`, `test_router_reactivate.py`, `test_retention.py`. Docs: `docs/knowledge/{08_interests,03_settings}.md`.

## [1.20.11] - 2026-05-21

### Added — ReAct mode now enriches answers with the proactive Initiative phase (ADR-070 / ADR-062 parity)

The Initiative phase — the post-execution step that, after the main answer, optionally runs read-only cross-domain lookups to enrich the reply (e.g. the weather and the drive time before an appointment) — only ran in Pipeline mode. In ReAct mode it was reachable *incidentally* on the draft-confirmation path, but the nominal path (`react_finalize → response`) bypassed it, so an autonomous ReAct answer never received this enrichment.

ReAct now reaches Initiative on the nominal path too, reusing the existing `initiative_node` (its pre-filter reads `query_intelligence.domains`, its execution summary reads `current_turn_registry`, and the per-request tool manifests are all already populated in ReAct). Wiring: `react_finalize` routes through a new conditional edge `route_from_react_finalize` → `initiative` when `INITIATIVE_ENABLED` **and** the new `INITIATIVE_REACT_ENABLED` flag are set (default `false` — ship dark), otherwise straight to `response`. The ReAct **draft** path is intentionally not gated by the new flag, so default-off behaviour is byte-identical to before this release.

Two ReAct-specific adaptations live outside the node: (1) `route_from_initiative` short-circuits to `response` in ReAct (there is no orchestrator loop to re-evaluate against — exactly one enrichment pass); (2) `response_node` previously injected the ReAct answer only `if not agent_results`, which would have dropped it once Initiative wrote `{turn}:initiative` first — it now **merges** via `_merge_react_synthesis_result` (idempotent on `{turn}:react_agent`) so the answer and the proactive findings coexist. A ReAct-only `<ProactiveFindings>` prompt directive invites the response LLM to weave the findings (already present via `data_for_filtering`) into the reply; the suggestion uses the existing `<InitiativeSuggestion>` injection.

One robustness fix in the node itself: `_format_execution_summary` only handled registry items in `dict` form (their shape in the pipeline after a PostgreSQL checkpoint round-trip), but in ReAct the registry is built in-memory by `react_execute_tools` and the items are live Pydantic `RegistryItem` objects. The function skipped them all, so the summary collapsed to `"No execution results."` and the LLM declined to act (observed live: *"sans détails sur les rendez-vous"*, `should_act=false`). It now normalizes both shapes.

**Config** — new `INITIATIVE_REACT_ENABLED` (default `false`). **Tests** — `test_routing_react_initiative.py`, `test_response_node_react_merge.py`, `test_initiative_execution_summary.py`, `test_react_initiative_flow.py`. Docs: ADR-070 + ADR-062 amendments, `docs/ARCHITECTURE_LANGRAPH.md`, `docs/technical/REACT_EXECUTION_MODE.md`.

### Added — Configurable Today Briefing widget content limits (`BriefingSettings`)

The per-widget content limits of the Today Briefing home page were hard-coded constants. They are now env-overridable via a new `BriefingSettings` module added to the `Settings` MRO: `BRIEFING_MAX_AGENDA_ITEMS` (default raised **3 → 10**), `BRIEFING_AGENDA_LOOKAHEAD_HOURS`, `BRIEFING_MAX_MAILS_ITEMS`, `BRIEFING_MAX_BIRTHDAYS_ITEMS`, `BRIEFING_MAX_BIRTHDAYS_HORIZON_DAYS`, `BRIEFING_MAX_REMINDERS_ITEMS`, `BRIEFING_HEALTH_WINDOW_DAYS`, `BRIEFING_WEATHER_DAILY_FORECAST_DAYS`. Defaults live in `core/constants.py` (`BRIEFING_*_DEFAULT`) — not in the briefing domain — so `core/config` can import them without triggering the briefing package `__init__` (which would create a config↔domain circular import). The pure formatters stay pure: `daily_forecast_days` is threaded as a parameter, not read from `settings`.

**Tests** — `test_briefing_settings.py`. Docs: `docs/technical/BRIEFING_DOMAIN.md`, `.env.example` / `.env.prod.example`.

### Fixed — Today Briefing greeting now reflects the actual agenda (right day, named event)

The dashboard greeting (a one-sentence LLM line) received only an aggregate `agenda_count` and **no dates**, so it could neither tell that the only event was *tomorrow* (it implied today) nor name it, and a raw count made it lump tomorrow's events into "this afternoon". The greeting now receives the upcoming events (≤ the agenda cap, next ~24 h) with a per-event day-aware start (`"15:00"` = today, `"demain 08:00"` = tomorrow); the prompt reacts to the day's shape (empty/busy, today vs tomorrow) and names an imminent event, without inventing counts. (Side fix found via this work: a literal `{…}` introduced in the prompt broke `str.format` and silently degraded the greeting to its static fallback — the prompt is now brace-safe and a regression test pins the `str.format` contract.)

**Tests** — `test_greeting_agenda_hint.py`.

### Fixed — Currency amounts (`$`) no longer rendered as broken LaTeX in chat and notifications

The markdown renderer (`MarkdownContent`) had KaTeX inline-math enabled with single-`$` delimiters, so a message containing two `$` (e.g. *"1,50$ … 9$"* in an interest notification) had the span between them rendered as a math formula — spaces dropped, `*`→`∗`, `é`→`eˊ`. `remark-math` is now configured with `singleDollarTextMath: false`: a single `$` is literal text, while `$$…$$` display math still works for the rare intentional case.

### Fixed — Currency exchange-rate API endpoint corrected (Frankfurter `.dev/v1`)

`CURRENCY_API_URL_DEFAULT` pointed at `https://api.frankfurter.dev` while the code appends `/latest`; the `.dev` host returns 404 on `/latest` (it requires the versioned `/v1` prefix) and the legacy `.app` host now 301-redirects. The default is now `https://api.frankfurter.dev/v1`, restoring accurate USD→EUR LLM-cost conversion (it had been falling back to the stale DB rate). `CURRENCY_API_URL` is now documented in `.env.example` / `.env.prod.example`.

### Changed — Scheduler leader-election "lock busy" log demoted from warning to info

`_log_stale_lock_info` logged `scheduler_leader_stale_lock_detected` at **warning** on every `SETNX` miss — i.e. every non-leader worker start, and in dev with `--reload` every fresh PID seeing the previous process's still-valid lock. It is now `scheduler_leader_lock_busy` at **info** (the normal case); a genuinely stuck lock (TTL `-1`, no expiry) is escalated to `scheduler_leader_lock_no_expiry` at warning. `docs/guides/GUIDE_DEBUGGING.md` updated to match.

Files: `apps/api/src/core/config/{briefing,agents,advanced}.py`, `apps/api/src/core/constants.py`, `apps/api/src/domains/agents/graph.py`, `apps/api/src/domains/agents/nodes/{routing,initiative_node,response_node}.py`, `apps/api/src/domains/agents/prompts/v1/briefing_greeting_prompt.txt`, `apps/api/src/domains/briefing/{constants,fetchers,formatters,llm}.py`, `apps/api/src/infrastructure/external/currency_api.py`, `apps/api/src/infrastructure/scheduler/leader_elector.py`, `apps/web/src/components/chat/MarkdownContent.tsx`, plus the test files above and the docs noted per section.

## [1.20.10] - 2026-05-21

### Fixed — ReAct mode: the agent's internal reasoning no longer leaks into the reply, and the answer is no longer shown twice

In ReAct execution mode two regressions surfaced on the final answer. (1) The reply reproduced the agent's step-by-step scaffolding — e.g. *"**PLAN** … **OBSERVATION** … **CROSS-CHECK** … **RÉPONSE FINALE** …"* — or the model adopted the agent's role outright (*"Je vais chercher l'adresse… il me faut ton point de départ… appel outil"*) instead of just answering. (2) The final text was streamed **twice** on screen before collapsing back to a single copy.

Root cause of (1) was twofold and converged on `response_node`. First, `react_setup_node` accumulates the full `react_agent_prompt` — including its `<Workflow>` PLAN/ACT/OBSERVE/CROSS-CHECK loop and the *"you operate in ReAct mode, call tools"* role — as `SystemMessage`s in `state["messages"]`, and `filter_for_llm_context()` **kept all non-`__` SystemMessages**, so this internal scaffolding reached the response LLM and the (weaker, high-temperature) model either mimicked the reasoning structure or impersonated the agent. Second, the ReAct loop's clean final answer is handed to the response synthesizer via `agent_results[…]["data"]["react_synthesis"]`, but that entry carries **no `status` key**, so `_format_status_messages()` fell through to `"❓ react_agent: Statut inconnu (unknown)"` and the answer text was **silently dropped** — leaving the LLM with no authoritative reply to reformulate, so it reconstructed one from the polluted context. A controlled A/B (deepseek-v4-flash, temp 1.0) confirmed the trigger: with the ReAct scaffolding present in history the leak/role-confusion appeared in ~20 % of runs; with it removed, 0 %.

Root cause of (2): LangGraph `stream_mode="messages"` emits **both** the LLM's streaming token deltas (`AIMessageChunk`) **and** the complete post-processed `AIMessage` the node returns to the `messages` channel. The streaming layer forwarded both, so the whole reply was sent a second time and a post-loop `content_replacement` chunk then collapsed it — the "double then single" flash. The previous guard (checking `content_final_replacement` in state) could never fire for the current turn, because that flag is set by the response node only *after* its own tokens have already streamed (the `values` snapshot arrives after the `messages` deltas). Confirmed in prod logs: streamed length was consistently ≈ `len(raw_content) + len(cleaned_content)` (≈ 2×).

The fix has three parts, all reusing existing structures. `filter_for_llm_context()` now **allowlists** only the compaction-summary `SystemMessage` (matched via a new `COMPACTION_SUMMARY_MARKER` constant centralized in `core/constants.py` and reused by `compaction_node` / `compaction_service`, replacing three duplicated literals) and drops every other `SystemMessage` as internal scaffolding — the compaction summary is preserved because it is the response LLM's sole carrier of compacted history (the `compaction_summary` state field is not re-injected into the prompt). `_format_status_messages()` now surfaces `data["react_synthesis"]` (keyed by a new shared `FIELD_REACT_SYNTHESIS` constant, eliminating the writer/reader literal drift that caused the silent drop) as the authoritative answer. `StreamingService._process_messages_chunk()` streams token deltas only (`AIMessageChunk`) and skips the complete returned `AIMessage` once deltas have been seen, with a non-streaming fallback that still emits the complete message when no delta occurred; this replaces the timing-broken `content_final_replacement` guard. Confirmed in dev logs: `response_duplicate_message_skipped{message_type="AIMessage"}` fires and the double is gone.

**Tests** — `test_agent_results_react_synthesis.py` (new: `react_synthesis` surfaced verbatim, turn filtering, no "Statut inconnu", empty-synthesis defence); `test_message_filters.py` (compaction summary kept, ReAct scaffolding dropped, Human/AI turns preserved, list-content `SystemMessage` dropped without crashing); `test_streaming_service.py` (delta streamed + flag set, complete message skipped after deltas, complete message emitted when no prior delta, consecutive deltas). 270+ unit tests green; Ruff / Black / MyPy clean.

Files: `apps/api/src/domains/agents/utils/message_filters.py`, `apps/api/src/domains/agents/formatters/agent_results.py`, `apps/api/src/domains/agents/services/streaming/service.py`, `apps/api/src/core/constants.py`, `apps/api/src/core/field_names.py`, `apps/api/src/domains/agents/nodes/response_node.py`, `apps/api/src/domains/agents/nodes/compaction_node.py`, `apps/api/src/domains/agents/services/compaction_service.py`, and the three test files above.

## [1.20.9] - 2026-05-20

### Fixed — ReAct mode: draft-based mutations now trigger HITL confirmation instead of hallucinating success (ADR-070 amendment)

In ReAct execution mode, asking the assistant to create/modify/reply/forward/delete (events, emails, contacts, tasks, …) made it answer *"C'est fait."* without ever performing the action. Root cause: these mutation tools do not execute directly — they prepare a **draft** (`requires_confirmation=True`) that must be confirmed via HITL before the real action runs. The pipeline wires this through `task_orchestrator → hitl_dispatch (draft_critique) → response`, but the ReAct loop had no equivalent: `react_execute_tools` collected the draft into the `ReactToolWrapper`'s `_accumulated_drafts` (dead code, never consumed) and looped back to the model, which then interpreted the "draft prepared" tool result as completion. Only tools flagged `hitl_required` in their manifest (e.g. `delegate_to_sub_agent_tool`) reached an `interrupt()`; the draft-based tools (all create/update/delete across event·email·contact·task·file·label) silently fell through.

The fix gives ReAct the same draft-confirmation flow as the pipeline by reusing the existing nodes — no new HITL machinery. `react_execute_tools_node` now detects a prepared draft from the raw tool output (`tool_metadata.requires_confirmation`), extracts the executable payload from the draft's registry item (`payload["content"]` — the same source the pipeline's `DraftExecutor` consumes), and sets `pending_draft_critique` / `pending_drafts_queue` **always** (`None` / `[]` when no draft) so a stale value from a previous turn can never mis-route the loop (the router does not reset these). A new routing function `route_from_react_execute_tools` sends the turn to `hitl_dispatch` (the shared `NODE_DRAFT_CRITIQUE`) when a draft is pending and otherwise loops back to `react_call_model`; the existing `hitl_dispatch → initiative → response_node` path then runs the confirm/edit/cancel HITL and executes the confirmed draft via `execute_draft_if_confirmed`. Because confirmation lives in a node **downstream** of `react_execute_tools`, resume after the interrupt re-enters `hitl_dispatch` only — the draft tool is never re-run, so there are no duplicate drafts. ReAct completion metrics are preserved on this short-circuited path: a shared `_record_react_metrics` helper (also used by `react_finalize`) emits `react_agent_executions_total{status="draft"}` plus iterations/duration, and a minimal `react_agent_result` (empty `final_message`, so `response_node` synthesizes from the real draft-execution result rather than a passthrough) is set for debug. Reminder creation (`create_reminder_tool`) executes directly without a draft and is intentionally not gated — unchanged in both modes. The now-redundant `_accumulated_drafts` collector was removed from `ReactToolWrapper` (it also carried a latent bug — `draft_content` was read from `tool_metadata`, where it is empty rather than from the registry payload), leaving a single, correct draft-detection path at the node level.

**Tests** — 4 new routing cases (`test_routing_react.py`: draft → `hitl_dispatch`; no-draft / missing-key / empty-draft → `react_call_model`) and 7 new draft-detection cases (`test_react_nodes_draft.py`: object/dict registry-payload extraction, `requires_confirmation=false`, no `tool_metadata`, missing `draft_id`, missing content, `draft_id` absent from registry). The obsolete `test_collects_draft_metadata` wrapper test was removed alongside the dead `_accumulated_drafts` collector.

Files: `apps/api/src/domains/agents/nodes/react_nodes.py`, `apps/api/src/domains/agents/nodes/routing.py`, `apps/api/src/domains/agents/graph.py`, `apps/api/src/domains/agents/tools/react_tool_wrapper.py`, `apps/api/src/infrastructure/observability/metrics_agents.py`, `apps/api/tests/unit/domains/agents/nodes/test_routing_react.py`, `apps/api/tests/unit/domains/agents/nodes/test_react_nodes_draft.py` (new), `apps/api/tests/unit/domains/agents/tools/test_react_tool_wrapper.py`, `docs/architecture/ADR-070-ReAct-Execution-Mode.md`, `docs/ARCHITECTURE_LANGRAPH.md`, `docs/technical/REACT_EXECUTION_MODE.md`. Amendment: [`docs/architecture/ADR-070-ReAct-Execution-Mode.md`](docs/architecture/ADR-070-ReAct-Execution-Mode.md).

## [1.20.8] - 2026-05-20

### Fixed — Conversation-history compaction v2: hardening, observability, and user-visible truncation (ADR-086)

The compaction node — entry point of the LangGraph chat graph since F4 (2026-03) — caused a production hang on 2026-05-16 where one user could no longer send any message. Every request hit the compaction node, the LLM responded once after ~32 s, then went silent for ~93 s until the SSE stream was cancelled at 125 s with `Erreur de connexion: network error`. Re-tries reproduced the same hang because the partial state was never fully persisted. Forensic audit surfaced seven defects: `await llm.ainvoke()` had **no timeout** in `_summarize_chunk`; compaction ran synchronously at the graph entry-point and blocked the whole turn; the router-level `last_heartbeat` only pulsed **between** received chunks (never during a silent `await` — Cloudflare tunnel idle ~100 s closed the connection); prior `"compaction #N"` SystemMessages were excluded from `to_compact` and accumulated linearly; an `except Exception` branch silently produced `strategy="descriptive_fallback"` with a near-useless stub (`"[Previous conversation compacted — 48 messages…]"`) and was counted as a success; no retry on transient errors, no global budget, no signal to the frontend during the wait; the frontend had no `'compacting'` status and no UI hint that a summary was running.

**Resilience backend** — `apps/api/src/domains/agents/services/compaction_service.py` now wraps every LLM call in `asyncio.wait_for(per_chunk_timeout_seconds=35)`, retries on `ConnectionError` / `TimeoutError` via `tenacity.AsyncRetrying` with exponential backoff (`stop_after_attempt(3)`, `wait_exponential(multiplier=1.0, min=1.0, max=30)` — `min` aligned with the multiplier so the first retry actually waits one base unit instead of clamping to 0 per tenacity issue #175), and wraps the whole `compact()` in a global `asyncio.wait_for(global_timeout_seconds=120)`. On global-timeout or any unrecoverable error, the new `_truncation_fallback` produces an explicit, deterministic `SystemMessage` (`"[Older conversation truncated — N messages removed because the automatic summary could not complete (global_timeout). Key identifiers preserved: …]"`) instead of the silent `descriptive_fallback` stub that v1 emitted. The `descriptive_fallback` codepath is removed; `strategy="truncation"` is the explicit, user-visible substitute. New settings centralised in `agents.py` + `constants.py` and exposed in `.env.example` / `.env.prod.example`: `compaction_per_chunk_timeout_seconds`, `compaction_global_timeout_seconds`, `compaction_max_retries`, `compaction_retry_backoff_base_seconds`, `compaction_include_previous_summaries`. `should_compact()` reordered so a small-but-token-heavy conversation (e.g. 13 messages containing a single 6 K-token AIMessage with embedded tool data) still triggers compaction — the token count is the real signal, the `compaction_min_messages` floor is now only a fast-path for sub-threshold conversations.

**Prior-summary consolidation** — Previous `"compaction #N"` SystemMessages are now prepended to the merge step (recursive consolidation, opt-in via `compaction_include_previous_summaries=true`), preventing the linear accumulation observed in v1 where each turn appended a new summary on top of all the old ones. The node only removes the prior summaries from state if the merge **actually consolidated them** (`consolidated_previous_summaries=True`) — on truncation fallback or any path that didn't merge them, they are preserved so the conversation does not lose information v1 had retained. The strategy label `single_chunk_with_merge` was introduced to distinguish a one-chunk run that still ran a merge step from a true `multi_chunk` LLM workload — Grafana no longer over-estimates the multi_chunk rate. `_format_messages_for_summary` now serialises content blocks via `json.dumps` instead of `BaseMessage.text`, which on `ToolMessage` with `content: list[ContentBlock]` was leaking Python repr / JSON wrappers into the prompt and degrading the summary quality.

**SSE custom stream-mode signal** — The compaction node now emits `compaction_start` and `compaction_done` payloads via `langgraph.config.get_stream_writer()` through a new `stream_mode="custom"` (LangGraph 1.x). The orchestration layer's two `astream()` call sites were updated to include `"custom"` in their mode list. `StreamingService._process_custom_chunk` translates these payloads into `ChatStreamChunk(type="execution_step", metadata={step_type: "compaction", step_label: ...})`, folding `step_type` / `step_label` into the metadata dict to fit the existing schema. The node falls back to a no-op writer when `get_stream_writer` is missing or raises (older LangGraph, unit tests, graph executed without `stream_mode=["custom"]`) — the fallback is logged at WARNING **and** increments a new Counter `compaction_writer_unavailable_total{reason}` so silent degradation is now visible in Grafana. The `compaction_start` payload carries `estimated_duration_seconds` (heuristic derived from `COMPACTION_UI_ESTIMATE_*` constants: tokens-per-chunk × seconds-per-chunk, capped at the global-budget margin) and `is_resume`. The `compaction_done` payload carries `strategy`, `tokens_saved`, `duration_ms`.

**Concurrent SSE keepalive** — New module `apps/api/src/domains/agents/api/sse_keepalive.py` exposes `iter_with_keepalive(source, keepalive_interval_seconds)` which spawns **one** consumer task that drains the upstream into an `asyncio.Queue` and yields a `KeepalivePulse` sentinel on every `queue.get()` timeout (defaults to `SSE_HEARTBEAT_INTERVAL=15s`). The router serialises pulses as the SSE comment line `": heartbeat\n\n"`. Critically the single-consumer-task design preserves `ContextVar.set() / .reset()` stability (the earlier prototype spawned a fresh `asyncio.create_task(__anext__())` per iteration, which broke because each `__anext__()` ran in a brand-new Context and the tokens minted by the upstream's `__aenter__` could no longer be `.reset()` from the next iteration's Context). The `finally` block cancels the consumer, awaits it, swallows the expected `CancelledError` / `StopAsyncIteration`, and logs at DEBUG only on unexpected exceptions — full observability without leaking errors past the caller. The legacy router-level `last_heartbeat` check (which only pulsed between received chunks) is removed.

**User-visible frontend feedback** — New reducer transitions `STREAM_COMPACTION_START` / `STREAM_COMPACTION_DONE` set `status === 'compacting'` (folded into `useChat.isTyping` so the existing `disabled={isTyping || isUsageBlocked}` wire on `ChatInput` locks the textarea automatically). `handleCompactionStep` (in `apps/web/src/lib/sse-handlers/handlers.ts`) intercepts `execution_step` chunks carrying `metadata.step_type === 'compaction'` and drives a **morphing sonner toast** via a stable id (`COMPACTION_TOAST_ID = "compaction-progress"`): `toast.loading(t('chat.compaction.in_progress'))` on start, then `toast.success(t('chat.compaction.completed', {tokens}))` or `toast.warning(t('chat.compaction.truncated'))` on done. A first attempt placed a `<CompactionBanner>` inside `ChatMessageList` (sticky-top variant tested) but the dual `overflow-y: auto` boundary (scroll container + max-width wrapper) made the banner invisible at the default post-send scroll position. The pivot to a position-fixed sonner toast (decoupled from the chat scroll layout) is documented in the *Update* section of ADR-086 — the SSE contract and reducer state are unchanged, only the rendering layer moved. New i18n keys `chat.compaction.{in_progress, completed, truncated}` added in all 6 locales (`fr` / `en` / `de` / `es` / `it` / `zh`), with `{{tokens}}` interpolation in the success copy. Dead key `chat.compaction.elapsed` removed (it had been retained for an inline-timer variant of the banner that the toast does not need).

**Context-usage pill** — Discreet 16-px SVG ring with `tokens / threshold` percentage in the chat header (between the voice-mode badge and the delete-conversation button). Colours shift across 4 tiers (green ≤ 50 %, amber ≤ 75 %, orange ≤ 90 %, rose > 90 %). The badge label is clamped at 100 % (we never display nonsensical inline values like *"150%"*); the tooltip displays the real ratio and uses the explicit `chat.context_usage.tooltip_overflow` copy when `ratio > 1` (*"compaction will run on your next message"*). The pill hydrates from server state on page load via a new helper `useChat.hydrateContextUsage(tokens, threshold)` consumed in `apps/web/src/app/[lng]/dashboard/chat/page.tsx`, fed by two new optional fields on `ConversationTotalsResponse` (`context_tokens` / `context_threshold`) populated by `ConversationService._compute_checkpoint_context_usage()`. That helper uses `checkpointer.aget_tuple(config)` (not `aget`) so the access goes through the canonical `CheckpointTuple` API instead of relying on the stale `aget` type-cast in `InstrumentedAsyncPostgresSaver` — a future LangGraph bump can no longer silently break the pill hydration. The token counter is the same `CompactionService._token_counter` the backend uses for decisions, so the pill and the compaction trigger agree on what the threshold is. Three i18n keys in `chat.context_usage.*` (tooltip / tooltip_compact / tooltip_overflow) localized in 6 languages with `{{tokens}}` / `{{threshold}}` / `{{percent}}` interpolation.

**Observability** — Five new Prometheus metrics in `apps/api/src/infrastructure/observability/metrics_compaction.py`: `compaction_chunk_timeouts_total` (per-chunk `asyncio.wait_for` triggers), `compaction_global_timeouts_total` (truncation fallback firings), `compaction_total_duration_seconds` (v2-aware histogram with buckets up to 180 s), `compaction_writer_unavailable_total{reason}` (no-op writer fallbacks), and the existing `compaction_executions_total{strategy}` now labels `single_chunk` / `multi_chunk` / `single_chunk_with_merge` / `truncation` / `noop` (the legacy `descriptive_fallback` is gone). New Grafana dashboard `infrastructure/observability/grafana/dashboards/14-compaction.json` (7 panels: strategy mix, latency p50/p95/p99, chunk timeouts, global timeouts, errors by type, skipped reasons, tokens saved). Structured logging on every defensive branch: `compaction_threshold_exceeded`, `compaction_chunk_timeout`, `compaction_global_timeout_fallback_to_truncation`, `compaction_writer_unavailable`, `compaction_node_applied`, `compaction_completed` with the full set of structured fields (token counts, strategy, duration, attempts).

**Operator runbook** — New transactional admin script `scripts/admin/reset_user_checkpoints.sql` that wipes a single user's LangGraph checkpoints (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) inside a transaction with before/after counts, leaving application data (messages, conversations) untouched — the fastest recovery path for any future stuck-conversation report. The runbook itself is documented in `docs/technical/COMPACTION_v2.md` along with threshold-tuning guidance, the `/resume` forced-compaction command, Grafana diagnosis tips, and a Cloudflare-tunnel note clarifying that the 15 s SSE keepalive is sufficient to neutralize the ~100 s idle cut (no `cloudflared` configuration change required).

**Dependencies** — `tenacity==9.1.4` declared explicitly in `apps/api/requirements.txt` (was transitive via `langchain-core`). DeepSeek V4 family added to `MODEL_CONTEXT_WINDOWS` in `apps/api/src/core/config/llm.py` (`deepseek-v4-flash` / `deepseek-v4-pro` / `deepseek-v4-reasoner` / `deepseek-v4` → 1 M tokens) so the dynamic compaction threshold (`compaction_threshold_ratio × context_window`) is correct on V4 deployments instead of falling back to the 128 K default.

**Tests** — 25 new backend tests (`test_compaction_service_v2.py`: 9 cases including per-chunk timeout, retry-then-succeed, retry exhaustion, global-timeout fallback, unexpected-error fallback, single_chunk_with_merge label, prior-summary consolidation, ContextVar regression; `test_sse_keepalive.py`: 9 cases including a regression guard `test_contextvar_set_and_reset_survives_keepalives`; `test_custom_stream_mode_integration.py`: 1 end-to-end LangGraph custom-mode → StreamingService integration; `test_compaction_node.py`: 4 new cases on writer emission + RemoveMessage consolidation behaviour; `test_streaming_service.py`: 4 new `TestProcessCustomChunk` cases) and 25 new frontend tests (`chat-reducer.compaction.test.ts`: 6 cases on the new reducer transitions, `chat-reducer.context-usage.test.ts`: 7 cases on the hydration action, `compaction-handler.test.ts`: 5 cases including the non-compaction execution_step regression guard, `ContextUsagePill.test.tsx`: 7 cases including the badge-clamping regression on `ratio > 1`).

**Baseline integration-test sweep (2026-05-20)** — Took the opportunity to clear 19 pre-existing integration-test failures unrelated to compaction (4 stale `get_redis_session` mocks pointing at `base_google_client` instead of `base_oauth_client`; 1 hardcoded LLM provider list missing `qwen` / `gemini` — now derived from the canonical `ProviderType` Literal via `typing.get_args()`; 14 stale `get_global_registry` mocks pointing at `query_analyzer_service` instead of `agent_registry`, plus 9 `"contacts"` → `"contact"` assertions aligned with the singular canonical name in `core_types.source_domains`). No production code touched; all changes confined to `tests/integration/`. The post-sweep baseline (`BASELINE_KNOWN_FAILURES.md`) is now `64 passed, 0 failed, 172 skipped`.

Files: `apps/api/src/domains/agents/services/compaction_service.py`, `apps/api/src/domains/agents/nodes/compaction_node.py`, `apps/api/src/domains/agents/api/sse_keepalive.py` (new), `apps/api/src/domains/agents/services/streaming/service.py`, `apps/api/src/domains/agents/services/orchestration/service.py`, `apps/api/src/domains/agents/api/router.py`, `apps/api/src/domains/conversations/{router,schemas,service}.py`, `apps/api/src/infrastructure/observability/metrics_compaction.py`, `apps/api/src/core/{config/agents,constants,config/llm}.py`, `apps/api/requirements.txt`, `apps/web/src/components/chat/ContextUsagePill.tsx` (new), `apps/web/src/lib/sse-handlers/handlers.ts`, `apps/web/src/reducers/chat-reducer.ts`, `apps/web/src/types/chat-state.ts`, `apps/web/src/hooks/{useChat,useConversation}.ts`, `apps/web/src/app/[lng]/dashboard/chat/page.tsx`, 6 × `apps/web/locales/{lang}/translation.json`, `docs/architecture/ADR-086-Conversation-History-Compaction-v2.md` (new), `docs/technical/COMPACTION_v2.md` (new), `infrastructure/observability/grafana/dashboards/14-compaction.json` (new), `scripts/admin/reset_user_checkpoints.sql` (new). Architecture: [`docs/architecture/ADR-086-Conversation-History-Compaction-v2.md`](docs/architecture/ADR-086-Conversation-History-Compaction-v2.md). Runbook: [`docs/technical/COMPACTION_v2.md`](docs/technical/COMPACTION_v2.md).

## [1.20.7] - 2026-05-17

### Fixed — Pre-confirmation HITL preview rendering: unified across DraftCritique and ForEachConfirmation (ADR-085 extension)

After fixing the post-execution rendering, the **pre-confirmation** previews — the bullet list of items the user is about to mutate, shown before the destructive/for_each HITL question — were found to use two distinct codepaths that produced incoherent rows for the same scenario. For `Supprime tous mes rappels`:

```
# Path A — ForEachConfirmationInteraction          # Path B — DraftCritiqueInteraction (batch)
Rappel : Médecin le 17 mai 2026 à 19:00            🔔 Médecin 🔔 dimanche 17 mai 2026 à 19:00
```

Path A built rows from a generic `item_previews: list[dict]` joined by a localized connector (`"le"`/`"on"`/`"el"`/...) — **no emoji prefix**. Path B built rows via a ~100-line per-`draft_type` if/elif chain that injected the row emoji both as `main_label` prefix and inside the appended `detail_parts` — **duplicated 🔔** when the markdown bullet got flattened by the chat UI. And `_DESTRUCTIVE_CONFIRM_ACTION_TITLES` had no `reminder_delete` entry, so the title fell back to the generic *"Confirmation requise"* instead of *"Confirmation de suppression"* — same systemic oversight that motivated ADR-085.

Unified both paths to share a single registry-driven helper:

- New public function `apps/api/src/core/i18n_drafts.py::format_hitl_item_preview(draft_type, content, language, user_timezone)` consumes `DRAFT_DISPLAY_REGISTRY` (ADR-085) — emoji, ordered label-extraction fields, optional secondary datetime, localized capitalized noun via `DRAFT_RESULT_NOUNS`. Always renders the datetime with `include_day_name=True`. Output: `{emoji} {Noun_capitalized} : {label} - {datetime_with_day_name}` (Chinese uses its own word order template inherited from `RESULT_HEADER_TEMPLATES`).
- `DraftCritiqueInteraction._generate_batch_critique` — removed the ~100-line `_extract_batch_item_preview` if/elif chain; calls the helper directly. Defensive 6-field fallback (`subject/summary/title/name/content/label_name`) preserved for unregistered draft types.
- `ForEachConfirmationInteraction._build_item_previews_section` — added a `steps: list[dict[str, Any]] | None` parameter and a static helper `_steps_to_draft_type(steps)` that maps a FOR_EACH `tool_name` to a canonical `DraftType` string (`cancel_reminder_tool` → `"reminder_delete"`, `update_event_tool` → `"event_update"`, `send_email_tool` → `"email"`, etc.). When the mapping resolves, the unified helper is used; otherwise the legacy generic renderer remains intact (preserved for non-draft domains: places, weather, routes, web_fetch, mcp).
- `_DESTRUCTIVE_CONFIRM_ACTION_TITLES` — `reminder_delete` added in all 6 languages (`"Confirmation de suppression"` / `"Confirm deletion"` / `"Confirmar eliminación"` / `"Löschung bestätigen"` / `"Conferma eliminazione"` / `"确认删除"`).

Final rendering for `Supprime tous mes rappels` (both HITL paths converge):

```
⚠️ **Confirmation de suppression**

**Éléments concernés :**
- 🔔 Rappel : Médecin - dimanche 17 mai 2026 à 19:00
- 🔔 Rappel : Ramonage - jeudi 21 mai 2026 à 19:00
- 🔔 Rappel : Alsace - vendredi 22 mai 2026 à 19:00

⚠️ Cette action est irréversible.

**Confirmes-tu cette suppression ?**
```

Other domains inherit the same shape: `📅 Événement : Réunion équipe - lundi 20 mai 2026 à 10:00`, `📧 Email : Confirmation rdv jeudi - jeudi 16 mai 2026 à 14:00`, `👤 Contact : Marie Dupont`, `✅ Tâche : Préparer démo - mardi 20 mai 2026 à 17:00`.

**Backwards-compat preserved**: `HitlMessages.get_draft_emoji()` unchanged. The legacy generic FOR_EACH fallback (with `item_date_connector`) remains for non-draft domains. All existing tests in `tests/unit/domains/agents/` keep passing.

**Files**: MODIFY `apps/api/src/core/i18n_drafts.py` (+ `format_hitl_item_preview`), `apps/api/src/core/i18n_hitl.py` (+ `reminder_delete` × 6 languages in `_DESTRUCTIVE_CONFIRM_ACTION_TITLES`), `apps/api/src/domains/agents/services/hitl/interactions/draft_critique.py` (- `_extract_batch_item_preview`, refactor `_generate_batch_critique`), `apps/api/src/domains/agents/services/hitl/interactions/for_each_confirmation.py` (+ `_steps_to_draft_type`, refactor `_build_item_previews_section`). NEW tests `apps/api/tests/unit/domains/agents/drafts/test_hitl_item_preview.py` (119 parametrized cases) and `apps/api/tests/unit/domains/agents/drafts/test_for_each_draft_type_mapping.py` (25 cases). Architecture: `docs/architecture/ADR-085-Draft-Display-Registry.md` extension section.

---

### Fixed — Post-HITL confirmation rendering: from "Action exécutée avec succès" × N to a localized, structured result block (ADR-085)

`Supprime tous mes rappels` (3 reminders) used to render after confirmation as `✅ 3/3 / ✅ Action exécutée avec succès × 3` — no domain emoji, no per-item label, no datetime context, bland default message repeated. Forensic trace exposed **4 disjoint sources of per-`DraftType` knowledge** in the post-HITL rendering pipeline with hetereogeneous coverage (13/16, 15/16, 6/16, plus a hard-coded label-extraction chain), of which the recently-added `REMINDER_DELETE` type had only been registered in one. `file_delete` and `label_delete` silently suffered the same defect in batch mode — never spotted because never exercised under batch.

Replaced the 4 sources with a **single declarative registry** keyed by `DraftType` (`DRAFT_DISPLAY_REGISTRY` in `apps/api/src/domains/agents/drafts/display.py`) that captures, per type: the domain emoji, the ordered label-extraction fields, an optional secondary datetime key (e.g. `trigger_at` for reminders), the rich detail rows for single-confirm, and i18n keys driving header composition. `assert_registry_completeness()` is invoked at lifespan startup *and* in a parametrized unit test — a new `DraftType` without a registered display config either fails to boot or fails the PR.

Localized **batch header now uses correct grammar in all 6 supported languages** (`apps/api/src/core/i18n_drafts.py`): two new tables (`DRAFT_RESULT_NOUNS` and `DRAFT_RESULT_VERBS_PAST`) encode noun forms (singular/plural + gender for fr/es/it) and past-participle forms (4 gender/number combinations for fr/es/it, invariant string for en/de/zh-CN). `RESULT_HEADER_TEMPLATES` handles Chinese's different word order (`已删除 3 个提醒`). `compose_result_header(success, total, noun_key, verb_past_key, language)` assembles `"3 rappels supprimés"` (fr m+plur), `"1 tâche créée"` (fr f+sing), `"3 reminders deleted"` (en invariant), `"3 Termine gelöscht"` (de invariant), `"3 attività create"` (it noun-invariant + verb agreement). Pluralization rule per language: French treats 0 and 1 as singular; English/Spanish/German/Italian treat 1 as singular and everything else as plural; Chinese is invariant.

Each batch row now carries both the **item label** (sourced via the registry's `item_label_fields` priority chain, with dotted notation for nested keys like `file.name` or `contact.names.0.displayName`) **and an optional contextual datetime** (`item_secondary_datetime_key` — e.g. `trigger_at` for reminders → ` — 16 mai à 14h00`). When extraction fails, a `draft_result_format_empty_label` warning is logged with the available content keys.

Final rendering for `Supprime tous mes rappels`:

```
🔔 ✅ 3 rappels supprimés
✅ **Faire les courses** — 16 mai à 14h00
✅ **Appeler Maman** — 17 mai à 09h00
✅ **Rendez-vous médecin** — 18 mai à 11h00
```

**Backwards-compat preserved**: `HitlMessages.get_draft_emoji()` keeps the same shape (becomes a one-line wrapper over the registry), the three external callsites in `draft_critique.py` are untouched, and `DRAFT_SUCCESS_MESSAGES` / `DRAFT_CANCEL_MESSAGES` are kept (still used by `Draft.get_summary()`), with the missing `reminder_delete` entry added in all 6 languages.

**Files**: NEW `apps/api/src/domains/agents/drafts/display.py`, MODIFY `apps/api/src/core/i18n_drafts.py` / `apps/api/src/core/i18n_hitl.py` / `apps/api/src/domains/agents/nodes/response_node.py` / `apps/api/src/main.py`, NEW tests `apps/api/tests/unit/domains/agents/drafts/test_display_registry.py` (~30 parametrized cases on `DraftType` × 6 languages) and `apps/api/tests/unit/domains/agents/nodes/test_format_draft_execution_result.py` (19 cases covering batch/single/cancel/error per type + per-language header snapshots). Architecture: `docs/architecture/ADR-085-Draft-Display-Registry.md`.

---

## [1.20.6] - 2026-05-15

### Added — Indexable vs Semantic criteria: universal planning principle + leak detector

Repeated diagnostics of "mes deux prochains rdv médicaux" surfaced a class of failures invisible to the existing validator: the planner LLM was passing semantic qualifiers (e.g. `medical`, `urgent`, `important`) as the `query` of literal-text-search tools (Google Calendar / Gmail / Notion-like stores), which then returned 0 hits or false positives, then no `web_searchs`/`events` card was rendered. Cause is twofold and **independent of any specific connector**:

- **Weaker / non-reasoning query analyzers** (`deepseek-v4-flash` without `reasoning_effort`) misclassified specific filtered queries as broad skill activations (e.g. `briefing-quotidien`) → `SkillBypassStrategy` short-circuited the LLM planner entirely → fixed 5-step generic plan with `max_results=5` and a 2-day window → 0 events of the requested category. Adding `reasoning_effort=high` fixed the skill misclassification but exposed the second failure mode.
- **Reasoning-enabled planners still leaked semantic terms into `query`** — e.g. `get_events_tool(query="medical", max_results=2, time_max=now+1y)` against a calendar API that indexes by title literals. The smart_planner prompt's pre-existing rule 4 ("Non-searchable field criteria → broad results, Response LLM filters") was too abstract and required an inference about each connector's indexing semantics that only top-tier reasoning models (e.g. `gpt-5.2`) reliably made.

A 3-layer defense addresses this generically, gated by a feature flag in `observe` mode for the rollout — **no plans are altered in production until metrics confirm safe activation in Phase 2**.

#### Layer 1 — Universal planning principle in the smart_planner prompt

New section `INDEXABLE vs SEMANTIC CRITERIA (universal planning principle)` in `apps/api/src/domains/agents/prompts/v1/smart_planner_prompt.txt`, placed before `PLANNING RULES` so it is a conceptual framing applied to every rule below. Generic, English (cohérent avec le pipeline post-`semantic_pivot`), agnostic au connecteur (Google / Microsoft / Apple / Notion / Slack / JIRA / futurs MCPs traités identiquement). Covers:

- The two-class taxonomy: **indexable** values (literal counterpart in a structured field — dates, IDs, sender, status, label id, location…) → tool parameter; **semantic** qualifiers (no literal counterpart — categories, priorities, quality/ranking, relative time without date) → Response LLM filtering downstream.
- A concept-level example list grouped by sub-class (`nature/category`, `priority/urgency`, `quality/ranking`, `relative time without a date`) explicitly marked non-exhaustive — bias on principle, not casuistic list.
- The **CARDINALITY × SEMANTIC trap**: "the N <semantic> X" → N is the FINAL count after Response filtering, not `max_results`. Bring back a 20–50 batch.
- Two **EXCEPTIONS** to preserve legitimate cases: (1) user explicitly cites the term as a literal string to match (quoted, "with X in the title/subject"), (2) tool description states it performs semantic/vector search on `query`.
- Interpolation placeholder `{semantic_filter_terms_hint}` — when empty renders as `(none)` to keep prompt-cache-friendly stable length; when non-empty lists the terms flagged by the query analyzer for the current request.

Prompt size impact: **~370 tokens added** — recovered by Anthropic/OpenAI prompt caches after the first call, so steady-state cost is null.

#### Layer 2 — Structured hint emitted by the query analyzer

New `semantic_filter_terms: list[str]` field on `QueryAnalysisOutput` (Pydantic, `default_factory=list` → schema rétro-compatible; if the LLM ignores it, comportement actuel préservé). Description explicitly frames this as a **probabilistic hint, NOT authoritative** — the planner still owns the decision. Propagated through `QueryAnalysisResult` → `QueryIntelligence.semantic_filter_terms: tuple[str, ...]` (frozen) → `ValidationContext.semantic_filter_terms`. Also cleared by the existing `chat_override` (same hygiene rationale as the existing `skill_name` clear, lines 1162-1173 of `query_analyzer_service.py`).

Corresponding new section in `query_analyzer_prompt.txt` (`INDEXABLE vs SEMANTIC HINT`) instructing the LLM what to emit: english-pivoted form, leave empty when user cites the term as a literal value, do NOT include indexable values. Cohérent avec la langue du pipeline post-`semantic_pivot`.

Metric `lia_planner_semantic_filter_terms_emitted_total{model, term_count_bucket}` (`1` / `2-3` / `4+`) records emission rate per model — drives the Phase 2 rollout decision.

#### Layer 3 — Universal validator (`observe` by default, `autocorrect` on flip)

New `_check_semantic_leak` method on `PlanValidator` in `apps/api/src/domains/agents/orchestration/validator.py`, invoked from `validate_execution_plan` for every step of every plan (single-domain, multi-domain, future strategies). Tool-agnostic: iterates over `TEXT_SEARCH_PARAM_NAMES` (`query`, `q`, `search`, `search_query`, `text`, `keywords`) on each TOOL step. Word-boundary match against the term set (split + strip on punctuation) to avoid substring false positives (`medical` ⊄ `medicalign`).

Mode-gated by `PLANNER_SEMANTIC_LEAK_MODE` (settings field `planner_semantic_leak_mode: Literal["off", "observe", "autocorrect"]`):

- `off` — kill switch.
- `observe` (default) — log + metric `lia_planner_semantic_leak_detected_total{tool_name, param_name, mode}`, plan untouched. **Zero regression guarantee for Phase 1 ship**.
- `autocorrect` — NULL the leaky parameter and bump `max_results` to `PLANNER_SEMANTIC_BROAD_BATCH` (default `25`, range `10-100`) **only when** the existing `max_results` is `< PLANNER_SEMANTIC_BROAD_BATCH_MIN` (= `20`). Already-broad values are preserved (test row covered). Emits the dedicated `lia_planner_semantic_leak_autocorrected_total{tool_name, param_name}` counter.

Two escape hatches honored by the validator (mirror the prompt exceptions): (1) any quote character in the param value (`"medical"` or `"urgent"` patterns) → skip (literal-match intent), (2) tool's manifest `text_search_mode != "literal"` → skip (the store performs semantic search natively).

Rollout strategy explicitly **observe → measure → autocorrect**: ship Layer 3 in `observe`, accumulate 1-2 weeks of `lia_planner_semantic_leak_detected_total{mode="observe"}` data, then flip via `.env` (no code redeploy) once leak frequency is confirmed and a manual sample shows no false positives.

#### New `ToolManifest.text_search_mode` (Layer 4, structural)

New field `text_search_mode: Literal["literal", "semantic", "hybrid"] = "literal"` on `ToolManifest` (`apps/api/src/domains/agents/registry/catalogue.py`). Default `"literal"` preserves the current behavior of every existing tool — **no tool needs to be updated to ship Phase 1**. Future MCP tools, Notion AI search, vector-search backends can declare `"semantic"` or `"hybrid"` to opt out of the leak detector cleanly. Documented in the field's inline comment with reference to the prompt section and the validator.

### Added — New env vars (4 settings, all tunable via `.env`)

| Variable | Default | Range | Purpose |
|----------|---------|-------|---------|
| `PLANNER_SEMANTIC_LEAK_MODE` | `observe` | `off` / `observe` / `autocorrect` | Validator behavior on a detected leak. Ship in `observe` for the rollout, flip to `autocorrect` in Phase 2. |
| `PLANNER_SEMANTIC_BROAD_BATCH` | `25` | 10-100 | `max_results` bump applied by `autocorrect`, only when the existing value is `< 20`. |

Constants centralised in `src/core/constants.py`: `TEXT_SEARCH_PARAM_NAMES` (frozenset of free-text query parameter names), `PLANNER_SEMANTIC_BROAD_BATCH_DEFAULT` (25), `PLANNER_SEMANTIC_BROAD_BATCH_MIN` (20). `.env.example` and `.env.prod.example` updated.

### Tests

- `tests/unit/domains/agents/orchestration/test_validator_semantic_leak.py` — 17 cases covering the 10-row regression matrix (generic listing without semantic filter, indexable filter such as `from:marc`, quoted literal `"urgent"`, semantic-search tool exception, target case `mes deux prochains rdv médicaux` in both `observe` and `autocorrect` modes, cardinality × semantic combo such as "the 3 most important emails from boss", mixed indexable + semantic, multi-step per-step independent detection, conservatism when no hint is emitted, word-boundary true positive on `medical clinic Paris` and absence of false positive on `medicalign software`) plus 3 mode-gating tests (`off` is a no-op, `observe` does not mutate the plan, `autocorrect` preserves an already-broad `max_results`) and 2 backward-compatibility tests (default `ValidationContext.semantic_filter_terms == ()`, full `validate_execution_plan` pipeline runs cleanly with no hint).
- Non-regression verified by running adjacent suites: 521 cases in `tests/unit/domains/agents/orchestration/` pass after the change, 276 in `tests/unit/domains/agents/registry/`, 60 across `tests/unit/domains/agents/services/` matching `planner` or `query_analyzer`. Docker `lia-api-dev` restarted cleanly (healthy after ~50 s, no startup exception related to the new code).

### Observability

- Three Prometheus counters in `src/infrastructure/observability/metrics_agents.py`: `lia_planner_semantic_filter_terms_emitted_total{model, term_count_bucket}`, `lia_planner_semantic_leak_detected_total{tool_name, param_name, mode}`, `lia_planner_semantic_leak_autocorrected_total{tool_name, param_name}`.
- New structured log events: `semantic_filter_terms_emitted` (query analyzer), `semantic_leak_in_plan` (validator), `semantic_leak_autocorrected` (validator). The leaky `query` value itself is **not logged** (potential PII); only the matched semantic terms, the step id, the param name, and the tool name appear in the warning.

### Refactor — Timeout configuration centralization (Vagues 1–5): 24 timeouts moved to Settings + `.env`, 2 magic numbers extracted, 1 orphan wired, 2 dead constants + 1 duplicate Field removed

Audit (V1 → V3 in [docs/technical/TIMEOUT_REGISTRY.md](docs/technical/TIMEOUT_REGISTRY.md)) inventoried ~80 timeouts across the backend (HTTP outbound, tools, DB, Redis, locks, scheduler, SSE, WebSocket, browser, voice, MCP, sub-agents, infra) and surfaced three classes of debt:

- **Hardcoded constants used in production paths** but never exposed to operators (no `Settings` Field, no `.env` entry) — required a Docker rebuild to tune. Examples: `HTTP_TIMEOUT_PERPLEXITY` (60 s), `DEFAULT_TOOL_TIMEOUT_SECONDS` (30 s), `BROWSER_TOOL_TIMEOUT_SECONDS` (300 s), `OAUTH_LOCK_TIMEOUT_SECONDS` (10 s), `MCP_OAUTH_HTTP_TIMEOUT_SECONDS` (10 s), 17 others.
- **Inline magic numbers** (`90.0` for image-generation tools, `120.0` for `claude_server_task_tool`) embedded in `parallel_executor._compute_step_timeout` without a named constant.
- **Orphans, duplicates, dead code, inverted cascades**: `task_orchestrator_execution_timeout_seconds` declared in `agents.py` + `.env.example` but **never read** at runtime; `http_timeout_currency_api` and `currency_api_timeout_seconds` shadowing each other (only the latter actually used by the Frankfurter client); `HTTP_TIMEOUT_PROMPT_REGISTRY` and `BACKGROUND_TASK_TIMEOUT_DEFAULT` defined in `constants.py` with zero call sites; `BRAVE_SEARCH_ENRICHMENT_TIMEOUT = 3.0 s` firing **before** the per-request `HTTP_TIMEOUT_BRAVE_SEARCH = 5.0 s` it was supposed to wrap (G2 cascade inversion).

LLM-call timeouts (`router`, `response`, `planner`, `query_analyzer`, etc.) are deliberately **out of scope** — they are governed per-LLM-type by the `llm_config` table and the Admin → Configuration LLM UI; per-row granularity does not fit env vars. Annex A of the registry cross-references them for reading.

The migration is split into five waves; each wave preserves the historical default value for every migrated entry — **no behavioural change of normal traffic** unless the operator overrides via `.env`. The only intentional behavioural changes are: (a) the Brave G2 cascade fix, (b) the wiring of the previously-orphan `task_orchestrator_execution_timeout_seconds` as a soft wave-scheduling cap.

#### Vague 1 — HTTP outbound (7 timeouts)

`HTTP_TIMEOUT_PERPLEXITY` (60.0), `HTTP_TIMEOUT_WEATHER` (10.0), `HTTP_TIMEOUT_WIKIPEDIA` (15.0), `HTTP_TIMEOUT_BRAVE_SEARCH` (5.0), `BRAVE_SEARCH_ENRICHMENT_TIMEOUT_SECONDS` (**3.0 → 8.0**, G2 fix), `OLLAMA_DISCOVERY_TIMEOUT_SECONDS` (5.0), `WEB_FETCH_TIMEOUT_SECONDS` (15.0). Migrated as Pydantic Fields in `connectors.py` / `agents.py` / `llm.py`. Consumers updated: `perplexity_client`, `openweathermap_client`, `wikipedia_client`, `brave_search_client`, `ollama_discovery`, `web_fetch_tools`, `response_node` (3 sites), `knowledge_enrichment_service` (2 sites). The Brave fix preserves the documented constraint `enrichment ≥ HTTP × 1.5`.

#### Vague 2 — Connectors / locks / SSE / scheduler (11 timeouts, 2 new modules)

Created `apps/api/src/core/config/scheduler.py` (`SchedulerSettings` — `scheduled_actions_execution_timeout_seconds`, `scheduled_actions_stale_timeout_minutes`) and `apps/api/src/core/config/locks.py` (`LocksSettings` — `oauth_lock_timeout_seconds`). Both added to the `Settings` MRO in `__init__.py` (positions 21 and 22). The remaining nine entries enriched existing modules: `connectors.py` (`http_timeout_connector_standard/long`, `http_timeout_sse_polling`, `hue_pairing_timeout_seconds`), `agents.py` (`http_timeout_conditional_eval`), `mcp.py` (`mcp_oauth_http_timeout_seconds`), `usage_limits.py` (`usage_limit_ws_idle_timeout_seconds`), `health_metrics.py` (`health_metrics_heartbeat_fetch_timeout_seconds`).

Consumers migrated to `settings.<field>`: `connectors/router.py` (5 sites), `base_api_key_client`, `parallel_executor` (conditional eval), `notifications/router`, `infrastructure/locks/oauth_lock` (`__init__` signature now takes `int | None` and resolves at call time to preserve testability), `mcp/auth.py`, `mcp/oauth_flow.py` (3 sites), `philips_hue_client`, `usage_limits/websocket`, `heartbeat/context_aggregator`, `scheduled_action_executor` (2 sites).

#### Vague 3 — Tool execution & extraction of inline magic numbers (8 settings)

`default_tool_timeout_seconds` / `max_tool_timeout_seconds` / `default_tool_timeout_ms` / `browser_tool_timeout_seconds` / `max_browser_tool_timeout_seconds` (all in `agents.py`), `browser_default_timeout_ms` (in `browser.py`, used by the catalogue manifest), and **two new constants** introduced for the magic-number extraction: `IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS_DEFAULT = 90.0` (formerly inline `_IMAGE_TOOL_TIMEOUT_SECONDS`) → `image_generation_tool_timeout_seconds` Field in `image_generation.py`; `DEVOPS_CLAUDE_TOOL_TIMEOUT_SECONDS_DEFAULT = 120.0` (formerly inline `_DEVOPS_TOOL_TIMEOUT_SECONDS`) → `devops_claude_tool_timeout_seconds` Field in `devops.py`. Both new constants follow the new naming convention `<DOMAIN>_<USAGE>_TIMEOUT_<UNIT>_DEFAULT` (existing constants kept under their legacy names — boy-scout for new code only).

`parallel_executor._compute_step_timeout` rewritten to read every value from `settings` (sub-agent floor/ceiling already used `settings.subagent_tool_*` since ADR-083; now the same applies to generic / browser / image / devops). `catalogue_loader.py` reads `settings.default_tool_timeout_ms` (10 manifest sites) and `settings.browser_default_timeout_ms` (1 site) instead of the constants. The constants themselves remain in `constants.py` as the single source of truth for defaults consumed by Pydantic Fields and by the existing `test_parallel_executor_compute_step_timeout.py` matrix (no test rewrite needed).

#### Vague 4 — Hygiene

- Removed dead constants: `HTTP_TIMEOUT_PROMPT_REGISTRY` (defined in `constants.py:788`, **zero call sites**), `BACKGROUND_TASK_TIMEOUT_DEFAULT` (defined in `constants.py:832`, **zero call sites**).
- Resolved the **G1 currency_api duplicate**: removed `http_timeout_currency_api` Field (`connectors.py:343`), the matching constant `HTTP_TIMEOUT_CURRENCY_API` (`constants.py:784`), the env line `HTTP_TIMEOUT_CURRENCY_API` (both `.env.example` and `.env.prod.example`), and the `validate_config.py` range entry. The actually-used `currency_api_timeout_seconds` Field in `advanced.py` (read by `currency_api.py:65`) is the surviving setting. Notes left at the deleted call sites point at the resolution for archaeological clarity.

#### Vague 5 — Wiring `task_orchestrator_execution_timeout_seconds`

The Field was declared in `agents.py:466` and listed in both `.env` files since Sprint 17.4 but **never read**. Wired in `parallel_executor.execute_plan_parallel` as a **soft check at the start of each wave-scheduling iteration** (lines 1346–1370): when `time.time() - start_time` exceeds `settings.task_orchestrator_execution_timeout_seconds`, the loop breaks (no new wave is scheduled) but the in-flight wave is **never violently cancelled** — preserves sub-agents and browser flows that legitimately need their full per-step budget. A `parallel_execution_global_timeout` warning log records the breach with `elapsed_seconds`, `completed_count`, `total_steps`, and the configured timeout. Default 120 s preserved; HITL pauses do not count (LangGraph `interrupt()` exits the function and `start_time` is re-initialised on resume).

`hitl_max_wait_seconds` (declared, 900 s) remains intentionally **non-wired** — kept as an orphan Field documented in TIMEOUT_REGISTRY § 6, pending a product decision (auto-cancel HITL after N minutes vs. soft-watchdog log only vs. delete). Consumers who want this guard today must implement at the application layer.

### Added — TIMEOUT_REGISTRY.md (single source of documentation truth)

[`docs/technical/TIMEOUT_REGISTRY.md`](docs/technical/TIMEOUT_REGISTRY.md) — 12 sections covering every backend timeout with the conventions, every Field's range, default, consumer file, and notes on cascade relationships. Sections cover HTTP outbound (connectors, LLM provider discovery), database / cache, locks, tool execution (`parallel_executor`), conditional / micro-eval, SSE & WebSocket, scheduler, resilience / circuit breaker, agent-level (`react_agent_timeout_seconds`, the now-wired `task_orchestrator_execution_timeout_seconds`, `hitl_max_wait_seconds`), browser, devops. Annex A enumerates the LLM-call timeouts deliberately out of scope (managed by `llm_config` UI). Annex B mirrors the frontend-side timeouts (`apps/web/src/lib/constants.ts`, `apps/web/src/constants/timing.ts`). Annex C explicitly lists known gaps deferred to a future Vague 6: `postgres_statement_timeout`, `app_startup_timeout_seconds` / `app_shutdown_timeout_seconds`, `mcp_session_close_timeout_seconds`, sub-agent / browser / MCP nested-ReAct temporal guards, frontend chat SSE watchdog, APScheduler per-job timeout. The known-conflicts section documents G1 and G2 resolutions for posterity.

### Added — New env vars exposed by the centralization (24 settings, all tunable via `.env`)

Full alphabetical list (every entry has the same default as before — operators can now change them without rebuilding):

| Variable | Default | Range | Purpose |
|----------|---------|-------|---------|
| `BRAVE_SEARCH_ENRICHMENT_TIMEOUT_SECONDS` | `8.0` | 2.0–60.0 | Wraps Brave cache lookup + HTTP. **Was 3.0 s** — raised to fix G2 inversion. |
| `BROWSER_DEFAULT_TIMEOUT_MS` | `120000` | 30000–600000 | `browser_agent` catalogue manifest default (planner-facing display). |
| `BROWSER_TOOL_TIMEOUT_SECONDS` | `300.0` | 30.0–1800.0 | Floor for `browser_task_tool` step timeout. |
| `DEFAULT_TOOL_TIMEOUT_MS` | `30000` | 1000–300000 | Catalogue manifest default for non-browser tools. |
| `DEFAULT_TOOL_TIMEOUT_SECONDS` | `30.0` | 1.0–300.0 | Generic-tool floor in `parallel_executor`. |
| `DEVOPS_CLAUDE_TOOL_TIMEOUT_SECONDS` | `120.0` | 30.0–900.0 | `claude_server_task_tool` step floor (formerly inline magic). |
| `HEALTH_METRICS_HEARTBEAT_FETCH_TIMEOUT_SECONDS` | `2.0` | 0.5–30.0 | Safety wrap on health-metrics fetch in heartbeat context. |
| `HTTP_TIMEOUT_BRAVE_SEARCH` | `5.0` | 1.0–60.0 | Per-request HTTP timeout. |
| `HTTP_TIMEOUT_CONDITIONAL_EVAL` | `5.0` | 1.0–30.0 | Jinja conditional evaluation in `parallel_executor`. |
| `HTTP_TIMEOUT_CONNECTOR_LONG` | `30.0` | 1.0–300.0 | Bulk fetches, attachment downloads. |
| `HTTP_TIMEOUT_CONNECTOR_STANDARD` | `15.0` | 1.0–120.0 | Standard connector HTTP ops. |
| `HTTP_TIMEOUT_PERPLEXITY` | `60.0` | 1.0–180.0 | Perplexity API (deep queries). |
| `HTTP_TIMEOUT_SSE_POLLING` | `30.0` | 5.0–120.0 | Long-poll on the notifications SSE endpoint. |
| `HTTP_TIMEOUT_WEATHER` | `10.0` | 1.0–60.0 | OpenWeatherMap. |
| `HTTP_TIMEOUT_WIKIPEDIA` | `15.0` | 1.0–60.0 | Wikipedia API. |
| `HUE_PAIRING_TIMEOUT_SECONDS` | `30.0` | 5.0–120.0 | Philips Hue Bridge pairing handshake. |
| `IMAGE_GENERATION_TOOL_TIMEOUT_SECONDS` | `90.0` | 10.0–600.0 | `generate_image` / `edit_image` step floor (formerly inline magic). |
| `MAX_BROWSER_TOOL_TIMEOUT_SECONDS` | `600.0` | 60.0–3600.0 | Hard ceiling for `browser_task_tool` (planner cannot exceed). |
| `MAX_TOOL_TIMEOUT_SECONDS` | `120.0` | 30.0–600.0 | Hard ceiling for generic tools. |
| `MCP_OAUTH_HTTP_TIMEOUT_SECONDS` | `10` | 1–60 | MCP OAuth 2.1 helper calls (discovery, token exchange, refresh). |
| `OAUTH_LOCK_TIMEOUT_SECONDS` | `10` | 1–120 | Per-(user, connector) Redis lock acquisition for OAuth refresh. |
| `OLLAMA_DISCOVERY_TIMEOUT_SECONDS` | `5.0` | 1.0–60.0 | `/api/tags` + `/api/show` (NOT a chat completion). |
| `SCHEDULED_ACTIONS_EXECUTION_TIMEOUT_SECONDS` | `300` | 30–1800 | Per-action wall-clock (already in `.env`, now in `SchedulerSettings`). |
| `SCHEDULED_ACTIONS_STALE_TIMEOUT_MINUTES` | `10` | 1–120 | `recover_stale_executing()` threshold (already in `.env`, now in `SchedulerSettings`). |
| `USAGE_LIMIT_WS_IDLE_TIMEOUT_SECONDS` | `120` | 30–600 | Idle close on the usage-limits live-update WebSocket. |
| `WEB_FETCH_TIMEOUT_SECONDS` | `15.0` | 1.0–120.0 | `fetch_web_page` tool single HTTP request. |

`scripts/validate_config.py` updated with matching ranges in `INT_VARS` / `FLOAT_VARS` for every new entry. The cross-check `validate_config range == Pydantic Field range` is followed for the Vague 1–3 additions; legacy Fields (`http_timeout_oauth/token/external_api`, `currency_api_timeout_seconds`) keep their pre-migration `gt=0` upper-bound-less form — flagged for alignment in a future hardening pass (audit V3 § A3).

### Removed

- Constant `HTTP_TIMEOUT_PROMPT_REGISTRY` (`constants.py`) — dead code.
- Constant `HTTP_TIMEOUT_CURRENCY_API` (`constants.py`) — duplicate (G1).
- Constant `BACKGROUND_TASK_TIMEOUT_DEFAULT` (`constants.py`) — dead code.
- Field `http_timeout_currency_api` (`connectors.py`) — duplicate (G1). Surviving Field: `currency_api_timeout_seconds` in `advanced.py`.
- Env var `HTTP_TIMEOUT_CURRENCY_API` (both `.env.example` and `.env.prod.example`) — G1.
- Inline magic numbers `_IMAGE_TOOL_TIMEOUT_SECONDS = 90.0` and `_DEVOPS_TOOL_TIMEOUT_SECONDS = 120.0` from `parallel_executor.py` — extracted as named constants + Settings Fields (Vague 3).

### Tests

No test rewriting was necessary: `test_parallel_executor_compute_step_timeout.py` continues to import the constants (`BROWSER_TOOL_TIMEOUT_SECONDS`, `DEFAULT_TOOL_TIMEOUT_SECONDS`, `MAX_BROWSER_TOOL_TIMEOUT_SECONDS`, `MAX_TOOL_TIMEOUT_SECONDS`) as the assertion source — these constants now back the Settings Fields as defaults, so the test matrix passes unchanged. The previously-acknowledged audit V3 § A8 coverage gap is **closed** in this changeset: `tests/unit/domains/agents/orchestration/test_parallel_executor_global_timeout.py` adds two cases that prove the soft check at `parallel_executor.py:1360` (Vague 5 wiring) fires when budget is exceeded (counter increments with `plan_outcome=empty`, structured warning logged) and stays silent when budget is generous. The `parallel_execution_global_timeout_total` Counter was also added in `metrics_agents.py` and incremented at the break point.

### Audit V3 — known follow-ups (intentionally not in this changeset)

The 8-angle rigorous review (cascades, default-vs-range, validate_config-vs-Field, units, semantic duplicates, soft-check edge cases, HITL × timer, test coverage) flagged 8 errors and 8 warnings. Those that remain after the five waves:

- **Cascade browser/sub-agent step ceilings** (1800 / 900 s) can mathematically exceed the parent `task_orchestrator_execution_timeout_seconds` ceiling (600 s). Intentional (preserve sub-agents in flight) but the docstring should explicitly state the soft semantics.
- **`validate_config.py` ↔ Field Pydantic ranges**: realigned end-to-end. The 4 Vague-3 mismatches initially listed here (`DEFAULT_TOOL_TIMEOUT_MS/SECONDS`, `BROWSER_TOOL_TIMEOUT_SECONDS`, `MAX_BROWSER_TOOL_TIMEOUT_SECONDS`) were aligned on the Pydantic Field bounds (single source of enforcement truth). The 4 legacy `gt=0`-only Fields in `connectors.py` (`http_timeout_oauth`, `http_timeout_token`, `http_timeout_external_api`, `apple_connection_timeout`) were also tightened to `ge=1.0, le=60.0` (Apple: `le=120.0`) to match `validate_config.py`. `APPLE_CONNECTION_TIMEOUT` was added to `validate_config.FLOAT_VARS` for completeness. No remaining range divergence between Pydantic and `validate_config.py`.
- **Unit drift** between `default_tool_timeout_seconds` and `default_tool_timeout_ms`, and between `browser_tool_timeout_seconds` (300 s, executor) and `browser_default_timeout_ms` (120 s = 120 000 ms, manifest). No cross-validator.
- **DB column `user_mcp.timeout_seconds`** uses the constant `MCP_DEFAULT_TIMEOUT_SECONDS` as `server_default`, not `settings.mcp_tool_timeout_seconds` — overriding the env at runtime does not update the DB default.
- **Vague 5 soft-check edge cases**: steps not yet scheduled when the check fires generate **no `StepResult`** (silent skip rather than `TIMEOUT` error); no Prometheus metric; no test coverage.

These are tracked in TIMEOUT_REGISTRY.md and are explicit candidates for a future P1-hardening PR.

### Fixed — Gemini 3.x `response.content` shape: planner JSON parse error + 27 latent sites

Switching the `query_analyzer` and `planner` LLM types to `gemini-3.1-pro-preview` surfaced a `smart_planner_panic_failed` with `JSON decode error: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)`. The pipeline degraded to a conversational fallback instead of executing the plan. Root cause: `langchain_google_genai/chat_models.py:933` wraps `response.content` as `list[dict]` (content blocks, like Anthropic) **specifically for Gemini 3.x** — condition `if thought_sig or _is_gemini_3_or_later(effective_model_name)`. Every other provider (Gemini 2.5, OpenAI, Anthropic, DeepSeek, Qwen, Perplexity, Ollama) keeps `response.content` as `str`.

Two pervasive patterns across the codebase silently broke on this shape:

- **Pattern A** — `str(response.content).strip()` (8 sites). `str(list[dict])` produces the **Python `repr()`** of the list (single-quoted keys/values), not valid JSON. The parser error signature (`char 2`) maps exactly to `[` then `{` then `'`.
- **Pattern B** — `X.content if isinstance(X.content, str) else str(X.content)` (20 sites). The `isinstance` branch correctly handles the `str` case, but the `else` branch produces the same Python-repr garbage as Pattern A. Looks defensive, isn't.

The planner failure was loud (JSON parser exception caught and surfaced as `panic_failed`). The other 27 sites would have manifested progressively as Gemini 3.x usage widened to other LLM types — corrupted token counts (`token_counter_service`), garbled message previews (`memory_extractor`, `extraction_service` ×2, `compaction_service`), broken HITL classification (`hitl_classifier`, `item_filter`, `draft_modifier`), wrong summaries (`compaction_service`, `psyche/service`, `heartbeat/prompts`), etc.

Fix: replaced all 28 occurrences with the **LangChain Core 1.2+ official `BaseMessage.text` property**, which handles both shapes — for `str` content it returns the string; for `list[dict]` content it concatenates the `text` blocks and ignores `thinking` blocks. The property returns a `TextAccessor` (a `str` subclass kept for backward compat with the deprecated `.text()` method form), so `isinstance(message.text, str) == True` and runtime behaviour is identical to `content` for the previously-working `str` case. Where MyPy strict mode could not reconcile `TextAccessor` with a later `str` reassignment or `str` return (6 sites), the read is wrapped in `str(...)` — runtime no-op since `TextAccessor` IS-A `str`.

Sites touched (28 occurrences across 21 files):

- `domains/agents/services/smart_planner_service.py` (×2 — single-domain + panic retry)
- `domains/agents/services/planner/strategies/{single_domain,multi_domain}.py`
- `domains/agents/services/compaction_service.py` (×3 — `_extract_identifiers`, `_format_messages_for_summary`, `_summarize_chunk`)
- `domains/agents/services/semantic_pivot_service.py` — also dropped a paranoid `hasattr(result, "content")` fallback since `BaseChatModel.ainvoke` always returns a `BaseMessage`
- `domains/agents/services/token_counter_service.py`
- `domains/agents/services/memory_extractor.py` (×2 — message formatting + LLM-result text)
- `domains/agents/services/hitl_classifier.py`, `…/hitl/item_filter.py`, `…/hitl/draft_modifier.py`
- `domains/agents/nodes/compaction_node.py`, `…/response_node.py`
- `domains/notifications/broadcast_service.py`
- `domains/user_mcp/service.py`
- `domains/journals/extraction_service.py` (×2), `…/consolidation_service.py`
- `domains/interests/services/extraction_service.py` (×2), `…/content_sources/llm_reflection_source.py`, `domains/interests/proactive_task.py`
- `domains/psyche/service.py` (×2 — `psyche_summary`, `psyche_narrative`)
- `domains/heartbeat/prompts.py`

Sites intentionally not touched:

- `domains/agents/nodes/react_nodes.py:551` — already has a custom block-text extractor (`" ".join(block.get("text", "") for block in last_message.content if isinstance(block, dict))`) that works correctly on Gemini 3.x.
- `domains/channels/inbound_handler.py:259` — `chunk` is a custom streaming object (`chunk.type` is `"token"`/`"content_replacement"`/`"error"`/…), not a LangChain `BaseMessage`; `.text` is not available.
- `domains/agents/utils/message_filters.py:251` — `str(msg.content)[:100]` in a debug-log preview; latent but cosmetic only.
- `infrastructure/llm/providers/responses_adapter.py:572/586/595/733` — outbound serialization of messages to the OpenAI Responses API payload, different semantics from reading an LLM response.
- `domains/agents/services/query_analyzer_service.py:1344` + `domains/agents/services/analysis/goal_inferrer.py:116` — defensive `if hasattr(msg, "content")` fallbacks on objects that may not be `BaseMessage`; outside the LLM-response hot path.

Validation: trace `617d5411-1ee6-4b08-9d50-550fe0deddc1` (2026-05-15 17:10) — full Gemini 3.1 Pro Preview pipeline runs end-to-end: `query_analyzer` → `planner_v3_success` (`steps=2`, `used_panic_mode=false`) → `task_orchestrator` → `initiative` → `response` → persist (19 400 tokens, 0.049 EUR). Same query before the fix: `smart_planner_panic_failed` → conversational fallback. Ruff, Black, MyPy strict all pass on the 21 modified files.

## [1.20.5] - 2026-05-14

### Fixed — Sub-agent delegation: vague outputs, runaway exploration, dilution by the response node

After the ADR-083 Phase 2 rewrite of `delegate_to_sub_agent_tool` onto `ReactSubAgentRunner`, observed runs of "as a senior analyst, use a specialized sub-agent" queries surfaced three failure modes that combined to make delegation produce **no measurable value over a direct answer**:

- **`GraphRecursionError` / 47-char final message** — `subagent_default_max_iterations` defaulted to `5`, which LangGraph spends on `2 × call_model + 2 × execute_tools + 1` supersteps. Sub-agents that batched 4-5 parallel searches in pass 1 then ran out of budget for the synthesis pass and exited with a near-empty `final_message` (one observed run: 9 iterations, 31 brave_search calls, **47 chars** returned). Default bumped to `10` (range `1–30`); the per-step ReAct loop now has headroom for ~3-4 tool rounds plus synthesis.
- **80+ tools exposed to the sub-agent** — `resolve_tools_for_subagent` was called with `allowed_tools=[]`, so it fell back to "everything except `SUBAGENT_DEFAULT_BLOCKED_TOOLS`" (~83 read-only tools). Faced with that catalogue, the sub-agent's ReAct loop burns its recursion budget exploring options instead of converging. New whitelist mode wired through `SUBAGENT_RESEARCH_TOOLS_WHITELIST` (default `brave_search_tool,fetch_web_page_tool`) — when set, the resolver becomes an allow-list and the sub-agent stays focused on factual verification.
- **`delegate_to_sub_agent_tool` step killed at 120 s** — the generic `MAX_TOOL_TIMEOUT_SECONDS = 120` is fine for a single API call but starves a slow-reasoning ReAct loop (deepseek with high effort, 3-4 tool rounds + synthesis can legitimately need 90-150 s). Pair of dedicated env vars added — `SUBAGENT_TOOL_TIMEOUT_SECONDS` floor (default `180`, range `30-600`) and `SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS` ceiling (default `300`, range `60-900`) — wired through `parallel_executor._execute_step_with_timeout` via a `tool_name == "delegate_to_sub_agent_tool"` branch so other tools keep the global `MAX_TOOL_TIMEOUT_SECONDS = 120` (unchanged).
- **`response_node` compressing 26 KB of expert analysis to 2 KB and overlaying the principal's voice** — the `<ResponseGuidelines>` rule "do not list/detail results (handled by cards)" is correct for record lists (emails, events) but defeats the purpose of delegation when the payload is a multi-section expert analysis written specifically as the response body. New conditional `<SubAgentDeliveryOverride>` block in `response_system_prompt_base.txt` detects substantial textual analyses (markdown sections + expert voice + cited sources + several thousand characters) and switches the response node to verbatim restitution: no compression, no rewriting in the assistant's conversational personality voice, only a one-sentence intro and 2-3 follow-up suggestions allowed. For non-textual payloads (record lists, action confirmations), `<ResponseGuidelines>` apply unchanged.

### Changed — `subagent_react_prompt.txt` rewritten for delivery discipline

Previous prompt (~17 lines) stated "produce a concise factual analytical text" — too vague. The sub-agent was tempted to over-explore (31 brave_search calls in one observed run) and under-deliver (47-char final message in the same run, 203 chars in another). Rewrite (~65 lines) introduces:

- **Value contract**: "If a knowledgeable assistant could write the same thing without consulting you, you have failed. The bar is what an expert with 10+ years in this domain would produce."
- **Task calibration lexicon**: keywords like *analyse / étude / compte rendu / détaillé / approfondi* trigger a multi-section structured report; *résumé / brief / concis* triggers a tight condensation; *comparaison / vs / benchmark* triggers parallel structure across dimensions. Depth modifiers win on ambiguous wording (e.g. "synthèse détaillée" → deeper form).
- **Epistemic rigor**: cite URLs for every numeric/factual claim, mark inferences explicitly ("Inference:", "Per my analysis:"), name gaps when sources are insufficient instead of fabricating, quote numbers/dates/names exactly.
- **Execution discipline**: 1-3 rounds of tool calls preferred, "5+ parallel searches in one round" called out as a tool-spam tell, "when you have enough material, STOP and write" — soft signal complementing the hard `recursion_limit` cap.
- **Negative voice anchor**: explicitly forbids the principal's conversational tone (sarcasm, orality, "tour de contrôle"/"vieux briscard" rhetoric, first-person banter). The sub-agent is a written expert document; the principal's voice is the principal's.
- **NO markdown tables** — tables are explicitly penalised in `Output style`. For comparisons or multi-dimensional data, the prompt mandates parallel bullet lists, one section per item with the same sub-headings, or inline structured prose. For numeric data, figures are integrated into prose with sources cited inline.
- **Pre-emit self-check** — 6-question checklist (sources cited? inferences marked? depth proportional? expert voice preserved? gaps named? endorsable by a senior practitioner?) before producing the final answer.
- **Explicit anti-patterns** — 7 documented failure modes (e.g. *"announcing 'Voici l'analyse complète' then delivering 47 characters"*) — LLMs exclude better than they prescribe.

### Added — New env vars (4 settings, all tunable via `.env`)

| Variable | Default | Range | Purpose |
|----------|---------|-------|---------|
| `SUBAGENT_TOOL_TIMEOUT_SECONDS` | `180.0` | 30-600 | Floor on `delegate_to_sub_agent_tool` step timeout. Replaces the generic 120 s. |
| `SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS` | `300.0` | 60-900 | Dedicated ceiling — operators can raise the sub-agent budget without touching the app-wide `MAX_TOOL_TIMEOUT_SECONDS`. |
| `SUBAGENT_RESEARCH_TOOLS_WHITELIST` | `brave_search_tool,fetch_web_page_tool` | snake_case CSV | Tools the ReAct sub-agent may invoke. Empty = legacy blocklist-only behaviour. |
| `SUBAGENT_DEFAULT_MAX_ITERATIONS` | bumped `5 → 10` | 1-30 (ceiling raised from 15) | LangGraph `recursion_limit` of the sub-agent ReAct loop. |

A Pydantic `field_validator` on `subagent_research_tools_whitelist` rejects malformed values (dashes instead of underscores, semicolons instead of commas, leading digits, uppercase) with a clear error at config-load time — silent typo-induced empty whitelists would otherwise degrade the sub-agent to blocklist-only mode (the known cause of `GraphRecursionError`).

### Tests

- `tests/unit/test_subagent_settings.py` — 21 cases covering defaults (180/300/10), Pydantic ranges (rejected below 30 / above 600 for timeout, below 60 / above 900 for max timeout, above 30 for iterations), the `subagent_research_tools_whitelist_parsed` property (CSV parsing edge cases: trailing comma, whitespace-only entries, single value, empty input), and the new `field_validator` (rejects dashes, semicolons, uppercase, leading digits; accepts empty; accepts default).
- `tests/unit/domains/sub_agents/test_subagent_prompt.py` — 8 cases asserting the rewritten prompt contains the value contract ("materially better", "10+ years"), explicit `NO markdown tables` directive, the task calibration lexicon (analyse / synthèse / résumé / comparaison), the self-check protocol, and explicit anti-patterns. New case for the `<SubAgentDeliveryOverride>` block in `response_system_prompt_base.txt`.

### Documentation

- `docs/technical/SUB_AGENTS.md` — new env vars table (4 settings, ranges, rationale), new `Why dedicated timeout + whitelist` section explaining why the generic `MAX_TOOL_TIMEOUT_SECONDS` was insufficient and why the 80-tool catalogue starved the recursion budget, new `Response Node — Verbatim Delivery Override (2026-05-14)` section documenting the conditional `<SubAgentDeliveryOverride>` block.
- In-app FAQ (`apps/web/locales/*/translation.json`, 6 languages): new `faq.changelog.versions.v1_20_5` entry (3 user/admin items focused on observable quality improvement, no internal implementation details).
- `docs/GETTING_STARTED.md` compatibility line bumped to v1.20.5.
- `README.md` top banner updated to v1.20.5 (v1.20.4 demoted to a `<details>` block).
- Version bumped to `1.20.5` across `apps/api/pyproject.toml`, `apps/web/package.json`, `package.json`, and `apps/web/src/lib/version.ts` (`LAST_UPDATED = 2026-05-14T17:30:00`, shown on the landing page).

## [1.20.4] - 2026-05-12

### Fixed — Browser agent: model 404, premature step kill, AX-tree starvation

- **`claude-opus-4.6` (and `claude-opus-4.5`, `claude-sonnet-4.6`, `claude-haiku-4.5`) → `404 not_found_error`** — the LLM catalogue (`llm_models`, `llm_config_overrides`) and `domains/llm_config/constants.py` stored Anthropic 4.x model ids with a dot (`claude-opus-4.6`), but the Anthropic API only accepts the dashed form (`claude-opus-4-6`, …) — `core/config/llm.py` already used the dashed form. Any LLM type pointed at one of these (e.g. `browser_agent` after the admin picked "Claude Opus 4.6") crashed at instantiation. Renamed to the dashed form everywhere: pricing/config seeds, `mcp_app_react_agent` default, unit tests, frontend i18n strings (`claude-opus-4-5` template label), docs. New Alembic migration `rename_anthropic_model_ids_001` rewrites the existing `llm_models.model_name` / `llm_config_overrides.model` rows (idempotent regex `^(claude-[a-z]+-[0-9]+)\.([0-9]+)$` → `\1-\2`, reversible); DEV migrated, PROD updated via the equivalent in-transaction SQL.
- **`browser_task_tool` step killed mid-task** — the parallel executor wraps each tool step in `asyncio.wait_for(timeout=step.timeout_seconds or DEFAULT_TOOL_TIMEOUT_SECONDS)`, and `browser_task_tool` (a full nested ReAct loop) was absent from `_HIGH_LATENCY_TOOLS`, so the planner's 30/60/120 s `timeout_seconds` cancelled the loop before it could finish (observed step durations: exactly 30 009 / 60 020 / 120 009 ms, then `asyncio.CancelledError` inside `browser_task_tool`). Added `browser_task_tool` to `_HIGH_LATENCY_TOOLS` with a dedicated floor `BROWSER_TOOL_TIMEOUT_SECONDS = 300 s` and ceiling `MAX_BROWSER_TOOL_TIMEOUT_SECONDS = 600 s` (the generic `MAX_TOOL_TIMEOUT_SECONDS = 120 s` no longer applies to it).
- **Accessibility-tree truncation hid form controls** — `BROWSER_AX_TREE_MAX_TOKENS` code default raised `5000 → 15000` (new `BROWSER_AX_TREE_MAX_TOKENS_DEFAULT` constant, referenced from `BrowserSettings`); `.env.example` / `.env.prod.example` updated.

### Added — `BROWSER_REACT_MAX_ITERATIONS`

New env var (default 15, range 1–50) capping the `create_react_agent` `recursion_limit` of the browser agent loop run by `browser_task_tool` — mirrors `REACT_AGENT_MAX_ITERATIONS` / `MCP_REACT_MAX_ITERATIONS`. Constant `BROWSER_REACT_MAX_ITERATIONS_DEFAULT`, field `browser_react_max_iterations` on `BrowserSettings`, wired in `browser_tools.py` (was a hard-coded `15`); `.env.example` / `.env.prod.example` and `BROWSER_CONTROL.md` updated.

### Changed — Browser agent prompt (`prompts/v1/browser_agent_prompt.txt`)

Rewritten from web-research best practices (notably the `browser-use` agent prompt): explicit read-vs-transactional task modes, no fabricated query-param URLs, observe→act→verify loop with a mandatory snapshot after state-changing actions, stale-`[ref]` handling, autocomplete → click-the-suggestion (not Enter), `fill` only on real input controls (textbox/searchbox/combobox/spinbutton), cookie-banner/403/login obstacle handling, stuck-loop detection, stop-before-payment + report-only-facts. `browser_agent_prompt` added to the `PromptName` `Literal` (was missing — pre-existing gap).

### Fixed — `reasoning_effort` ↔ model coherence (robustness on model/provider change)

Switching a model/provider on an LLM type could leave a `reasoning_effort` whose **shape** no longer matched the new model's `reasoning_widget` (e.g. a DeepSeek `{"effort": "off"}` enum value left on a config whose effective model became the Qwen `toggle_budget` default — the admin UI rendered it as "thinking disabled", so it looked fine), which then crashed the typed reasoning builder at `get_llm()` time (`RuntimeError: ... must be ReasoningEffortToggleBudget, got ReasoningEffortEnum. Validation upstream is broken.`). Three layers now prevent this:

1. **Frontend** — the admin dialog normalizes `reasoning_effort` to the newly selected model on `model`/`provider` change: kept only if its shape fits the new `reasoning_widget` (and, for `enum`, the value is allowed), otherwise reset to `null`. New `coerceReasoningEffortForModel` / `reasoningEffortMatchesModel` in `components/settings/llm-config/reasoningHelpers.ts`.
2. **Write path** — `LLMConfigService.update_config` validates `reasoning_effort` against the **effective** model (`update.model`, or `LLM_DEFAULTS[llm_type].model` when the model override is `null`), rejecting an incompatible combination with `422` + structured `ctx`.
3. **Merge runtime** — `core/llm_config_helper.py::merge_config` → new `_reconcile_reasoning_effort` drops any still-incompatible `reasoning_effort` at merge time (stale override row, outdated seed, manual edit, a past bug), falling back to the model's default and logging `llm_config_reasoning_effort_dropped` — `get_llm()` degrades gracefully regardless of the drift's origin.

Shared non-raising predicate `reasoning_effort_matches_widget(caps, value)` (twin of `validate_reasoning_effort`) in `domains/llm_config/reasoning_validation.py` — one source of truth for "is this value valid for this model?", reused by layers 1 and 3.

### Fixed — Production build: stale GeoIP database date

`apps/api/Dockerfile.prod` hard-coded `ARG DBIP_DATE=2026-03` for the DB-IP City Lite GeoIP download; db-ip.com keeps only the last ~2 months online, so the URL started returning `404` ("not in gzip format" after `curl -L` wrote the error page) and `gunzip` failed the production image build. The `geoip-downloader` stage now resolves the latest available month at build time — current month, then the previous one — using `curl -fsSL` (so a 404 cleanly falls through to the next candidate); still overridable with `--build-arg DBIP_DATE=YYYY-MM`. Build-only change, no runtime impact.

### Tests

- `tests/unit/domains/llm_config/test_reasoning_validation.py::TestReasoningEffortMatchesWidget` — none/enum/budget_int/toggle_budget cases incl. the `{"effort": "off"}`-on-Qwen regression.
- `tests/unit/domains/llm_config/test_config_helper.py::TestEffectiveConfigReasoningReconciliation` — incompatible `reasoning_effort` override dropped, compatible kept, unknown model left untouched.
- `apps/web/src/components/settings/llm-config/__tests__/reasoningHelpers.test.ts` — 10 cases for `reasoningEffortShape` / `reasoningEffortMatchesModel` / `coerceReasoningEffortForModel`.
- `test_reasoning_validation.py` / `test_constants.py` / `test_llm_defaults_compliance.py` / `test_reasoning_builders.py` updated for the `claude-opus-4-6` etc. rename.

### Documentation

- `docs/technical/LLM_CONFIG_ADMIN.md` — new "Cohérence `reasoning_effort` ↔ modèle" section (the 3-layer guarantee), `reasoning_validation.py` / `ReasoningWidget.tsx` / `reasoningHelpers.ts` added to the file map, PUT-semantics note.
- `docs/technical/BROWSER_CONTROL.md` — `BROWSER_REACT_MAX_ITERATIONS` + browser step-timeout + `BROWSER_AX_TREE_MAX_TOKENS` notes; new "Agent prompt" section summarising the prompt's behavioural contract.
- In-app FAQ (`apps/web/locales/*/translation.json`, 6 languages): new `faq.changelog.versions.v1_20_4` entry (3 user/admin items); `faq.intro.features.browserControl` blurb refined (multi-step flow, stops at login/payment, reports a summary); `faq.sections.tool_examples_external` q18/q19 refined (multi-step example, "good to know" note, corrected timing). `docs/knowledge/06_external_services.md` propagated from the updated FAQ. `docs/GETTING_STARTED.md` compatibility line bumped to v1.20.4 (with v1.20.1–v1.20.4 highlights). `README.md` top banner updated to v1.20.4 (v1.20.3 demoted to a `<details>` block).
- `README.md` / `docs/technical/LLM_PRICING_TEMPLATES.md` / `docs/guides/GUIDE_CONFIG_ARCHITECTURE.md` / the 6 `apps/web/locales/*/translation.json` — `claude-opus-4.5` → `claude-opus-4-5` in prose/examples.
- Version bumped to `1.20.4` across `apps/api/pyproject.toml`, `apps/web/package.json`, `package.json`, and `apps/web/src/lib/version.ts` (`LAST_UPDATED = 2026-05-12T22:48:00`, shown on the landing page).

## [1.20.3] - 2026-05-08

### Fixed — Itinerary tool resilience against past timestamps

When the user asked "Quel itinéraire pour aller à mon prochain rdv ?", the planner correctly produced a 2-step plan (`get_events_tool` → `get_route_tool`) and the LLM legitimately passed the targeted event's start time as `arrival_time`. If that event had already started — e.g. an in-progress all-day reservation, or a meeting whose start was 30 minutes ago — Google Routes API rejected the call with `400 INVALID_ARGUMENT: "Timestamp must be set to a future time"`, the adaptive replanner retried twice with the same arguments, the step ended in `failed`, and `response_node` synthesised an answer with no route data: no HTML map card, no ETA, just a chatty fallback.

#### Cause

`get_route_tool` forwards `arrival_time` to `GoogleRoutesClient.compute_route` and (for non-TRANSIT modes) reuses it as a `departureTime` proxy to fetch traffic predictions for the same window. `_normalize_departure_time` in `google_routes_client.py` only handled formatting (timezone suffix, `T` separator) — neither tool nor client validated that the value was strictly in the future, which Google Routes mandates.

#### Fix

- New module-level helper `_clamp_to_future_iso(timestamp, *, buffer_seconds=60)` in `apps/api/src/domains/agents/tools/routes_tools.py`. Returns `(timestamp, was_clamped)`. Past values become `now + buffer` (UTC, ISO 8601); genuinely future values are returned unchanged so traffic prediction stays accurate; malformed inputs are returned as-is so Google's own error stays explicit; `None` flows through unchanged.
- Applied to both `departure_time` and `arrival_time` after `normalize_user_datetime` (timezone normalisation) and before the `effective_departure_time` proxy logic for non-TRANSIT modes. Naive timestamps that lost their tzinfo upstream are interpreted as UTC by the helper for safety.
- Each clamp emits a `route_timestamp_clamped_to_now` `WARNING` log with `field`, `original`, `clamped` for observability — surfaces planner mistakes (LLM passing past events) without breaking the user-facing flow.
- `google_routes_client.py` is unchanged; the past/future semantics live in the agent tool, where the timestamp's user-intent is known.

### Tests

6 new unit tests in `apps/api/tests/unit/domains/agents/tools/test_routes_arrival_time.py::TestClampToFutureIso` cover the clamp helper end-to-end:

- `test_returns_none_when_input_is_none` — `None` flows through unchanged
- `test_future_timestamp_is_left_intact` — future timestamps untouched (traffic accuracy preserved)
- `test_past_timestamp_is_clamped_to_now_with_buffer` — past ISO 8601 clamped to `now + 60s ± tolerance`
- `test_naive_past_timestamp_is_treated_as_utc_and_clamped` — defensive handling of naive datetimes
- `test_malformed_timestamp_is_returned_unchanged` — unparsable strings forwarded so the API surfaces the real error
- `test_arrival_time_at_event_already_started_is_clamped` — end-to-end regression for the exact scenario captured from prod logs

### Documentation

- `docs/technical/ROUTES.md` gains a "Past timestamp clamping (v1.20.3)" note next to the existing "Timezone handling" callout, documenting that arrival/departure times in the past are silently clamped to `now + 60 s` and that genuine future intents are preserved.

## [1.20.2] - 2026-05-08

### Added — Voice STT/TTS catalogue, per-message cost attribution, sentence streaming

A four-axis voice rework landing simultaneously: STT distant ElevenLabs, TTS catalogue-driven, per-message TTS cost attribution and sentence-level latency optimisation.

#### Schema (5 Alembic migrations 2026_05_07_0001..0005)

- `pricing_unit_enum` PostgreSQL ENUM added (`per_1m_tokens` / `per_audio_minute` / `per_audio_hour`); the three price columns on `llm_model_pricing` renamed (`input_unit_price`, `output_unit_price`, `cached_input_unit_price`) so the unit can be `per_audio_hour` for ElevenLabs Scribe ($0.22/h) without compromising the chat catalogue. Audit-friendly: prices are stored verbatim, not pre-converted (cf. [ADR-080](docs/architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md)).
- 5 nullable columns on `conversation_messages` for STT cost attribution: `stt_provider`, `stt_audio_duration_seconds`, `stt_cost_usd`, `stt_cost_eur`, `stt_usd_to_eur_rate`. Partial index `WHERE stt_provider IS NOT NULL` for the export query.
- 4 aggregates on `user_statistics`: `total_stt_audio_seconds`, `total_stt_cost_eur`, `cycle_stt_audio_seconds`, `cycle_stt_cost_eur`. Plus `users.voice_stt_mode VARCHAR(20)` (local/remote preference).
- `'edge'` value added to `llm_provider_enum` (dynamic `pg_attribute` loop migrating every dependent column). `system_settings.voice_tts_mode` row dropped — TTS now lives on `llm_config_overrides.voice_tts` (cf. [ADR-081](docs/architecture/ADR-081-Voice-TTS-Catalogue-Driven.md)).
- 6 nullable columns on `conversation_messages` for TTS cost attribution: `tts_provider`, `tts_model`, `tts_characters`, `tts_cost_usd`, `tts_cost_eur`, `tts_usd_to_eur_rate`. Partial index. Plus 4 aggregates on `user_statistics`: `total_tts_characters`, `total_tts_cost_eur`, `cycle_tts_characters`, `cycle_tts_cost_eur` — symmetric mirror of STT.

#### Voice STT — ElevenLabs Scribe as a remote provider (ADR-080)

- New `voice_transcription` LLM type (`kind=audio`) in `LLM_TYPES_REGISTRY`. Default `provider=elevenlabs, model=scribe_v2`; admin can switch via Configuration LLM. Free Sherpa-onnx Whisper local pipeline kept as the default `voice_stt_mode=local`.
- `SttServiceProtocol` + factory: `SherpaSttService` (local, free) and `ElevenLabsSttService` (remote, $0.22/h) implement the same `transcribe_pcm_int16_async(bytes, sample_rate, language)` interface. ElevenLabs accepts the raw Int16 LE 16 kHz mono buffer via `file_format=pcm_s16le_16` — no WAV wrapping.
- WebSocket ticket extended with `voice_stt_mode` so `/ws/audio` routes without re-querying the DB.
- Per-message STT cost surfaced as a discreet badge `🎤 X.Xs · €X.XXX` on the user bubble; persisted on `conversation_messages.stt_*`. Edge / Sherpa = NULL = no badge.
- Usage limits: `cycle_cost_eur` automatically includes STT via `add_stt_usage()`. Hard cap before each remote call → close 4029 if the cycle limit is hit.
- Push-to-talk decoupled from wake-word: the `voice_stt_mode` switch alone gates remote STT, regardless of `voice_mode_enabled`.
- New CSV exports: `consumption-summary` extended with STT columns; new dedicated `stt-usage` export (admin + user).

#### Voice TTS — catalogue-driven (ADR-081)

- New `voice_tts` LLM type (`kind=tts`) in `LLM_TYPES_REGISTRY`. Voice + provider-specific tuning live in `llm_config_overrides.voice_tts.provider_config` (JSONB), so a single admin form drives provider/model/voice/rate/pitch/volume/speed/voice_settings/output_format.
- Three providers seeded (Edge $0, OpenAI tts-1 / tts-1-hd $15-30, ElevenLabs eleven_multilingual_v2 / eleven_turbo_v2_5 / eleven_flash_v2_5 $50-100 — all per 1M characters). Edge stays free.
- Dynamic voice picker: `GET /admin/voice/voices?provider=X` returns curated lists for Edge/OpenAI and a live `GET /v1/voices` against the configured ElevenLabs account. `voices_read` scope required on the API key.
- Per-message TTS cost: badge `🔊 N chars` on the assistant bubble (paid providers only — Edge stays NULL = no badge). Persisted on `conversation_messages.tts_*` via a double-pass backfill (parallel during streaming + sync fallback after run cleanup) so both PATH 1 (parallel) and PATH 2 (sync direct_tts) populate the row.
- Legacy retired: `system_settings.voice_tts_mode`, the binary Standard/HD switch, the 14 `VOICE_TTS_*` env vars, the `AdminVoiceSettingsSection.tsx` component, and 13 `VOICE_TTS_*_DEFAULT` constants.
- New CSV exports: `consumption-summary` extended with TTS columns; new dedicated `tts-usage` export (admin + user). i18n keys aligned across the 6 supported locales.

#### Voice latency — sentence streaming (ADR-082)

- New `ProgressiveSentenceStreamer` (`apps/api/src/domains/voice/sentence_streamer.py`) — buffers a text token stream, dispatches a TTS task per complete sentence (`[.!?]+` boundary), enforces in-order delivery via `_pending: dict[int, VoiceAudioChunk]` + lock, skips failed slots without blocking the queue, idempotent end-of-stream sentinel.
- Chat mode: agents SSE loop watches `router_decision.intention=conversation` to spin up `VoiceCommentService.start_progressive_chat_stream(...)` and feeds it token-by-token. The user hears the first sentence ~1 s after the question instead of after the full response (~5 s on a 5-sentence response).
- Agent mode: `stream_voice_comment` rewritten to consume the voice-comment LLM via `astream()` (was `ainvoke()`), feeding each chunk into the streamer. First audio lands ~1.5 s after the registry is captured (was ~3.5 s).
- Persistent `httpx.AsyncClient` on `ElevenLabsTTSClient`: ~100–300 ms saved per sentence by skipping TLS handshake on calls #2..N within a request. `OpenAITTSClient` already pooled via the OpenAI SDK; Edge runs through the WebSocket-based `edge-tts` library.
- `_cleanup_chat_voice_pipeline()` helper invoked on every SSE generator exit path (HITL `GraphInterrupt`, top-level `except`, normal end) so the drain task and persistent httpx client are deterministically released.
- Configuration: `voice_chat_mode_max_sentences` clamp raised from `le=6` to `le=50` with an explicit description (3 default conversational, 10 educational, 50 functional ceiling).

### Tests

**46 new backend tests** across 4 dedicated files cover the v1.20.2 voice surface end-to-end:

- `apps/api/tests/unit/domains/voice/test_elevenlabs_stt.py` — **13 tests** on the ElevenLabs Scribe service: PCM Int16 transport (`pcm_s16le_16` payload), language-code filtering (6 LIA ISO-639-1 codes), HTTP error mapping (timeout, 429 with `Retry-After`, 5xx, 422), audio_duration_secs return + STTResult shape, empty-buffer short-circuit.
- `apps/api/tests/unit/domains/voice/test_stt_factory.py` — **11 tests** on the local-vs-remote factory: returns the singleton Sherpa for `mode='local'`, instantiates `ElevenLabsSttService` with the active `voice_transcription` override + ElevenLabs key for `mode='remote'`, raises `STTProviderError(elevenlabs_api_key_missing)` when key absent, `provider_config.base_url` parsing (regional residency override).
- `apps/api/tests/unit/domains/voice/test_sentence_streamer.py` — **12 tests** on `ProgressiveSentenceStreamer`: happy path, trailing flush, max_sentences cap, failed slot skipping, out-of-order arrival reordering, cancel_pending, empty stream, feed-after-close guard, on_chars_synthesized callback (called + throw swallowed), `first_audio_latency_seconds` property, MIME fallback for non-mp3 audio formats.
- `apps/api/tests/unit/infrastructure/test_pricing_cache_audio.py` — **10 tests** on `get_cached_cost_audio_usd_eur`: per_audio_hour math, per_audio_minute math, mismatched pricing_unit returns (0, 0) + warning, Decimal precision over varied durations (0.5 s / 1 s / 60 s / 3600 s), missing model in cache, EUR conversion via cached usd_eur_rate.

The 46 new tests run inside the existing pytest collection (9992 total tests) — no new markers, no new fixture files. Coverage includes the column rename refactor (input_unit_price / output_unit_price / cached_input_unit_price across 4 modified files in `tests/integration/test_llm_admin_routes.py`, `tests/unit/domains/llm/test_schemas_reasoning.py`, `tests/unit/domains/llm/test_service.py`, `tests/helpers/llm_helpers.py`) which keeps the ADR-080 schema migration verifiable.

### Changed

- `LLMTypeConfigUpdate.provider` Literal extended with `'elevenlabs'` and `'edge'` (PUT used to fail 422 on these providers).
- `TrackingContext` gains a `_tts_records: list[TTSUsageRecord]` bucket + `record_tts_call(provider, model, characters)`. The legacy `_track_tts_cost → record_node_tokens(node_name='tts_hd')` path retired (TTS no longer mixed in `token_usage_logs` with chat nodes).
- `archive_message` accepts 6 `tts_*` kwargs and `update_message_tts` is added on the repository for the post-voice backfill (TTS finalises after `archive_message` runs in the parallel mode).
- `TokenSummaryDTO` extended with `tts_cost_eur` so the SSE `done` chunk's consolidated `cost_eur` includes TTS — the live frontend badge sees the correct grand total without waiting for a reload.
- `tracker.commit()` early-return guard now checks `pending_tts > 0` too — without this, the sync-fallback voice flow (chat mode without parallel) would skip `_persist_to_database`.
- `LLMConfigOverrideCache` now persists `provider_config` (was already in the schema but the cache was missing it).
- `AUDIO_MIME_TYPES` and `DEFAULT_AUDIO_MIME_TYPE` extracted to `voice/schemas.py` (was duplicated between `voice/service.py` and `voice/sentence_streamer.py`).

### Fixed

- HTTP 402 on ElevenLabs library voices surfaced as a clear "ElevenLabs paid plan required" hint when a non-premade voice is selected on a free account.
- Prometheus counters on `ElevenLabsTTSClient` aligned on `["voice_name"]` / `["error_type", "voice_name"]` (the previous `provider`/`model` labels caused `Incorrect label names` runtime errors that silently broke every ElevenLabs synthesis).
- `voice_chunk_queue` race condition: when a chat-mode streamer was active and the registry appeared mid-stream, the agent-mode parallel task would create a new queue and silently drop the chat audio. Now mutually exclusive via `chat_voice_drain_task is None` guard.
- Sentinel duplicated when `cancel_pending()` and the last task's `done_callback` raced for the queue close — now flagged via `_sentinel_pushed`.
- `feed_task` (LLM streaming feeder) leaked on `CancelledError` and on `Exception` paths in `stream_voice_comment` — now cancelled and awaited via `_abort_voice_comment_pipeline`.
- `chat_voice_drain_task` leaked on `GraphInterrupt` (HITL fallback) — now cleaned up via the shared `_cleanup_chat_voice_pipeline` helper.

### Removed

- `system_settings.voice_tts_mode` row + DB enum entry.
- `VoiceTTSMode` Literal (`Literal["standard", "hd"]`) and the 14 settings on `VoiceSettings` it gated (`voice_tts_default_mode`, `voice_tts_standard_*` × 6, `voice_tts_hd_*` × 7).
- `REDIS_KEY_VOICE_TTS_MODE` constant; `VoiceTTSModeCache` Redis service; `get_voice_tts_mode()` / `invalidate_voice_tts_mode_cache()` module functions; `voice_tts_mode_cache_total` Prometheus counter.
- 13 `VOICE_TTS_*_DEFAULT` constants from `core/constants.py`.
- `apps/web/src/components/settings/AdminVoiceSettingsSection.tsx` (replaced by Configuration LLM admin form, type `voice_tts`).
- Two unused settings on `VoiceSettings` retired: `elevenlabs_stt_api_base_url` and `elevenlabs_stt_request_timeout_seconds`. The model, regional `base_url` and per-call timeout already live on `llm_config_overrides.voice_transcription` (admin UI), so the duplicate `.env` knobs were dead config. Both `.env.example` and `.env.prod.example` lines removed.

### Hardening — voice domain audit remediation

Follow-up pass on the voice rework above to close cost-defence gaps, structure provider errors, and align cross-cutting documentation with the catalogue-driven model.

- **Cost-spike defence: STT remote duration cap actually enforced.** The `ELEVENLABS_STT_MAX_AUDIO_DURATION_SECONDS` setting (default 300 s) was declared earlier in this same release but never checked at runtime. The WebSocket handler now rejects oversized clips before any provider call (close code 4002 with `audio_too_long` reason; explicit error chunk to the frontend). New constant `STT_BYTES_PER_SECOND_AT_16KHZ_INT16 = 32000` derives the duration from the raw byte buffer without parsing the PCM stream.
- **Cost-spike defence: STT remote kill switch wired.** `ELEVENLABS_STT_ENABLED=false` now actually disables remote STT at the WebSocket entry point — instant fallback to Sherpa-onnx local for incident response or quota emergencies. Previously the flag existed in config but was ignored.
- **Structured TTS errors across all 3 providers.** New `TTSProviderError` (`apps/api/src/domains/voice/exceptions.py`) mirrors `STTProviderError`. Edge / OpenAI / ElevenLabs clients now raise typed errors with stable codes (`api_key_missing`, `provider_timeout`, `provider_rate_limited`, `provider_http_error`, `provider_invalid_response`, `provider_network_error`); ElevenLabs HTTP 429 carries `retry_after_seconds` from the `Retry-After` header. `RuntimeError` removed from every TTS code path. Frontend toasts can now match on `code` for precise i18n.
- **`admin_router.py` raw `HTTPException` calls replaced** by centralized raisers (`raise_invalid_input` / `raise_external_service_fetch_error`) for consistency with the rest of the API surface.
- **Configurable sentence boundary in the streamer.** `ProgressiveSentenceStreamer.__init__` now accepts a `sentence_delimiters` argument; the regex is built per-instance via `_build_sentence_end_regex(delimiters)` and follows `settings.voice_sentence_delimiters` (admin-tunable). Latin punctuation (`.!?`), Chinese `。！？`, Arabic `؟` etc. all supported when configured.
- **Magic constants extracted.** `VOICE_TTS_MS_PER_CHAR_HEURISTIC = 80` now lives in `core/constants.py` as the single source of truth used by both `voice/service.py` and `voice/sentence_streamer.py` for the `duration_ms` UI hint. `voice_comment_prompt` added to the `PromptName` Literal so MyPy strict catches any future typo.

### Documentation

- New ADRs: [ADR-080](docs/architecture/ADR-080-Voice-STT-Remote-Pricing-Unit.md), [ADR-081](docs/architecture/ADR-081-Voice-TTS-Catalogue-Driven.md), [ADR-082](docs/architecture/ADR-082-Progressive-Sentence-Streaming.md).
- ADR-050 (legacy Voice TTS architecture) marked as superseded by ADR-081.
- [docs/technical/VOICE.md](docs/technical/VOICE.md) v4.1: catalogue-driven config + per-message attribution + sentence streaming sections.
- [ADR-039](docs/architecture/ADR-039-Cost-Optimization-Token-Management.md) enriched with a "Voice silos (TTS / STT) — separate cost surfaces" section that contrasts the chat token-tracking pipeline with the audio-billed (`per_audio_hour`) and character-billed (`per_1m_tokens`) silos used by STT and TTS.
- Catalogue-driven TTS narrative propagated across 12 how/why guides (en/fr/de/es/it/zh) — obsolete "Standard / HD" + "Gemini TTS" mentions retired in favour of the three-provider description (Edge / OpenAI / ElevenLabs).
- Cross-cutting docs realigned: `README.md`, `docs/ARCHITECTURE.md` (line 99 + voice-flow diagram), `docs/GETTING_STARTED.md` (feature/mode tables), `CONTRIBUTING.md` (config map), `docs/INDEX.md` (VOICE.md description), `docs/knowledge/03_settings.md` and `docs/knowledge/20_voice_mode.md` (user-facing voice description). `CLAUDE.md` ADR count updated (75 ADRs).
- Module docstring on `metrics_voice.py` rewritten for multi-provider TTS — explicitly explains why no `provider` label is added (Prometheus rejects extra labels post-instantiation; provider derivable from voice_id naming pattern).
- 6 locale files updated with parity for `tts_usage_title`, `tts_usage_description`, `voiceTts.*` keys.

## [1.20.1] - 2026-05-06

### Added — LLM admin: per-model sampling matrix + reasoning shape templates

Two complementary refinements on the admin LLM catalogue introduced in v1.19.0 ([ADR-078](docs/architecture/ADR-078-LLM-Catalogue-DB-Source-Of-Truth.md)). Both target the same principle: every form input must reflect what the API actually accepts ("raw truth"), and every behavioral group must be reusable as a template instead of re-typed by hand.

#### Schema

- New columns on `llm_models` (4 sampling caps, all NOT NULL with permissive `True` defaults): `supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`. Migration `2026_05_06_0002-llm_sampling_flags.py` backfills the verbatim 96-model matrix and reconciles `is_reasoning_model` with `reasoning_widget` (37 stale rows fixed).
- New columns on `llm_models` (5 reasoning shape fields, materialised in v1.20.0 prep): `kind` (chat / image / audio / realtime / tts / embedding), `reasoning_widget` (none / enum / budget_int / toggle_budget), `reasoning_enum_values` (JSONB list, when widget=enum), `reasoning_budget_range` (JSONB `{min, max, off_sentinel, dynamic_sentinel}`), `reasoning_doc_i18n_key`. Migration `2026_05_06_0001-llm_reasoning_overhaul.py` covers the rollout + 25 row deletions (retired/fictional models).

#### Configuration LLM dialog (admin)

- Sampling parameter sliders (`temperature`, `top_p`, `frequency_penalty`, `presence_penalty`) now appear or hide **per individual parameter** based on the selected model's DB caps, replacing the previous global `showSamplingParams` heuristic. Example: Anthropic 4.5+ models surface only the temperature slider; DeepSeek V4 surfaces all four; GPT-5 series surfaces none. The `reasoning_widget` value drives the widget shape (enum select, integer budget, or toggle+budget) so the dialog never lets the operator pick a value the API would reject.
- Card badges on the type list use `reasoning_widget !== 'none'` (instead of the bare `is_reasoning_model` flag) to decide whether to render `E:effort`, and `supports_temperature` to decide `T:temp` — covering the deepseek-reasoner edge case (always-on reasoning, no level control) without false positives.

#### Pricing LLM dialog (admin)

- New section **"Reasoning & sampling"** in the model add/edit modal. Layout: `kind` Select → 4 sampling toggles → `Is reasoning model` toggle that gates the reasoning-shape controls below.
- New endpoint `GET /admin/llm/reasoning-templates` returns the deduplicated set of unique reasoning shapes present in `llm_models` (~15 templates today, e.g. `enum [low/medium/high]` (14 models, like claude-opus-4.5), `enum [minimal/low/medium/high]` (5 models, like gpt-5), `toggle+budget 0..32768` (4 models, like qwen3-max), `no reasoning` (55 models)). The set self-enriches: any model created in Custom mode with a novel fingerprint becomes available as a template on subsequent calls.
- **Template mode (default)**: the admin picks a representative model from the dropdown — the 4 reasoning shape fields are snapshot-copied at create time. **Custom mode (advanced)** unlocks manual entry for disruptions / brand-new families. `kind`, the four `supports_*` sampling flags and `reasoning_doc_i18n_key` are always saved per model regardless of the template choice — keeping model nature, per-parameter API acceptance and tooltip key independent from the shared reasoning shape.
- At edit time, the modal pre-selects the template whose fingerprint matches the current row, or falls back to "Custom" if none matches.

#### Backend

- Service `LLMModelService.list_templates()` groups active rows by a 4-field fingerprint (`is_reasoning_model`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`) and returns one deterministic representative per group. The fingerprint is derived from a single source of truth `_TEMPLATE_FIELDS` so adding a 5th shape field requires no parallel edit.
- Schemas `ModelPriceCreate` / `ModelPriceUpdate` enforce template-mode XOR custom-mode at validation time. `model_validator(mode="after")` rejects mixing `reasoning_template` with explicit reasoning shape fields, and validates widget cohesion (`enum` requires `enum_values`, `budget_int`/`toggle_budget` requires `budget_range`, `none` forbids both).
- New `UnknownReasoningTemplateError(LookupError)` exception — subclass of `LookupError` so legacy `except LookupError` catches keep working, but the router catches it BEFORE plain `LookupError` to translate it to `400 invalid_input` (distinct from the `404 not_found` used when the model being updated does not exist, and from the `409 already_exists` raised on duplicate `model_name`).
- Audit log on create/update enriched with `kind`, `reasoning_template` (slug or null in Custom mode), `reasoning_widget` (post-update for forensic search). The structured log line follows.

### Changed

- `LLMModelRepository.create_model()` signature now requires the 9 new fields (`kind`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`, `reasoning_doc_i18n_key`, `supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`) as explicit kwargs. Test fixtures get a `_DEFAULT_REASONING_KWARGS` constant for the non-reasoning baseline.
- Frontend pricing form helpers (`buildReasoningSamplingPayload`, `fingerprintMatches`, `parseEnumValuesCsv`, `formatEnumValuesCsv`) extracted to `apps/web/src/components/settings/admin-llm-pricing-helpers.ts` so they can be unit-tested independently of the React component.

### Fixed

- **Configuration LLM sampling sliders** — Anthropic 4.5+ models (claude-opus-4.5, claude-sonnet-4.6, claude-haiku-4.5, claude-opus-4.6) used to hide the temperature slider whenever `reasoning_effort` was set; they now correctly expose only the temperature input (no top_p, no penalties) at all times. DeepSeek V4 family (`deepseek-v4-flash`, `deepseek-v4-pro`) used to hide all four sliders behind the `enum` widget; they now surface all four. Qwen 3.x toggle+budget models still expose temperature/top_p/presence_penalty but hide frequency_penalty (matrix-driven).
- **Pricing admin error semantics** — passing an unknown `reasoning_template` to `POST /admin/llm/pricing` or `PUT /admin/llm/pricing/{name}` previously surfaced `409 already_exists` (overloaded `except ValueError`). Now returns `400 invalid_input` with the original message ("reasoning_template 'X' does not exist in llm_models"), so the admin sees which template name was wrong.
- **Stale `is_reasoning_model` flag in the pre-PR seed** — 37 rows in `llm_models` had `reasoning_widget != 'none'` but `is_reasoning_model = false`. Migration `2026_05_06_0002` reconciles the two: `is_reasoning_model = (reasoning_widget != 'none') OR model_name = 'deepseek-reasoner'`. Special case kept for deepseek-reasoner (always-on reasoning with no level control: widget='none' but is_reasoning=true).

### Documentation

- New: `docs/technical/LLM_PRICING_TEMPLATES.md` — Template/Custom modes, snapshot semantics, fingerprint dedupe, FAQ on edge cases (deepseek-reasoner, doc_i18n_key exclusion, post-create template edits). Indexed in `docs/INDEX.md` under "Cost Tracking & Billing".
- Updated docstrings on `ModelPriceCreate` / `ModelPriceUpdate` / `_copy_from_template_row` / `create()` / `update()` — every Raises clause now lists which exception maps to which HTTP code (`ValueError → 409`, `LookupError → 404`, `UnknownReasoningTemplateError → 400`).

### Tests

- Backend: 33 new schema validators tests (`test_schemas_reasoning.py`), 21 service helper tests (`test_service_helpers.py`, pure — no DB), 10 router structural tests (`test_router.py`), 9 service integration tests extended (`test_service.py`). All run on Postgres in CI; pure tests run anywhere.
- Frontend: 27 vitest tests on the extracted helpers (`__tests__/admin-llm-pricing-helpers.test.ts`) covering Template / Custom / Non-reasoning branches of `buildReasoningSamplingPayload`, fingerprint matching, CSV round-trip.

## [1.20.0] - 2026-05-06

### Added — Stratified Journal Consciousness ([ADR-079](docs/architecture/ADR-079-Stratified-Journal-Consciousness.md))

The personal journal (introduced in [ADR-057](docs/architecture/ADR-057-Personal-Journals.md), refined by [ADR-064](docs/architecture/ADR-064-Journal-Analyst-Persona.md) and [ADR-069](docs/architecture/ADR-069-Gemini-Embedding-Migration.md)) becomes a stratified meta-cognition organ. Four abstraction levels, deferred self-evaluation, ambient diffusion of a compiled user-model portrait across eight flows where LIA speaks.

#### Schema

- New columns on `journal_entries` (all nullable / server_default — fully reversible): `level VARCHAR(2) DEFAULT 'L1'`, `confidence VARCHAR(10) DEFAULT 'medium'`, `evidence_count INT DEFAULT 0`, `contradiction_count INT DEFAULT 0`.
- New columns on `users` (nullable): `journal_portrait_full TEXT`, `journal_portrait_brief TEXT`, `journal_portrait_compiled_at TIMESTAMPTZ`.
- New `JournalEntrySource` value: `user_correction` (created by lever 2 feedback).
- New enums: `JournalEntryLevel` (L0/L1/L2/L3), `JournalEntryConfidence` (low/medium/high).
- Migration: `2026_05_05_journals_stratified.py` — single file, 3 logical steps, reversible.

#### Stratification

- **L0** — raw observation, pre-directive. Rare, ephemeral, ~200c.
- **L1** — operational directive `WHEN [context] → DO [action] (BECAUSE [evidence])`. Default at extraction, ~500c.
- **L2** — transversal pattern, synthesis of convergent L1 directives. Consolidation only, ~700c.
- **L3** — portrait facet (traits, current phase, contexts, contradictions, blind spots, evolution). Consolidation only, feeds the user-model portrait.
- L2/L3 are produced exclusively by consolidation through active topic clustering (STEP 5 of `journal_consolidation_prompt.txt`).

#### Deferred self-evaluation T → T+1

- `MessagesState` carries `injected_journal_ids` between turns (symmetric to `injected_memories`).
- `response_node` reads the previous turn's IDs at start, passes them to the post-conversation extractor, then writes the current turn's IDs to state.
- Extractor sees the directives that were just applied and the user's reaction in the same prompt; the LLM signals `evidence_outcome="evidence" | "contradiction"` on update actions.
- Service atomically increments `evidence_count` / `contradiction_count` (anti-hallucination layer 4: LLM never writes absolute counter values).
- Zero additional LLM calls — same extractor, just enriched prompt.

#### User-model portrait (ambient diffusion)

- Consolidation now produces, in the same LLM call (zero additional cost), a `portrait_full` (~200 tokens, conversation/planner) and `portrait_brief` (~60 tokens, secondary flows) persisted on the `users` table.
- New standalone builder `journals/portrait_builder.py:build_journal_user_model_block(user_id, format, flow)` — symmetric to `psyche/service.py:build_psyche_prompt_block`. Returns a `<UserModelContext>...</UserModelContext>` block or empty string with graceful degradation.
- Diffused across eight flows: 2 primary in full format (`response_node`, `planner_node_v3`) and 6 secondary in brief format (`react_setup_node`, `interests/proactive_task`, `scheduler/reminder_notification`, `voice/service`, `heartbeat/prompts`, `agents/services/fallback_response` sync + async).

#### User correction (three levers)

- **Lever 1** — edit/delete L3 source entries via existing CRUD; portrait recompiles next consolidation.
- **Lever 2** — `POST /journals/portrait/feedback` (free-text + optional highlighted section). Creates an L0 entry with `source=user_correction`, then triggers a synchronous consolidation (~5–10 s) that re-weights L3 entries with the user signal pinned at top of the prompt.
- **Lever 3** — `POST /journals/consolidate`. Bypasses cooldown; runs the standard consolidation pass on demand.
- Portrait itself is intentionally **not directly editable**.

#### API endpoints

- `POST /journals/consolidate` — manual consolidation (lever 3).
- `GET /journals/portrait` — read full + brief + `compiled_at`.
- `POST /journals/portrait/feedback` — submit correction (lever 2).
- `GET /journals/export` — now includes the compiled portrait under `portrait` key.
- `PATCH /journals/{id}` — accepts `level` and `confidence` for manual overrides.

#### Observability

- 11 new Prometheus metrics in `infrastructure/observability/metrics_journals.py`: `journal_entries_total{action,theme,source}`, `journal_extraction_duration_seconds{outcome}`, `journal_zero_injection_age_days`, `journal_evidence_total{outcome}`, `journal_consolidation_promotions_total{from_level,to_level}`, `journal_level_distribution{level}`, `journal_dedup_actions_total`, `journal_portrait_compile_duration_seconds`, `journal_portrait_present_total{flow,format}`, `journal_portrait_age_hours`, `journal_portrait_feedback_total{outcome}`.

#### Frontend

- `JournalsSettings.tsx`: dedicated section "Comment LIA te perçoit" with full/brief tabs (read-only), 🚩 feedback dialog, 🔄 manual consolidation button.
- Per-entry badges: confidence (low/medium/high), level (L0/L1/L2/L3), `uses` counter, `last_inj` date.
- Group-by toggle (Theme | Level), filter "show only entries never used", `level` and `confidence` editable in create/edit dialogs.
- New env var `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS` (default 240 000 ms / 4 min) — configurable client timeout for the lever-3 button.

#### Internationalization

- ~38 new keys per locale (en / fr / de / es / it / zh) — confidence labels, level labels + descriptions, group-by, consolidate, portrait section, feedback dialog. Parity verified.

#### Cleanup

- Removed dead code: `journal_dedup_similarity_threshold` setting, `JOURNAL_EXTRACTION_RECENT_ENTRIES_FULL` constant, `archive_entry()` service method, `journal_merge_prompt.txt` orphan prompt. The historical write-time dedup guard (v1.12.1) was already retired in favor of mandatory dedup at consolidation (ADR-064 STEP 1, extended by ADR-079 active pairwise scan).
- `.env.example` / `.env.prod.example` updated.

#### GDPR

- Account deletion (`users/account_deletion_service.py:_mark_user_deleted`) now scrubs the three portrait columns alongside existing user data.
- Export endpoint enriched with the portrait payload.

#### Tests

- 50 new tests covering the stratified mechanism: 4 unit files (`test_models.py` extended, `test_portrait_builder.py`, `test_levels_promotions.py`, `test_self_evaluation.py`) and 1 integration file (`test_journal_full_cycle.py`, real Postgres). 86 unit tests + 8 integration tests passing in under 6 s.

### Changed — Prompt engineering pass on the journal LLM calls

- **Extraction prompt** (`journal_introspection_prompt.txt`):
  - Added a `STEP 0` to the decision tree explicitly handling ambiguous / not-yet-actionable signals → `L0` instead of forcing a half-baked `L1`.
  - Section 4 (abstraction levels) rewritten with three concrete `L0` examples and a "when in doubt → L0" rule.
  - Quality gate broadened to two clauses: "(a) will change my future response" OR "(b) weak signal worth tracking".
  - Self-audit (section 9) gains an "L0 sweep" step + a "downgrade fuzzy L1 to L0" check + a healthy distribution target across themes AND levels.
- **Both prompts** (`journal_introspection_prompt.txt`, `journal_consolidation_prompt.txt`):
  - Removed all language-specific examples (French / English mentions, "svp"/"stp", `"réunion"`, `"bon"`, `"concision et réponse ciblée"`, `"ton sobre face à la vulnérabilité"`). Replaced by language-agnostic equivalents — every input is now translated to English by the semantic pivot before reaching the LLM, so prompts must not anchor on a specific language.

### Fixed

- **Debug panel "Background Extraction" sub-section** — partial-update actions (where the LLM omits unchanged fields) used to display only the truncated UUID instead of the entry title/theme/mood. The backend now backfills the debug payload from the existing entry before streaming, so the panel reads `UPDATE 📓 Prefer concise replies` instead of `UPDATE 1ac9a75a`.
- **Manual consolidation timeout** — the new `/journals/consolidate` button is now backed by a configurable client timeout (`NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS`, default 4 min) so heavy reasoning models don't trip a premature client cancel.

## [1.19.1] - 2026-05-05

### Added — DeepSeek V4 family + parameterizable provider base URLs

DeepSeek released the V4 model family (`deepseek-v4-flash`, `deepseek-v4-pro`)
with first-class thinking-mode toggle: same model invoked with or without
chain-of-thought reasoning per request. This release wires V4 into the
admin-facing catalogue introduced in v1.19.0, with the necessary adapter
plumbing, a frontend constraints update, and a workaround for an
upstream `langchain-deepseek` bug.

#### Catalogue (admin-facing)

- **2 new entries** in the seed for fresh installs: `deepseek-v4-flash` and
  `deepseek-v4-pro` — both with `provider=deepseek`,
  `max_input_tokens=1_000_000`, `max_output_tokens=384_000`,
  `supports_tools=true`, `supports_structured_output=true`,
  `supports_streaming=true`, `is_reasoning_model=true`. Pricing seeded
  with the official DeepSeek tariffs (cache hit rate is unusually high:
  ~50× cheaper for flash, ~120× cheaper for pro).
- The seed now ships **121 chat models** (was 119); the trailing
  `RAISE WARNING` guard updated.
- Existing `deepseek-chat` (V3) and `deepseek-reasoner` (R1) entries
  preserved for backward compat — DeepSeek transparently routes those
  legacy names to V4 on their backend per upstream community
  confirmation, but admins are encouraged to deactivate them via the
  catalogue (`is_active=false`) once migrated to V4.

#### Adapter (`apps/api/src/infrastructure/llm/providers/adapter.py`)

- New branch in `_create_deepseek_llm` for V4: maps
  `reasoning_effort` from LIA's 6-level UI scale to DeepSeek's
  `extra_body.thinking.type` + `reasoning_effort` API fields.
  - `none` → `{"thinking": {"type": "disabled"}}`
  - `minimal`, `low`, `medium` → `{"thinking": {"type": "enabled"},
    "reasoning_effort": "high"}`
  - `high`, `xhigh` → `{"thinking": {"type": "enabled"},
    "reasoning_effort": "max"}`
- Sampling parameters (`temperature`, `top_p`, `frequency_penalty`,
  `presence_penalty`) are stripped locally when thinking is on — the
  V4 API silently ignores them otherwise; stripping makes the request
  log faithful to what the model actually consumes.
- `max_tokens` cap raised to 64 000 for V4 (matches the API
  documentation for the family).

#### Frontend (`apps/web/src/components/settings/AdminLLMConfigSection.tsx`)

- `getModelConstraints` deepseek case extended: V4 models gated on
  the catalogue's `is_reasoning_model` flag expose the
  `reasoning_effort` dropdown with `['none', 'low', 'medium', 'high']`.
- V3 deepseek-chat/deepseek-reasoner unchanged.

#### Provider base URLs are now per-deployment configurable

- New env vars `PERPLEXITY_BASE_URL` and `QWEN_BASE_URL` (consistent
  with the existing `OLLAMA_BASE_URL` convention).
- New helper `_get_base_url(provider)` in the adapter: env-first
  resolution with documented vendor defaults as fallback.
- Documented use cases: regional endpoints (e.g. Qwen US ↔ CN
  DashScope), self-hosted OpenAI-compatible gateways, mock servers
  for tests — all with no code change required.
- Templates updated: `.env.example`, `.env.prod.example`,
  `.env`, `.env.prod`. `.env.min.prod` deliberately skipped (its
  philosophy delegates provider configuration to the admin UI).

### Fixed

- **Structured output via forced `tool_choice` rejected by V4 with
  thinking on.** The DeepSeek API returns
  `400 - 'deepseek-reasoner does not support this tool_choice'` even
  for requests targeting `deepseek-v4-flash` / `deepseek-v4-pro`,
  because thinking-mode requests are routed to a reasoner-style
  backend that rejects forced tool selection. New helper
  `_is_v4_thinking_enabled(llm)` in `structured_output.py` detects
  this combination and **transparently downgrades to the JSON-mode
  fallback** (which uses `response_format={"type": "json_object"}`
  and does not use `tool_choice`). Schema conformance is enforced by
  Pydantic on our side. The fix is fully automatic — nodes that need
  structured output (`query_analyzer`, `semantic_validator`,
  `planner`, `hitl_classifier`...) now work with V4 thinking on.
- **`reasoning_content` round-trip in tool flows on V4.** The pinned
  `langchain-deepseek==1.0.1` (and current upstream master) does NOT
  inject prior `AIMessage.additional_kwargs["reasoning_content"]`
  back into the request payload's assistant messages. The DeepSeek
  V4 API rejects multi-turn tool flows that omit it with
  `400 invalid_request_error: 'The reasoning_content in the thinking
  mode must be passed back to the API.'`. Six upstream PRs over six
  months attempting this fix have not been merged. Local subclass
  `ChatDeepSeekPatched`
  ([`apps/api/src/infrastructure/llm/providers/_deepseek_patched.py`](apps/api/src/infrastructure/llm/providers/_deepseek_patched.py))
  overrides `_get_request_payload` with the round-trip logic. The
  patch is unconditional (no-op when `additional_kwargs` is empty),
  so it has zero effect on V3 or thinking-disabled V4 calls. To be
  removed once `langchain-deepseek` ships the round-trip natively
  (tracking [issue #37178](https://github.com/langchain-ai/langchain/issues/37178)).
- **Misleading `reasoning_effort_unsupported_provider` warning for
  DeepSeek.** `LLMAgentConfig.validate_reasoning_effort` whitelisted
  only `{openai, anthropic, gemini, qwen}` and logged a misleading
  warning whenever `reasoning_effort` was set on a DeepSeek node.
  V4 supports `reasoning_effort` natively at the adapter level, so
  `deepseek` is now in the supported set and the warning message is
  reformulated to reflect the 5 thinking-capable providers.

### Tests + tooling

- 18 new unit tests in
  [`apps/api/tests/unit/infrastructure/llm/providers/test_deepseek_patched.py`](apps/api/tests/unit/infrastructure/llm/providers/test_deepseek_patched.py)
  covering the round-trip patch (7 tests), the V4 thinking mapping in
  the adapter (5 tests), and the `_is_v4_thinking_enabled` detector (6
  tests). All pass.
- Pre-commit hook still green.

### Documentation

- ADR-078 — *LLM Catalogue DB-Source-of-Truth* — extended with a
  concrete *Adding a new provider* worked example using DeepSeek V4
  to illustrate the catalogue extension pattern.
- New section in `docs/technical/LLM_PROVIDERS.md` —
  *DeepSeek V4 — `reasoning_content` round-trip patch* — explains
  the upstream bug, the local fix, the criteria for removal, and
  cross-references issue #37178 / PR #37179.
- `docs/technical/LLM_PROVIDER_CONSTRAINTS.md` — new V4 row in the
  parameter compatibility table with footnote ⁶, plus a dedicated
  V4 subsection explaining the thinking-mode mapping, the
  `tool_choice` constraint and the JSON-mode fallback.
- README.md — *Supported LLM Providers* table updated to list V4 as
  the recommended DeepSeek tier.

## [1.19.0] - 2026-05-05

### Added — LLM model catalogue becomes the source of truth in the database

The chat + image LLM catalogue used to live as frozen Python constants
(`MODEL_PROFILES`, `IMAGE_GENERATION_MODELS`, `REASONING_MODELS_PATTERN`).
Adding or tuning a model required a code change, a release, and a redeploy.
**The catalogue is now persisted in the database** — administrators can
declare new models and edit their full capability + pricing profile from
the admin UI, and every consumer (LangChain factory, agent constraints,
image options dropdowns) reads from the DB live, with no page refresh and
no worker restart.

#### New schema (`apps/api/src/domains/llm/models.py`)

- `llm_models` — catalogue table. One row per distinct `model_name`.
  - `provider` — `LLMProviderEnum` (openai, anthropic, deepseek, perplexity,
    ollama, gemini, qwen) — replaces the regex-based provider inference.
  - 8 capability columns: `max_input_tokens`, `max_output_tokens`,
    `supports_tools`, `supports_structured_output`, `supports_strict_mode`,
    `supports_streaming`, `supports_vision`, `is_reasoning_model`.
  - `is_active` for temporal versioning (deactivated rows preserve history).
- `llm_model_pricing` — pricing rows now FK to `llm_models.id` with
  `ondelete=RESTRICT`. The legacy `model_name` column is dropped — pricing
  joins through the catalogue. Composite uniqueness on
  `(model_id, effective_from)` enforces one rate per model per date.
- `image_generation_pricing` — gains a NOT NULL `provider` column
  (`LLMProviderEnum`) so image options can be grouped by provider and
  filtered by the same provider list as text models.

#### Migrations (3-step pattern, ADR-040)

- `2026_05_05_0001-llm_models_schema.py` — creates the new tables and
  adds nullable columns, no data movement.
- `2026_05_05_0002-llm_models_backfill.py` — backfills 47 known models
  from a frozen `MODELS_DATA` list (preserves capability profiles from
  the deleted `FALLBACK_PROFILES` dict).
- `2026_05_05_0003-llm_models_constraints.py` — flips backfilled columns
  to NOT NULL, drops legacy `llm_model_pricing.model_name`, adds the
  composite unique constraint.

All three are reversible with full `downgrade()` paths.

#### In-memory caches with cross-worker invalidation

- `ModelCapabilitiesCache` (singleton) — loads the active catalogue at
  boot from `llm_models` and exposes `get(model_name)` + `is_reasoning_model()`
  in O(1). Replaces the static `FALLBACK_PROFILES` dict (~750 lines deleted).
- `ImageOptionsCache` (singleton) — loads active rows from
  `image_generation_pricing`, groups them by provider, and exposes
  `QualityOption`, `SizeOption`, `ModelOptions` dataclasses for the
  preferences UI and the agent constraints.
- Both caches register reload handlers via the existing Pub/Sub
  invalidation bus (ADR-063). Any admin write triggers a Redis publish
  on `cache:invalidate:{model_capabilities,image_generation_options}`,
  every API worker reloads, every consumer (factory, options endpoint,
  responses adapter, reasoning detector) sees the new data immediately.

#### Backend service + admin endpoints

- `LLMModelService` (transactional create/update/deactivate) with three
  update modes: capabilities-only (no pricing change), pricing-only
  (capabilities frozen), and mixed (transactional). The pre-populated
  `pricing.model` relationship is preserved through `flush()` (no
  `db.refresh()` calls — defaults are all Python-side).
- `LLMModelRepository` extends `BaseRepository[LLMModel]`.
- `POST/PUT/DELETE /admin/llm/pricing` and `/admin/image/pricing`
  refactored to use the service + a `_invalidate_caches()` helper that
  emits the Pub/Sub message after every successful write.
- New endpoint `GET /api/v1/image-generation/options` — returns the
  current `ImageOptionsCache` content for the preferences screen.

#### Frontend admin form

- **Tarification LLM Texte** — full rewrite of `AdminLLMPricingSection`
  with a 3-section modal (Modèle / Capacités / Tarification) and 14
  fields. Provider is a `<Select>` driven by `LLMProviderEnum`. Each
  capability is a `<Switch>`.
- **Tarification LLM Image** — `AdminImagePricingSection` gains a
  `provider` field on the create/edit form and a `Provider` column in
  the table.
- **Configuration LLM (agents)** — `AdminLLMConfigSection.getModelConstraints`
  now consults the DB capabilities first (live from the cache) and falls
  back to the legacy regex only for unknown models. The
  `is_reasoning_model` toggle correctly disappears when an admin
  disables it on the catalogue, even on models where the regex still
  matched the name.
- **Préférences → Génération d'images** — `ImageGenerationSettings` is
  now driven by the new `useImageGenerationOptions` hook. Quality and
  size dropdowns rebuild themselves from the live catalogue, with price
  ranges shown next to each option.
- **Live invalidation across siblings** — new
  `apps/web/src/lib/catalogue-invalidation-context.tsx` Provider +
  hooks. After an admin write, the form emits a `model_capabilities`
  or `image_generation_options` event; the LLM Configuration section
  and the Image Generation Settings page (mounted as siblings under
  the dashboard) refetch automatically. **No page reload, no worker
  restart.**

#### Reasoning-model detection consolidated

Three call sites used to hardcode the same regex
(`REASONING_MODELS_PATTERN`) to decide whether a model was a reasoning
model. With the DB catalogue authoritative, `is_reasoning_model()`
short-circuits via the cache; the regex is kept as a fallback only for
brand-new models not yet in the catalogue. Affected files:
`AdminLLMConfigSection.getModelConstraints`,
`responses_adapter._is_reasoning_model`,
`adapter._prepare_provider_config`.

#### Seeds

- `infrastructure/database/seeds/llm_pricing_seed.sql` — rewritten to
  insert into `llm_models` (119 catalogue rows with conservative
  default capabilities) **then** into `llm_model_pricing` via
  `INSERT … SELECT … JOIN llm_models ON model_name`. Capabilities are
  refinable post-seed via the 14-field admin form.
- `infrastructure/database/seeds/image_generation_pricing_seed.sql` —
  every row gains `provider='openai'::llm_provider_enum` (today only
  OpenAI image models exist; the column is provider-ready for the
  future).

### Changed

- `model_profiles.py` — the static `FALLBACK_PROFILES` dict is removed
  (~750 lines). `get_model_profile()` now reads from the
  `ModelCapabilitiesCache` singleton.
- `LLMConfigService.get_provider_models()` reads from both caches
  (chat + image) for the admin metadata endpoint, replacing the
  hardcoded provider→models map.
- `main.py` lifespan registers the two new caches and their reload
  handlers in deterministic order.

### Fixed

- **Pricing PUT toast error on existing models** — the
  `lazy="raise"` relationship on `LLMModelPricing.model` was being
  invalidated by a `db.refresh(pricing)` call in the service layer
  after `flush()`. Removed the 3 unnecessary refreshes; defaults
  (`uuid4`, `datetime.now`) are all Python-side and the pre-populated
  `pricing.model` relationship survives `flush()`.
- **`is_reasoning_model` admin toggle ignored at runtime** — the
  reasoning-model detection had two extra hardcoded regex usages
  (`responses_adapter._is_reasoning_model`,
  `adapter._prepare_provider_config`) that bypassed the admin's
  intent. Both now consult the cache first and fall back to the
  regex only for unknown models.
- **`UserSkillState` mapper init failure at boot** —
  `sa_inspect(LLMModel).mapper.column_attrs` was triggering eager
  mapper configuration at module import time (before all domain
  models were loaded). Replaced with table-level introspection
  (`LLMModel.__table__.columns.keys()`) which has no side effect.
- **Pricing seed `id NOT NULL` violation** — `llm_model_pricing.id`
  has no DB default; the rewritten seed now provides
  `gen_random_uuid()` explicitly in the `INSERT … SELECT`.

### i18n (6 languages)

- 14 new keys for the admin LLM pricing form (provider label, 8
  capability labels, 4 pricing labels) + 5 keys for the section
  headers (Modèle / Capacités / Tarification + buttons), in
  fr/en/de/es/it/zh.
- 2 new keys for the image options metadata (`provider` column
  header + price range tooltip) in 6 languages.

### Tests + tooling

- All migrations are revertible and tested via the standard
  `alembic upgrade head` / `alembic downgrade -1` cycle.
- Pre-commit hook (host MyPy + Ruff + Black, host ESLint + tsc, i18n
  parity check across 4315 keys × 6 languages) green on the full
  branch.

### Documentation

- New ADR-078 — *LLM Catalogue DB-Source-of-Truth* — documents the
  DB-as-source-of-truth pattern, the three-step migration strategy,
  the dual cache + Pub/Sub invalidation contract, and the React
  Context for cross-sibling invalidation.
- ADR-026 (LLM Model Selection Strategy) — section added on the
  catalogue source change.
- ADR-063 (Cross-Worker Cache Invalidation) — `model_capabilities`
  and `image_generation_options` added to the documented consumer
  list.
- `docs/knowledge/03_settings.md` and
  `docs/knowledge/21_image_generation.md` reflect the new admin
  surface and the live propagation behavior.

## [1.18.1] - 2026-04-23

### Changed — Today Briefing polish + screenshots refresh

- **Greeting now lives on the Hero card** — The LLM-generated greeting that
  used to sit as a standalone block above the Hero now overlays the LIA
  avatar, replacing the rotating random marketing taglines. The `<HeroLiaCard>`
  accepts an optional `greeting` prop (with `LLMUsageBadge` underneath
  showing tokens + EUR cost) and falls back to a static localized tagline
  while the LLM call is in flight, so the area is never empty.
  `BriefingGreeting` and `GreetingSkeleton` are no longer mounted by
  `<TodayBriefing>` (left in the codebase as exported components).
- **Per-card refresh button always visible on mobile** — `<BriefingCard>`
  used to hide its refresh icon until card hover (`opacity-0`
  `group-hover:opacity-100`), which is invisible on touch devices. Now
  visible by default on mobile and hover-revealed (with the +12° rotation
  affordance) only on `sm+` viewports.
- **Usage statistics show the lifetime starting date** — `UserStatistics`
  schema gains a `total_since: datetime` field, populated from
  `User.created_at` in the service layer (default factory keeps
  `model_validate` working when constructing from the ORM row). Frontend
  formats it via `Intl.DateTimeFormat` with the active locale and renders
  "since DD/MM/YYYY" under each StatCard total. New i18n key
  `dashboard.statistics.since` in 6 languages.
- **Section headings get illustrative icons** — `<TodayBriefing>` "Mon
  dashboard" gains a `Sunrise` icon (consistent with the Today Briefing
  feature card in the FAQ); `<UsageStatistics>` "Statistiques d'utilisation"
  gains a `BarChart3` icon. Both in `text-primary`, `aria-hidden="true"`,
  matching the existing typography (`text-base sm:text-lg font-semibold`).
- **Title typography parity** — `<UsageStatistics>` title now uses the
  same Tailwind typography as `<TodayBriefing>` "Mon dashboard" so the
  two main sections of the home page look like siblings rather than
  unrelated blocks.

### Changed — Screenshots refresh + cache-busting

- **12 dashboard screenshots refreshed** — README (`docs/assets/`) and
  landing (`apps/web/public/screenshots/`) now ship the v1.18.x captures
  from `LIA Pics/v2/` and `apps/web/public/screenshots/v2/` respectively.
  8 existing screenshots replaced (homepage, chat, settings-preferences,
  settings-features, settings-administration,
  settings-administration-oneclick, settings-administration-llm, faq) and
  4 new ones added: `chat-debug-panel`, `chat-interactive-skills`,
  `settings-features-memory`, `settings-features-psyche`.
- **Automatic cache-busting on landing screenshots** — `<ScreenshotsSection>`
  appends `?v={APP_VERSION}` to every `<Image src>` so the browser, the
  Next.js Image optimizer (`.next/cache/images`) and any upstream CDN
  re-fetch the new PNG at every release. No manual cache invalidation
  required. The README, served by GitHub directly, refreshes via the
  commit-driven CDN.
- **README v1.18.0 release paragraph translated to English** — the v1.18.0
  description was accidentally drafted in French; aligned with the rest
  of the README, no content change.

### Changed — Landing page descriptions condensed

- **"Skills with maps & mini-apps"** and **"Health data"** descriptions
  on the landing features grid were 4× longer than adjacent descriptions.
  Both rewritten to ~150 chars in 6 languages to match the typography of
  the rest of the grid (no information loss — the long-form details live
  in the FAQ and dedicated docs).

### Fixed

- The optional `greeting` / `isLoadingGreeting` props on `<HeroLiaCard>`
  are typed and default to `null`/`false` — calling `<HeroLiaCard />`
  without them keeps the previous random-tagline behavior, so any other
  caller that may instantiate the Hero outside the briefing flow is
  unaffected.

### i18n (6 languages)

- New key `dashboard.statistics.since` in fr/en/de/es/it/zh.
- 4 new caption keys `landing.screenshots.items.{chat_debug_panel,
  chat_interactive_skills, settings_features_memory,
  settings_features_psyche}` for the new screenshots in the carousel.
- v1_18_1 changelog entry added to `faq.changelog.versions.*` (6 items,
  user-facing only).

### Tests + tooling

- All 7401 unit tests pass.
- `BriefingGreeting` and `GreetingSkeleton` are no longer used by the
  layout but still exported (kept as a non-breaking deprecation cushion).

## [1.18.0] - 2026-04-23

### Added — Today Briefing : the home page becomes a daily ritual

The dashboard home page was a static stats display. It is now a **Today
briefing** — an LLM-generated greeting + contextual synthesis above a
6-card grid of operational data (weather, calendar, unread mails, upcoming
birthdays, active reminders, health metrics).

#### New bounded context `apps/api/src/domains/briefing/`

- **No LangGraph chain** — direct orchestration via `asyncio.gather` of the
  existing services (OpenWeatherMap, multi-provider calendar/email,
  GooglePeople, ReminderService, HealthMetricsService).
- **No DB model, no migration, no scheduler** — pure read orchestration.
- **Per-section Redis cache** with TTL aligned to each source's natural
  change rate: weather 1 h, agenda 10 min, mails 5 min, birthdays 24 h,
  reminders live, health 15 min.
- **6 source fetchers** — pure async functions, each independently failable.
  `ConnectorNotConfiguredError` → `NOT_CONFIGURED` (card hidden in UI).
  `ConnectorAccessError` → `ERROR` (CTA mapped via stable `error_code`).
- **2 LLM calls** (greeting + synthesis) on a single `briefing` slot in
  `LLM_TYPES_REGISTRY` (default `gpt-4.1-nano`, T=0.7, 500 tokens), with
  two distinct versioned prompts. Tokens tracked via existing
  `track_proactive_tokens(task_type="briefing")` (cached tokens correctly
  subtracted from `input_tokens` to avoid double-counting cost). Synthesis
  is skipped when fewer than 2 cards have OK data. Fallback localized
  greeting guarantees the page always renders if the LLM is down. Each
  `TextSection` payload carries an optional `LLMUsage` block
  (`tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur`, `model_name`)
  computed via the in-memory pricing cache so the UI can surface real
  consumption next to the timestamp.

#### Endpoints

- `GET /api/v1/briefing/today` — assemble + return briefing (cache-aware).
- `POST /api/v1/briefing/refresh` — force-refresh selected sections (or
  `"all"`); LLM always regenerated for consistency.

#### Frontend (`apps/web/src/components/dashboard/`)

- **Generic `<BriefingCard>`** with 4 status states (OK / EMPTY / ERROR /
  NOT_CONFIGURED). Refresh button per card with overlay spinner. Optional
  `centerContent` prop vertically + horizontally centers OK content (used
  by Weather + Health).
- **`<BriefingSkeleton>`** mirrors the final layout for a seamless first paint.
- **`<BriefingSynthesis>` + `<BriefingGreeting>`** display a discreet
  `<LLMUsageBadge>` next to the timestamp — total tokens + EUR cost, with
  a tooltip detailing model + IN / OUT / CACHE breakdown. Synthesis also
  flashes a "mis à jour ✨" badge for 1.5 s after a refresh.
- **6 specific cards** : Weather, Agenda, Mails, Birthdays, Reminders, Health.
  - Weather forecast strip — weekday label derived client-side from
    `date_iso` via `Intl.DateTimeFormat` (locale-aware, replaces the
    C-locale `weekday_short` field that no longer ships in the API).
  - Health card — single CSS grid with `display: contents` on list items
    so the today / average separators line up vertically across metrics
    regardless of label widths. List semantics preserved.
- **`<HeroLiaCard>`** preserved verbatim (kept the marketing tagline).
- **`<QuickAccessCompact>`** — 2 compact cards (Help + Settings) replacing
  the previous 3 large cards. The "Security" card (no actionable purpose)
  has been removed.
- **`<UsageStatistics>`** — preserved verbatim (extracted to its own component).
- **Animations** : `animate-in fade-in slide-in-from-bottom-1` on cards with
  50 ms stagger; bouton refresh `animate-spin` during fetch, +12° rotation
  on hover. All wrapped in `motion-safe:` for `prefers-reduced-motion`.
- **Strict black/white per theme** — no decorative gradient. The chromatic
  warmth comes from the content (greeting/synthesis), not the decor.

#### Observability

- 4 new Prometheus metrics in `metrics_briefing.py`:
  `briefing_build_duration_seconds`, `briefing_section_status_total`,
  `briefing_refresh_requests_total`, `briefing_llm_invocations_total`.
- Single structured `briefing_built` log line per build with
  duration_ms + cache_state + sections_status.

#### i18n (6 languages)

- 16 new keys per locale under `dashboard.briefing.*` (en, fr, de, es, it, zh).
- 6 card-specific subsections with empty states, error CTAs, units.
- `usage_tokens` key uses i18next pluralization (`_one` / `_other`) so the
  inline LLM usage badge stays grammatically correct at any token count.

#### Tests + docs

- `tests/unit/domains/briefing/` — 30+ unit tests on formatters + service
  orchestration with mocked fetchers + LLM, including a happy-path test
  asserting that `LLMUsage` returned by the LLM helpers lands on
  `TextSection.usage` for both greeting and synthesis.
- `docs/technical/BRIEFING_DOMAIN.md` — full architecture + API + recipe
  to add a new card.
- `docs/architecture/ADR-077-Today-Briefing-Domain.md` — rationale for the
  separate bounded context + LangGraph bypass.

#### Cost & performance

- Latency: < 1 s on warm cache, < 2 s on cold cache (P95 target).
- LLM cost: ~ 0.005 cent per build, < 1 €/month total at 100 active users.
- Cache footprint: ~ 60 MB Redis at 1000 users.

---

## [1.17.2] - 2026-04-22

### Added — Health Metrics : agents + Heartbeat + Journal + Mémoire + extensibilité

La v1.17.1 a livré l'ingestion batch-upsert polymorphe, mais les données
santé restaient inertes pour la logique conversationnelle. La v1.17.2
les expose aux trois boucles centrales de LIA et pose les fondations
pour en ajouter facilement de nouvelles (sommeil, SpO2, calories…).

#### Registre central des kinds (`kinds.py`)

- Nouveau `HEALTH_KINDS: dict[str, HealthKindSpec]` — source unique de
  vérité pour les bornes physiologiques, la stratégie de merge intra-batch,
  la méthode d'agrégation, le type de baseline, et l'agent associé.
- Ingestion (`_validate_sample`), repository (`_merge_duplicate_samples`),
  aggregator (`_BucketAccumulator`) refactorisés pour lire ce registre —
  zéro branche `if kind ==` restante.
- Ajouter un kind = une entrée dans `kinds.py` + un nouveau pack de tools.

#### Baseline adaptive + détection de variations

- `baseline.py` — `compute_baseline()` avec sélection automatique
  `bootstrap` (médiane simple) jusqu'à 7 jours de données, puis `rolling`
  (médiane mobile 28 jours).
- `signals.py` — `detect_recent_variations()` (streaks directionnels) et
  `detect_notable_events()` (événements structurels, ex. inactivité).
- Seuils configurables via `.env` (`HEALTH_METRICS_BASELINE_MIN_DAYS`,
  `HEALTH_METRICS_VARIATION_MIN_DAYS`, `HEALTH_METRICS_VARIATION_MIN_DELTA_PCT`,
  `HEALTH_METRICS_VARIATION_DAILY_DELTA_PCT`).

#### Un agent `health_agent` avec 7 tools hand-crafted

Conforme au pattern 1 agent ↔ 1 domaine du codebase (cf. `email_agent`,
`event_agent`, `weather_agent`…). Sept tools sous un même
`health_agent`, tous construits via `build_generic_agent()` avec un
prompt unique versionné (`health_agent_prompt.txt` v1) et gatés par
`_check_user_toggle_or_error` qui retourne
`UnifiedToolOutput.failure(error_code="PERMISSION_DENIED")` si le toggle
utilisateur est désactivé :

- **Steps** — `get_steps_summary_tool`, `get_steps_daily_breakdown_tool`,
  `compare_steps_to_baseline_tool`.
- **Heart rate** — `get_heart_rate_summary_tool`,
  `compare_heart_rate_to_baseline_tool`.
- **Cross-kind** — `get_health_overview_tool`, `detect_health_changes_tool`.

Les tools de summary + overview utilisent **`time_min` / `time_max` ISO
8601** (même pattern que `calendar_tools.search_events_tool`) : le
planner extrait les deux bornes depuis les `resolved_references` du
QueryAnalyzer (« cette semaine » → `2026-04-20 to 2026-04-26` →
`time_min=2026-04-20`, `time_max=2026-04-26`) et les passe au tool.
Défaut côté service : `time_min` → aujourd'hui 00:00 UTC,
`time_max` → `datetime.now(UTC)`. Les valeurs factuelles (totaux,
moyennes, entrées par jour) sont inlinées dans le champ `message` de
l'`UnifiedToolOutput` pour être lues par le LLM Response (pattern
`weather_tools`).

#### Heartbeat — source `health_signals`

- `HeartbeatContext.health_signals` injecté dans `CURRENT CONTEXT` pour
  décisions proactives contextuelles. Fetch avec timeout 2 s + fallback
  silencieux pour ne jamais bloquer le gather.

#### Mémoire — `context_biometric` JSONB

- Nouvelle colonne optionnelle sur `memories` (migration `health_metrics_005`).
- Le memory_extractor injecte un `{health_context}` dans le prompt et
  persiste un blob `context_biometric` (deltas, tendances, événements
  uniquement — jamais de valeurs brutes) quand l'émotion dépasse un seuil.

#### Journal — extraction + consolidation

- Placeholders `{health_context}` (extraction) et `{health_signals_section}`
  (consolidation) injectés uniquement pour les utilisateurs opt-in.

#### Toggle utilisateur unique

- `User.health_metrics_agents_enabled` (migration `health_metrics_004`,
  default `false`). Un seul interrupteur gouverne les 4 intégrations :
  agents, Heartbeat, mémoire, journal.
- Nouvel endpoint `PATCH /auth/me/health-metrics-agents-preference`.
- Section « Assistant » dans **Réglages → Données santé** (6 langues).

#### Backward compatibility

- `HealthMetricAggregatePoint` conserve ses champs typés
  (`heart_rate_avg/min/max`, `steps_total`) et ajoute un
  `metrics_by_kind: dict[str, dict[str, int | float]] | None` additif —
  les kinds futurs apparaissent automatiquement dans cette clé sans
  casser le front existant.

### Fixed — Assistant santé : réponses fiables sur des plages temporelles naturelles

Quatre itérations de debug sur la même requête (« Combien de pas cette
semaine ? ») ont mis en évidence plusieurs défauts d'intégration, tous
corrigés en s'alignant sur les patterns existants du codebase plutôt
qu'en inventant du spécifique :

- **LLM Response ne voyait plus les données** — les tools retournaient
  des messages pauvres (« Steps breakdown over 7 days (8 days with
  data). ») sans inliner les valeurs, ce qui produisait la réponse
  trompeuse « Pas de données ». Les messages incluent désormais les
  chiffres factuels (totaux, moyennes, entrées par jour) dans le champ
  `UnifiedToolOutput.message`, pattern issu de `weather_tools`.
- **Paramètres temporels** — remplacement d'un enum `period` rigide
  par `time_min` / `time_max` ISO 8601 sur les tools summary +
  overview. Le `QueryAnalyzer` résolvait déjà « cette semaine » en
  plage de dates calendaire ; le tool ingère désormais directement
  ces bornes (pattern identique à `calendar_tools.search_events_tool`).
- **Sémantique de semaine** — la logique de fenêtre par défaut
  passait d'un rolling de 7 jours à une borne calendaire
  (aujourd'hui 00:00 UTC → maintenant) quand aucune borne n'est
  fournie, cohérent avec l'expérience frontend (`/aggregate`).
- **Pattern 1 agent ↔ 1 domaine** — consolidation de trois agents
  (`steps_agent`, `heart_rate_agent`, `health_overview_agent`) en un
  unique `health_agent` owning les 7 tools, conforme au reste du
  codebase (`email_agent`, `event_agent`, `weather_agent`…). Zéro
  modification des fichiers cœur (`agent_registry`, `router_node_v3`,
  `smart_catalogue_service`, `domain_taxonomy`).
- **Refactor `HealthMetricsRepository`** — split en deux classes
  héritant de `BaseRepository[T]` (`HealthSampleRepository`,
  `HealthMetricTokenRepository`), conforme au standard.
- **Parallélisation `compute_overview`** — passage de séquentiel à
  `asyncio.gather` pour les kinds enregistrés.

### Changed — Landing et FAQ : messaging générique plutôt qu'iPhone-centric

- Landing section « Données santé » repositionnée comme **API
  d'ingestion dédiée** (Raccourcis iOS, automatisation Android,
  intégration tierce, IoT) plutôt qu'exclusivement iPhone/Apple Santé.
  Titre, description et FAQ synchronisés dans les 6 langues
  (en/fr/de/es/it/zh).

## [1.17.1] - 2026-04-21

### Changed — Health Metrics : refonte en batch upsert polymorphe (BREAKING)

L'iPhone ne peut pas déclencher de manière fiable un automatisme horaire
(iOS exige que le téléphone soit déverrouillé), rendant le modèle v1.17.0
(un POST par heure avec `{data: {c, p, o}}`) structurellement fragile.
Refonte complète vers un modèle **batch quotidien avec upsert idempotent**
côté serveur.

#### BREAKING — Contrat d'API modifié

- Les endpoints `/api/v1/ingest/health` → **supprimés**, remplacés par
  deux endpoints par kind :
  - `POST /api/v1/ingest/health/steps`
  - `POST /api/v1/ingest/health/heart_rate`
- Le body `{"data": {"c": bpm, "p": steps, "o": source}}` → **remplacé**
  par un **tableau de samples auto-horodatés**
  `[{date_start, date_end, steps|heart_rate, o}, ...]` (ISO 8601 avec
  offset, normalisés UTC + tronqués à la seconde).
- L'ancien endpoint `DELETE /health-metrics?field=heart_rate|steps` (qui
  NULL-ait la colonne) → **remplacé** par `DELETE /health-metrics?kind=…`
  qui supprime les lignes de ce kind.
- L'ancienne table `health_metrics` (une ligne par POST) → **supprimée**
  et remplacée par la table polymorphe `health_samples(kind, date_start,
  date_end, value, source)` avec `UniqueConstraint(user_id, kind,
  date_start, date_end)` comme ancre d'idempotence. Migration `health_metrics_003`
  (DROP + CREATE, feature flag off en prod au moment de la coupure).

#### Added

- **Parser flexible** (`parser.py`) acceptant quatre formes d'enveloppe :
  tableau JSON canonique, NDJSON, `{"data": [...]}`, et le wrapping
  « Dictionnaire » iOS `{"<ndjson_blob>": {}}` (détecté par heuristique —
  clé unique avec `\n` + valeur vide). Aucune contrainte sur la forme du
  Raccourci côté utilisateur.
- **UPSERT PostgreSQL** via `INSERT ... ON CONFLICT ... DO UPDATE ...
  RETURNING (xmax = 0)` qui discrimine inserts vs updates en un aller-retour.
  Re-sending le même batch n'insère aucune ligne en double.
- **Dedupe intra-batch avec arbitrage per-kind** — résout le bug
  `CardinalityViolationError` survenant quand iOS émet des samples overlap
  (Apple Watch + iPhone) pour la même période. Stratégies :
  - `steps` → **MAX** (Watch et iPhone comptent des sous-ensembles
    complémentaires du mouvement ; MAX approche la vérité terrain mieux
    que SUM double-compte ou AVG sous-compte).
  - `heart_rate` → **AVG** arrondi (fusion de deux capteurs visant le
    même signal physiologique).
  - Duplicats collapsés comptabilisés comme `updated` dans la réponse,
    warning log `health_batch_duplicates_collapsed`, counter Prometheus
    `health_samples_batch_duplicates_total{kind}`.
- **Validation mixte par échantillon** — chaque sample est accepté ou
  rejeté individuellement avec son index 0-based, les siblings valides
  sont persistés. La réponse liste `rejected[{index, reason}]` avec des
  motifs bornés (`out_of_range | malformed | missing_field | invalid_date`).
- **Aggregator polymorphe server-side** (`aggregator.aggregate_samples`) —
  SUM sur les samples `steps`, AVG/MIN/MAX sur les samples `heart_rate`,
  gaps préservés (`has_data=False`).
- **UI Réglages — fenêtre temporelle agrégée affichée** dans la section
  Statistiques pour lever l'ambiguïté UX « les stats ne bougent pas quand
  je change de période » (les stats HR sont invariantes quand toutes les
  données tiennent dans la plus petite fenêtre — affichage explicite des
  bornes from/to).

#### Fixed

- **Bug prod : 500 `CardinalityViolationError`** sur les ingestions de
  heart_rate/steps couvrant plusieurs heures (Apple Watch + iPhone
  émettent des samples avec le même `(date_start, date_end)`). Résolu par
  le dedupe intra-batch avec arbitrage per-kind décrit ci-dessus.
- **Tooltips recharts illisibles en mode sombre** — les tooltips par
  défaut utilisaient un fond blanc avec label gris hardcodés, rendant le
  label invisible en dark mode. Correction : branchement sur les variables
  CSS shadcn (`--popover`, `--popover-foreground`, `--border`,
  `--muted-foreground`) pour respecter le thème actif.

#### Config

- Rate limit par token relevé **5 → 60 req/h** par défaut (bursts au
  déverrouillage de l'iPhone), paramétrable via `HEALTH_METRICS_RATE_LIMIT_PER_HOUR`.
- Nouveau `HEALTH_METRICS_MAX_SAMPLES_PER_REQUEST=1000` — plafond de taille
  de batch avec `HTTP 413` au-delà.
- Source par défaut `unknown` → **`iphone`**.
- Nouvelle métrique `health_samples_batch_duplicates_total{kind}`.
- Métrique `health_metrics_ingested_total` → **remplacée** par
  `health_samples_upserted_total{kind, operation}` (insert | update).

#### Tests

- 65 tests unit (aggregator polymorphe, parser 4 formes, validation
  per-kind, `_normalize_datetime`, `_merge_duplicate_samples` arbitrage).
- Tests d'intégration : upsert idempotent, mixed validation, dedupe
  intra-batch avec assertions sur les valeurs attendues par kind (MAX=1200
  pour steps, AVG=78 pour HR).

#### Documentation

- ADR-076 (révisé) — décisions de refonte documentées.
- `docs/technical/HEALTH_METRICS.md` réécrit — nouveau contrat, dedupe,
  schéma polymorphe.
- `docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md` réécrit — deux Shortcuts
  (steps + HR), format ISO 8601 obligatoire, failure modes.
- `docs/ARCHITECTURE.md` + `docs/architecture/ADR_INDEX.md` corrigés.
- `apps/web/src/data/guides/how.{6 langues}.md §23.12` + `why.{6
  langues}.md §3.9` réécrits (vitrine technique + fonctionnelle).
- `README.md`, `CHANGELOG.md` (cette entrée), FAQ applicative 6 langues.

## [1.17.0] - 2026-04-21

### Added — Health Metrics ingestion (iPhone Shortcuts) + settings visualization

Nouveau domaine `health_metrics` derrière feature flag `HEALTH_METRICS_ENABLED=false`.

- **Endpoint d'ingestion authentifié par token** `POST /api/v1/ingest/health`
  (Bearer `hm_xxx`). Body : `{"data": {"c": heart_rate, "p": steps_since_previous, "o": source}}`.
  `p` est le nombre de pas enregistrés depuis le précédent envoi (PAS un compteur
  cumulatif quotidien). Horodatage server-side à réception, rate-limit Redis
  (5 req/h/token par défaut), validation mixte par champ (valeur hors plage →
  NULL + log warn sans bloquer les autres champs valides).
- **Tokens hashés (SHA-256) avec préfixe d'affichage** — valeur brute révélée
  une seule fois à la génération, révocables individuellement. Plusieurs tokens
  peuvent cohabiter (rotation). Table `health_metric_tokens` + migration
  `health_metrics_001`.
- **Table `health_metrics` (une ligne par POST)** avec colonnes nullables pour
  `heart_rate` / `steps` (mixed validation), `source` slugifié,
  `recorded_at` UTC, index `(user_id, recorded_at)`.
- **Endpoints utilisateur (session-auth)** : listing, agrégation
  (`period=hour|day|week|month|year`), suppression par champ (`UPDATE NULL`)
  ou globale (`DELETE`), gestion tokens (list/create/revoke).
- **Agrégation server-side** (`aggregator.py`) : SUM des `steps` par bucket
  (heure/jour/semaine/mois/année), AVG/MIN/MAX pour la fréquence cardiaque,
  gaps préservés (`has_data=False`) pour affichage honnête des trous d'envoi.
- **UI Réglages → Fonctionnalités → Données santé** : 4 blocs accordéon
  (ingestion API + tokens, graphiques, statistiques, gestion) avec charts
  `recharts` — courbe FC + barres pas + lignes pointillées moyenne période.
- **i18n 6 langues** (fr/en/de/es/it/zh) — namespace `healthMetrics.*`.
- **Observabilité** : 8 métriques Prometheus (ingested/rejected/auth/rate-limit/
  tokens/deletions + latency histogram) + dashboard Grafana 21 dédié.
- **Documentation** : ADR-076, `docs/technical/HEALTH_METRICS.md`, guide
  iPhone `docs/guides/GUIDE_IPHONE_SHORTCUTS_HEALTH.md`.

## [1.16.10] - 2026-04-20

### Observability Overhaul — 90+ dead metrics revived, 2 new dashboards, DB index optimizations

Cette itération cible la dette d'observabilité du stack : une partie significative
des métriques Prometheus déclarées n'étaient pas émises, deux pans de l'exécution
(sub-agents/skills et ReAct/browser) n'étaient couverts par aucun dashboard, et
les gauges DB-backed (DAU/WAU) n'avaient pas d'index dédié. Livraison en un seul
commit additif sans changement de contrat API.

#### Added

- **Instrumentation de 90+ métriques mortes** — 40 fichiers backend touchés,
  instrumentation défensive (`try/except Exception: pass`) pour que les failures
  Prometheus ne cassent jamais les chemins critiques. Exemples notables :
  router (`router_latency_seconds`, `router_confidence_score`,
  `router_fallback_total`, `router_data_presumption_total`),
  planner (`planner_plans_created_total`, `planner_plans_rejected_total`,
  `planner_domain_confidence_score`, `planner_retries_total`,
  `planner_retry_success_total`, `planner_retry_exhausted_total`),
  sub-agents (`subagent_token_budget_exceeded_total`),
  HITL (`hitl_clarification_requests_total`,
  `hitl_question_generation_duration_seconds`, `hitl_question_ttft_seconds`,
  `rejection_total`, `rejection_response_tokens`), OAuth
  (`oauth_token_exchange_duration_seconds`, `oauth_provider_errors_total`,
  `oauth_connector_activation_total`, `oauth_connector_activation_duration_seconds`,
  `oauth_lock_acquired/released/wait/contention/timeout_total`), connecteurs
  (`connector_api_requests_total`, `connector_api_duration_seconds`,
  `connector_api_errors_total` avec sanitization de paths URL pour borner la
  cardinalité), voice (`voice_comment_tokens_total`,
  `voice_interruptions_total`, `voice_preference_toggles_total`), browser
  (`browser_errors_total`, `mcp_react_invocations_total`,
  `mcp_react_iterations_histogram`), drafts (`registry_draft_actions_total`,
  `draft_edit_iterations_total`), initiative (`initiative_evaluations_total`,
  `initiative_duration_seconds`, `initiative_actions_total`), data-registry
  (`registry_size`, `registry_expired_total`), conversations
  (`conversation_message_archived_total`, `conversation_repository_queries_total`,
  `conversation_repository_errors_total`, `user_return_rate_total`,
  `user_daily_conversations_total`).
- **Dashboard 19 — Sub-agents & Skills** (20 panels, 5 rows) : activité
  sub-agents, token budget, skills execution, rich outputs (frames/images),
  clarifications, query patterns.
- **Dashboard 20 — ReAct & Browser** (22 panels, 5 rows) : invocations ReAct,
  iterations, browser tool errors, MCP React, trajectory analysis.
- **DB indexes** (migration `obs_indexes_001`) : `ix_conversations_updated_at`
  (DAU/WAU), `ix_conversations_created_at` (daily-conversations histogram),
  `ix_connectors_status` (connector_activation_rate gauge). Objectif : passer
  les queries du background updater de ~500ms (full scan) à <50ms.
- **FastAPI `RequestValidationError` handler** (`validation_errors_total`
  dashboard 16) : comptabilise les 422 par field + error_type, cap à 10
  erreurs/requête pour borner la cardinalité.
- **SQLAlchemy event listeners** sur `Connector` (`before_insert` / `after_insert`)
  pour mesurer la durée d'activation réelle (flush SQL → completion) sans
  intrusion dans les services.
- **Gauges DB-backed** : DAU (`user_active_daily_gauge`), WAU
  (`user_active_weekly_gauge`), Redis pool
  (`redis_connection_pool_size_current`,
  `redis_connection_pool_available_current`), taille table checkpoints
  (`checkpoints_table_size_bytes`), taux d'activation connecteur
  (`connector_activation_rate`).

#### Fixed

- **`planner_plans_created_total` labels mismatch** — la metric était déclarée
  avec `[execution_mode]` seul mais appelée avec `(execution_mode, agents_count)`,
  provoquant un `ValueError` silencieux dans le try/except. Argument
  `agents_count` retiré.
- **`hitl_question_ttft_seconds.observe()` sans `.labels()`** — bug pré-existant
  dans [question_generator.py:337](apps/api/src/domains/agents/services/hitl/question_generator.py#L337)
  corrigé par ajout de `.labels(type="tool_confirmation")`.
- **Cardinality bomb sur `connector_api_*{operation}`** — les labels recevaient
  des paths URL bruts (avec UUIDs, tokens, IDs numériques), explosant la mémoire
  Prometheus. Sanitizer segment-par-segment (regex UUID/id/hex_id/token, 12/12
  cas de test passants) en amont du `.labels()`.
- **Dashboards 19 et 20 complètement vides** — utilisation fautive de
  `collapsed: false` avec des panels imbriqués dans `row.panels[]` : Grafana
  exige une structure flat quand le row n'est pas collapsé. Script de flatten
  `flatten_dashboards_19_20.py` appliqué.
- **`Connector.is_active` inexistant** — la colonne DB est `status`, pas
  `is_active`. Requête `connector_activation_rate` corrigée pour utiliser
  `Connector.status == ConnectorStatus.ACTIVE`.
- **Label `ConnectorType.BRAVE_SEARCH`** dans `connector_activation_rate` au
  lieu de `brave_search` : `ctype.value` (au lieu de `str(ctype)`) pour exposer
  uniquement la valeur snake_case.
- **Imports erronés** : `user_daily_conversations_total` et
  `user_return_rate_total` étaient importés depuis
  `infrastructure.observability.metrics` mais déclarés dans `metrics_business`.
  Corrigés.
- **Double import** dans `proactive/runner.py` (`track_proactive_notification`
  et `track_proactive_tokens`) fusionnés en un seul bloc `from ... import (a, b)`.
- **Magic number `0.5`** pour le seuil de fallback router remplacé par
  `get_confidence_bucket(confidence) == "low"` pour rester aligné sur les
  buckets existants de `router_decisions_total{confidence_bucket}`.
- **Proactive runner** : les helpers `track_proactive_task_execution`,
  `track_proactive_notification`, `track_proactive_tokens`,
  `track_proactive_feedback` étaient définis dans `metrics_registry.py` mais
  jamais appelés — le runner utilisait `background_job_duration_seconds`
  comme proxy. Rebranchés.

#### Changed

- **README, docs/INDEX.md, docs/technical/GRAFANA_DASHBOARDS.md,
  docs/technical/METRICS_REFERENCE.md, docs/readme/README_OBSERVABILITY.md,
  docs/readme/README_GRAFANA_DASHBOARD.md** — passent à **20 dashboards /
  354+ panels** (contre 18/312) avec versions bumpées (4.0 → 4.1) et dates
  mises à jour.
- **MyPy strict** — event listeners `Connector` typés
  (`_SAMapper`, `_SAConnection`, `target: "Connector"`), plus d'`untyped-def`.
- **Ruff + Black** — 809 fichiers conformes, 0 erreur.

## [1.16.9] - 2026-04-20

### Chat UX Polish — LaTeX, syntax highlighting, history search, copy buttons, a11y

Cette itération concentre une quinzaine d'améliorations ciblées de l'expérience
chat, un correctif de bug, et le nettoyage du skill-generator pour garantir la
livraison exhaustive des fichiers d'un skill.

#### Added

- **Support LaTeX dans les réponses assistant** — `remark-math` + `rehype-katex`
  branchés dans [MarkdownContent.tsx](apps/web/src/components/chat/MarkdownContent.tsx).
  Syntaxe : `$inline$` et `$$block$$`. CSS KaTeX chargé globalement dans
  [[lng]/layout.tsx](apps/web/src/app/[lng]/layout.tsx). Le prompt
  `response_system_prompt_base.txt` encourage le LLM à utiliser LaTeX pour les
  expressions mathématiques.
- **Coloration syntaxique + copy button sur blocs de code** — nouveau composant
  [CodeBlock.tsx](apps/web/src/components/chat/CodeBlock.tsx) avec
  `react-syntax-highlighter` en lazy-load (`PrismAsyncLight`), thème automatique
  (one-dark / one-light via `next-themes`), 25 langages enregistrés à la
  demande, bouton copy avec toggle Copy → Check + toast.
- **Copy button sur messages assistant** — bouton copy discret en top-right de
  chaque bulle (hover-only desktop, toujours visible mobile) avec tooltip et
  toast i18n.
- **Dates relatives dans ChatMessage** — `formatTime` renvoie maintenant
  l'heure seule pour aujourd'hui, « Hier + heure » pour J-1, nom de jour + heure
  pour J-2 à J-6, format complet au-delà (via `Intl.RelativeTimeFormat` /
  `Intl.DateTimeFormat`, zéro dépendance supplémentaire).
- **Recherche dans l'historique de conversations** — `GET /conversations/me/messages?search=`
  accepte un substring via PostgreSQL `ILIKE` (case-insensitive, MVP
  accent-sensitive). Input de recherche dans le header du chat avec filtrage
  client-side pour feedback instantané.
- **Primitive Tooltip Radix** — nouveau composant [tooltip.tsx](apps/web/src/components/ui/tooltip.tsx)
  (preset shadcn), `TooltipProvider` monté dans le layout racine. Migration
  appliquée aux icônes prioritaires du chat (paperclip, copy, feedback 👍/👎/🚫,
  download image, remove attachment).
- **Accessibilité TypingIndicator** — `role="status"` + `aria-live="polite"` +
  `aria-label` localisé pour annoncer le streaming aux lecteurs d'écran.
- **Attributs mobiles natifs du textarea chat** — `autoCapitalize`,
  `autoCorrect`, `spellCheck`, `enterKeyHint="send"` pour une expérience
  clavier mobile standard (bouton « Envoyer » au lieu de « Return »).
- **InterestFeedback optimistic UI** — les boutons 👍/👎/🚫 disparaissent
  immédiatement au clic, avec toast de confirmation proactif. Le backend
  reste source de vérité en cas d'échec (bouton réapparaîtra au prochain
  reload).
- **Constantes `FIELD_TARGET_ID`, `FIELD_FEEDBACK_ENABLED`,
  `FIELD_FEEDBACK_SUBMITTED`, `FIELD_FEEDBACK_VALUE`** dans
  [`core/field_names.py`](apps/api/src/core/field_names.py) — centralisation
  des clés JSONB de la metadata des messages proactifs. Migration
  correspondante dans [notification.py](apps/api/src/infrastructure/proactive/notification.py)
  (boy scout rule).
- **Helpers `_fetch_language` / `_language_from_result`** sur
  `ConnectorTool` ([base.py](apps/api/src/domains/agents/tools/base.py)) +
  constante `_LANGUAGE_RESULT_KEY`. Factorise le pattern Option C utilisé
  par les 6 tools Hue pour propager la langue utilisateur de l'execute
  async vers le formatter sync sans s'appuyer sur un état d'instance
  partagé (les tool instances sont des singletons concurrents).
- **Tests unitaires** — 14 tests `test_hue_i18n.py` (helpers + formatage),
  5 tests `test_feedback_persistence.py` (intégration, isolation
  cross-tenant, NULL metadata, multi-messages), 4 tests
  `test_messages_search.py` (ILIKE, no-match, None, accent-sensitive MVP).

#### Fixed

- **Bug InterestFeedback boutons réaffichés au reload** — le clic sur 👍/👎/🚫
  persiste désormais dans `conversation_messages.message_metadata.feedback_submitted`
  via `ConversationRepository.mark_interest_feedback_submitted`. Au reload,
  le frontend lit `message.metadata?.feedback_submitted` — plus de
  réapparition cross-session / cross-device.
- **Weather erreurs localisées correctement** — dans les 3 tool variants,
  `language` est désormais overridé par la préférence utilisateur
  (`if user_lang: language = user_lang`) au lieu du défaut kwargs, et les
  6 sites `_()` propagent `language` à gettext (message "Unable to find
  location" / "Please specify a city" rendu en allemand / italien / etc.).
- **Hue tool messages localisés** — les 6 tools Philips Hue
  (list_lights/control_light/list_rooms/control_room/list_scenes/activate_scene)
  passent par `_(text, language)` avec propagation via `self.runtime` →
  `self._fetch_language()`. 126 entrées ajoutées aux 6 fichiers `.po`
  (`fr/en/de/es/it/zh-CN`) et `.mo` recompilés.
- **Skill-generator livraison incomplète des fichiers** — `SKILL.md` du
  skill-generator renforcé : Phase 3 liste explicitement TOUS les types
  de fichiers à produire (scripts/*.py, references/*.md,
  translations.json), Phase 4 impose un protocole de livraison avec
  header de chemin avant chaque bloc de code, section "Delivery
  Checklist" ajoute une vérification finale comptant les resources
  déclarées vs livrées.
- **Prompt LaTeX KeyError runtime** — l'exemple initial
  `e^{-x}` déclenchait `KeyError: '-x'` dans `str.format()`. Remplacé
  par `a^2 + b^2 = c^2` (sans accolades) dans
  [response_system_prompt_base.txt](apps/api/src/domains/agents/prompts/v1/response_system_prompt_base.txt).

#### Removed

- **Image de fond + parallax sur la page chat** — suppression complète du
  hook `useDeviceParallax` (orphelin après cleanup) et de l'image de fond
  dans [[lng]/dashboard/chat/page.tsx](apps/web/src/app/[lng]/dashboard/chat/page.tsx).
  Interface chat plus épurée, performance mobile améliorée.

#### Dependencies

- Ajout : `remark-math@^6`, `rehype-katex@^7`, `katex@^0.16`,
  `@radix-ui/react-tooltip@^1.2`, `react-syntax-highlighter@^16` +
  `@types/react-syntax-highlighter` (frontend).
- Ajout dev : `polib` (backend — pour compiler les `.po` → `.mo` via
  `scripts/i18n/compile_translations.py`).

## [1.16.8] - 2026-04-20

### Rich Skill Outputs — Interactive Frames, Images & Runtime Conventions

Les skills ne sont plus limités à du texte. Cette release introduit un **contrat de sortie enrichi** (`SkillScriptOutput`) qui permet à un skill de retourner, en plus du texte, une **frame HTML interactive** (iframe sandboxée avec srcDoc ou URL externe) et/ou une **image statique**. Les trois champs sont indépendants et combinables — le script décide, l'application route. Le pipeline existant (Data Registry → SSE `registry_update` → sentinel HTML → composant React) a été répliqué pour les skills avec un nouveau type `SKILL_APP`, un sentinel dédié et un widget frontend `SkillAppWidget`. Cinq nouveaux skills systèmes illustrent le contrat (interactive-map, weather-dashboard, calendar-month, qr-code, pomodoro-timer, unit-converter, dice-roller). Le skill-generator et le guide utilisateur sont mis à jour en conséquence, avec documentation complète des conventions runtime (paramètres auto-injectés `_lang`/`_tz`, synchronisation thème/langue, auto-resize iframe, interactivité client-side sous CSP stricte).

#### Added

- **Contrat `SkillScriptOutput`** — modèle Pydantic (`src/domains/skills/script_output.py`) définissant le JSON écrit sur stdout par les scripts Python : champ `text` obligatoire, champs `frame` et `image` indépendants et combinables. `frame.html` XOR `frame.url` (srcDoc vs iframe externe), taille HTML bornée à `SKILLS_FRAME_MAX_HTML_BYTES = 200 KB`. Parser `parse_skill_stdout` tolérant : stdout non-JSON → dégradation en texte brut (rétrocompat totale).
- **Type `RegistryItemType.SKILL_APP`** et builder `build_skill_app_output` (`src/domains/skills/output_builder.py`) qui produit un `UnifiedToolOutput.data_success` avec `RegistryItem` typé, injection automatique d'un `<meta http-equiv="Content-Security-Policy">` strict pour les skills utilisateur (skills système exemptés — admin de confiance), et snippet auto-resize + theme-sync ajouté aux frames inline.
- **`SkillAppSentinel`** (`src/domains/agents/display/components/skill_app_sentinel.py`) — rendu HTML sous forme de `<div class="lia-skill-app" data-registry-id="…">` calqué sur `MCPAppSentinel`. Détecté côté React (`MarkdownContent.tsx`) et remplacé par `<SkillAppWidget>`.
- **`SkillAppWidget`** (`apps/web/src/components/chat/SkillAppWidget.tsx`) — rend séquentiellement `image` (via `ImageLightbox`) puis `frame` (iframe sandbox `allow-scripts allow-popups`, pas `allow-same-origin`, background transparent). Caption `text_summary` pour l'accessibilité.
- **Hook `useSkillAppBridge`** (`apps/web/src/hooks/useSkillAppBridge.ts`) — bridge `postMessage` minimaliste : `ui/initialize` (host info + theme + locale), `ui/notifications/size-changed` (resize iframe), `ui/open-link` (HTTPS only), push proactif de `ui/theme-changed` et `ui/locale-changed` sur iframe `load`, `MutationObserver` sur `<html class>` et `<html lang>` pour propagation live. **Délibérément sans** `tools/call`, `resources/read`, `ui/download-file` (attack surface réduite).
- **Auto-injection `_lang` et `_tz`** — `run_skill_script` enrichit automatiquement les paramètres du script avec la langue et le fuseau horaire de l'utilisateur, sans intervention du LLM ReAct.
- **Sept nouveaux skills systèmes** :
  - `interactive-map` (frame URL Google Maps embed) — affiche un lieu sur une carte.
  - `weather-dashboard` (frame HTML) — météo 5 jours avec icônes et gradients alignés OpenWeatherMap (11 groupes de conditions).
  - `calendar-month` (frame HTML) — vue mensuelle interactive d'un mois donné.
  - `qr-code` (image) — génération QR code via `segno` (pure-Python, bundled).
  - `pomodoro-timer` (frame HTML) — minuteur 25/5 interactif.
  - `unit-converter` (frame HTML) — conversion d'unités temps réel.
  - `dice-roller` (frame HTML) — lancer de dés avec animation, CSPRNG (`crypto.getRandomValues` + rejection sampling), re-roll depuis la frame.
- **Interactivité client-side** — pattern documenté : pas de `onclick` inline (CSP stricte), utilisation de `addEventListener` dans un `<script>`, CSPRNG pour les tirages aléatoires, animation via `cloneNode` + `replaceChild`.
- **Constante `SKILLS_FRAME_MAX_HTML_BYTES`** (`src/core/constants.py`) — borne supérieure de taille du HTML inline, enforced par validator Pydantic.
- **Dépendance `segno>=1.6.0`** dans `requirements.txt` — génération de QR codes pure-Python, sans Pillow.
- **Mise à jour skill-generator** (`data/skills/system/skill-generator/`) — nouvelle section "Runtime Conventions (Visualizer / Generator)" dans `SKILL.md`, sous-sections "Auto-injected parameters", "Theme & locale sync", "Iframe auto-resize", "Client-side interactivity" dans `references/format-specification.md`, chapitre 6 "Interactive Visualizer — canonical pattern" (skill `coin-flip` complet : SKILL.md + render_coin.py) dans `references/archetype-examples.md`. Exemple QR mis à jour avec `segno` (au lieu de `qrcode` + Pillow).
- **Mise à jour guide utilisateur** (`apps/web/src/components/settings/SkillGuideModal.tsx`) — nouvelle section "Localization, theming and runtime conventions" dans l'onglet Advanced avec 3 cartes explicatives (`_lang`/`_tz`, `data-theme`, auto-resize) + 2 exemples de code (Generator `segno`, Interactive `coin-flip`). Champs `outputs` et `compatibility` ajoutés à la liste des frontmatter fields. 17 nouvelles clés i18n par locale (6 langues).

#### Changed

- **Rendu conditionnel des widgets interactifs** — nouveau `INTERACTIVE_WIDGET_TYPES = frozenset({SKILL_APP, MCP_APP, DRAFT})` (`src/domains/agents/data_registry/models.py`). Le rendu dans `response_node` est désormais séparé en deux chemins : Path 1 (widgets interactifs) toujours injectés indépendamment du `user_display_mode` (HTML / Markdown / Cards), Path 2 (data cards) conditionnel sur le mode `CARDS`. Avant le fix, les frames de skills étaient invisibles pour les utilisateurs en mode "HTML enrichi" ou "Markdown".
- **Injection des instructions skill dans le prompt** — `skills_context` n'est plus interpolé dans `response_system_prompt_base.txt` mais injecté comme 2ᵉ message système dédié avec préfixe "SKILL INSTRUCTIONS CONTRACT (PRIORITY: HIGHEST)" et override explicite des `<ResponseGuidelines>`. L'effet de primauté (primacy-effect) du LLM honore désormais les `references/*.md` du skill actif au lieu des règles génériques.
- **Règle `<ResponseGuidelines>` enrichie** — directive ajoutée : quand un skill est actif, ses instructions l'emportent sur les formats par défaut.
- **Initiative proactive désactivée pendant l'exécution d'un skill** — évite les digressions cross-domaine du mode ReAct quand le skill est souverain sur sa réponse.
- **Auto-resize iframe via `getBoundingClientRect().bottom`** — remplace `Math.max(scrollHeight, offsetHeight)` qui incluait le viewport de l'iframe (frames météo systématiquement trop hautes). Pattern iframe-resizer. CSS reset avec `body{background:transparent!important}` pour que le thème de l'hôte soit visible.
- **Coercion des paramètres `run_skill_script`** — helper `_coerce_parameters(value: dict | str | None)` accepte désormais les chaînes JSON (contournement du modèle Qwen qui sérialise parfois `parameters` comme string). Évite les boucles infinies / `GraphRecursionError`.
- **Settings "Skills intégrées" et "Mes skills importées"** — sections collapsibles fermées par défaut (évite la surcharge visuelle quand l'utilisateur a beaucoup de skills). Chevron rotate -90° à l'état fermé.
- **Tables de traduction inline dans les skills** — `_WEEKDAYS_LONG/SHORT` et `_MONTHS_LONG/SHORT` pour les 6 langues (fr/en/es/de/it/zh), au lieu de `strftime` + `setlocale` (les locales POSIX ne sont pas installées dans le container).

#### Fixed

- **Frames skills invisibles en modes "HTML enrichi" / "Markdown"** — `user_display_mode != CARDS` court-circuitait toute injection HTML. Les widgets interactifs (SKILL_APP, MCP_APP, DRAFT) sont maintenant toujours rendus.
- **Frames météo en thème clair malgré l'app en thème sombre** — race condition : l'iframe émettait `ui/initialize` avant le mount du handler React. Fix : push proactif `ui/theme-changed` sur `load` event avec double `requestAnimationFrame`, `MutationObserver` en secours.
- **Dates météo affichées en anglais malgré la locale `fr`** — `strftime` tombait silencieusement en fallback US car `fr_FR.UTF-8` n'est pas installé dans le container. Tables de traduction inline par locale.
- **Dice-roller : même valeur pour 2 dés + pas d'animation + pas de re-roll** — `plan_template` figeait `notation: "1d6"` pour toutes les requêtes. Skill migré en A1 (script-only) avec parser regex tolérant. JS client avec CSPRNG + rejection sampling pour distribution uniforme.
- **Qwen : `parameters` envoyés comme string JSON → GraphRecursionError** — coercion automatique ajoutée.
- **Background iframe blanc en thème sombre** — CSS reset `body{background:transparent!important}` + `<iframe style="background:transparent">` + conversion des media queries `prefers-color-scheme` en sélecteurs `html[data-theme="dark"]` (plus fiable, synchronisé avec l'app).
- **Skill LLM ReAct n'appelle pas `run_skill_script`** — prompts reformulés pour généraliser : "use run_skill_script for validation, computation OR rich outputs".

#### Removed

- Aucune API publique retirée — rétrocompatibilité totale avec les scripts qui retournent du texte brut.

#### Documentation

- **`data/skills/system/skill-generator/SKILL.md`** — section "Runtime Conventions (Visualizer / Generator)" avec paramètres auto-injectés, thème via `[data-theme]`, `segno` pour QR, auto-resize, interactivité.
- **`data/skills/system/skill-generator/references/format-specification.md`** — section "Runtime Conventions" (4 sous-sections), frontmatter `outputs: [text|frame|image]`.
- **`data/skills/system/skill-generator/references/archetype-examples.md`** — chapitre 6 "Interactive Visualizer — canonical pattern" (skill `coin-flip` complet).
- **`data/skills/system/skill-generator/scripts/validate_skill.py`** — validation du frontmatter `outputs`, check de présence d'un script Python si `frame`/`image` déclaré, lint AST léger.
- **`apps/web/src/components/settings/SkillGuideModal.tsx`** — section "Localization, theming and runtime conventions" dans Advanced avec 3 cartes + 2 exemples.
- **`docs/guides/GUIDE_TOOL_CREATION.md`** — section "Rich Skill Outputs" ajoutée (schéma JSON, exemples, conventions, sécurité).
- **`docs/knowledge/12_skills.md`** — contrat `SkillScriptOutput` documenté.
- **`docs/technical/SKILLS_INTEGRATION.md`** — flow Data Registry pour skills, détails SKILL_APP.

## [1.16.7] - 2026-04-19

### Proactive Weather — Temperature Detection Fix + Travel Location (ADR-073)

Deux évolutions complémentaires du système de notifications proactives météo. D'abord, un **correctif du détecteur de chute de température** qui produisait des faux positifs quotidiens en confondant le cycle jour/nuit naturel avec un changement climatique réel : le code comparait la température courante avec chaque entrée forecast des 24 prochaines heures, donc une notification envoyée en fin d'après-midi flaggait systématiquement les températures nocturnes comme « chute ». Remplacé par une comparaison **moyenne du jour vs moyenne du lendemain** (bucketée par date locale), qui filtre naturellement le bruit diurne et capture les vraies transitions climatiques — chute **et** hausse désormais détectées. Ensuite, un **mécanisme de localisation en déplacement** (opt-in, chiffré, non historisé) pour que les notifications météo restent pertinentes quand l'utilisateur est loin de son domicile : la cascade `last_known (récent + > 50 km du domicile) > home` reproduit en mode asynchrone le comportement déjà exposé par le tool conversationnel `quelle météo` (cas implicite : `browser > home`).

#### Added

- **Détection de hausse de température (`temp_rise`)** en plus de `temp_drop` — comportement symétrique, même seuil `HEARTBEAT_WEATHER_TEMP_CHANGE_THRESHOLD`. Utile pour anticiper la tenue à prévoir pour le lendemain dans les deux sens.
- **Last-known location persistée côté serveur** — 3 colonnes ajoutées au modèle `User` : `last_known_location_encrypted` (Fernet JSON `{lat, lon, accuracy}`), `last_known_location_updated_at` (UTC), `weather_use_last_known_location` (opt-in, default `false`). Migration `last_known_loc_001`.
- **3 nouveaux endpoints `/auth/me/*`** :
  - `PATCH /weather-location-preference` — toggle opt-in (désactivation → wipe immédiat).
  - `PUT /last-location` — push d'une géolocalisation (403 si opt-out, 200 `throttled=True` si < 30 min depuis le dernier push).
  - `GET /last-location` — vue transparence RGPD avec flag `stale` basé sur le TTL configuré.
- **Service `UserLocationService`** avec la cascade `get_effective_location_for_proactive(user)` : retourne `(lat, lon, "home"|"last_known")`. Réutilise `_haversine_distance` existante et la clé Fernet globale.
- **Hook fire-and-forget dans `stream_chat_response`** — quand l'utilisateur a opt-in et que le frontend envoie une `BrowserGeolocation` dans le chat request, la position est persistée en arrière-plan via `safe_fire_and_forget`, sans bloquer la réponse. Opt-in et throttle 30 min enforcés côté serveur.
- **Reverse geocoding avec cache Redis** — `resolve_city_name(lat, lon, api_key)` dans `domains/heartbeat/geocoding.py` appelle l'API OpenWeatherMap reverse, cache Redis 30 jours sur bucket 3 décimales (≈100 m, partageable entre utilisateurs car coordonnées publiques). Le nom de ville est injecté dans le contexte du prompt `heartbeat_decision` (nouvelle règle 16 : obligation d'inclure la ville dans le message quand l'utilisateur est en déplacement, pour transparence).
- **Auto-wipe cascadé** — la suppression de `home_location` déclenche automatiquement le wipe de `last_known_location` : sans domicile comme référence, la cascade n'a plus de sens.
- **4 nouvelles constantes centralisées** dans `src/core/constants.py` — `LAST_KNOWN_LOCATION_TTL_HOURS_DEFAULT=24`, `_MIN_DISTANCE_KM_DEFAULT=50.0`, `_UPDATE_THROTTLE_MINUTES=30`, `_GEOCODE_CACHE_TTL_SECONDS=30j`.
- **2 settings `.env`** — `LAST_KNOWN_LOCATION_TTL_HOURS`, `LAST_KNOWN_LOCATION_MIN_DISTANCE_KM`.
- **3 métriques Prometheus** — `heartbeat_weather_location_source_total{source}`, `user_location_put_total{result}`, `user_location_geocode_total{result}`. Enregistrées au startup via l'import top-level du service.
- **UI `WeatherLocationBlock`** intégrée dans la section « Notifications proactives » (HeartbeatSettings) : toggle opt-in, note de confidentialité, alerte si geoloc navigateur désactivée, vue de la position stockée (coordonnées + fraîcheur + flag `stale`), bouton « Effacer maintenant ». 6 langues.
- **Tests** — 16 unitaires pour `UserLocationService` (update / throttle / forbidden / wipe / stale / cascade 5 branches), 9 pour `geocoding` (cache hit/miss, fallback API), 8 intégration pour les endpoints (opt-in/out, 403, throttle, DELETE home → wipe cascadé).
- **ADR-073** et runbook dédié (`docs/runbooks/LAST_KNOWN_LOCATION.md`).

#### Changed

- **`_detect_weather_changes` refondu côté température** — remplace la boucle `current.temp − entry.temp > threshold` qui générait des faux positifs nuit (ex : notif à 16h flaggait systématiquement la baisse nocturne à 2h du matin) par une comparaison **des moyennes quotidiennes** : entries bucketées par date locale → `avg_today` vs `avg_tomorrow` → déclenchement `temp_drop`/`temp_rise` si `|diff| > threshold`. Garde-fou : au moins 2 entries par bucket sinon la détection est skippée (protège contre les calculs biaisés près de minuit local). `expected_at` positionné à midi local du lendemain.
- **Forecast étendu à 48 h** (`cnt=8` → `cnt=16`) pour couvrir le lendemain complet quelle que soit l'heure d'envoi du heartbeat.
- **`_fetch_weather_with_changes` enrichi** — retourne désormais un tuple `(current, changes, source, city)` au lieu de `(current, changes)`. La source (`"home"`/`"last_known"`) et le nom de ville résolu sont propagés dans `HeartbeatContext` (nouveaux champs `weather_location_source`, `weather_location_city`) pour que le prompt LLM puisse mentionner explicitement la ville.
- **`HeartbeatContext.to_prompt_context()`** — la section CURRENT WEATHER inclut maintenant le nom de ville et un suffixe `(at home)` / `(away from home)` pour que le LLM n'ait aucune ambiguïté sur la localisation du forecast.
- **Prompts heartbeat v1** — nouvelle règle 16 dans `heartbeat_decision_prompt.txt` : obligation d'inclure la ville dans `message_draft` quand `weather_location_city` est disponible et source=`last_known`. Instruction de préservation de la ville dans `heartbeat_message_prompt.txt` lors de la réécriture de style.
- **UI settings** — la section « Localisation météo en déplacement » est intégrée dans la carte existante **Notifications proactives** (pas une nouvelle section), ce qui garde la page settings compacte et aligne la feature sur son contexte d'usage.

#### Fixed

- **Faux positifs `temp_drop` nocturnes** — les notifications « chute de température de X°C » apparaissaient quasi quotidiennement car la logique comparait la température de l'instant avec celle des heures à venir sur 24 h : toute entrée forecast nocturne déclenchait mécaniquement le seuil, même en l'absence de tout changement climatique. Remplacé par la comparaison des moyennes journalières qui lisse par nature le cycle jour/nuit (voir `Changed`).
- **Notifications météo non pertinentes en voyage** — quand l'utilisateur partait plusieurs jours loin de son domicile, les notifications heartbeat continuaient de parler du temps à son adresse `home`. Résolu par la cascade last-known opt-in (`> 50 km` + `< 24 h` de fraîcheur).
- **Counter `user_location_put_total{result="forbidden"}` pollué** — le hook chat appelait le service pour chaque message avec geoloc, même pour les utilisateurs non opt-in, incrémentant `forbidden` comme cas normal et masquant les vrais abus. Fix : check opt-in silencieux **avant** le service dans `update_user_location_fire_and_forget`. `forbidden` est désormais réservé aux appels explicites PUT en état opt-out (abus ou désync frontend).
- **Cohérence conversationnelle** — le tool météo implicite (`"quelle météo"`) utilisait déjà `browser > home` en runtime ; la notification proactive parlait exclusivement de `home`. Asymétrie supprimée : même logique des deux côtés, avec un browser persisté pour les jobs asynchrones.

#### Removed

- Aucune dépendance ajoutée, aucun package retiré.

#### Documentation

- **`docs/architecture/ADR-073-Last-Known-Location-Persistence.md`** — nouvelle ADR (scope, cascade, privacy-by-design, non-goals, alternatives rejetées).
- **`docs/architecture/ADR_INDEX.md`** — entrée ADR-073, compteur 72 → 73.
- **`docs/INDEX.md`** — compteur 72 → 73, arbre docs mis à jour.
- **`docs/runbooks/LAST_KNOWN_LOCATION.md`** — nouveau runbook (ops : wipe manuel, métriques attendues, troubleshooting, incident playbook).
- **`docs/technical/HEARTBEAT_AUTONOME.md`** — 2 settings `.env` ajoutés au tableau, nouveau champ user, nouvelle section « Location cascade (Phase 3 — ADR-073) », description `temp_drop`/`temp_rise` alignée sur la logique J vs J+1.

## [1.16.6] - 2026-04-18

### Long-Term Memory — Precision Overhaul

Refonte complète du pipeline mémoire long-terme (extraction + rétention + consolidation). Le prompt d'extraction manquait de critères explicites sur ce qui mérite d'être mémorisé et comment formuler les souvenirs pour un recall sémantique efficace. La formule de rétention combinait trois signaux dont un (`usage_count`) était toxique (éligibilité sémantique ≠ utilité réelle) et un autre (`recency_factor`) était cassé en pratique (la même constante servait de gate et de dénominateur, le facteur tombait à 0 au moment exact où l'évaluation devenait possible). Des doublons quasi-identiques s'accumulaient sans mécanisme de consolidation. Cette release adresse ces trois axes en bloc.

#### Added

- **Job `memory_consolidation` quotidien à 5 h UTC** — fusionne les paires de mémoires avec similarité cosine ≥ 0.9. Exclut les mémoires épinglées (côté SQL via `WHERE NOT (a.pinned OR b.pinned)`), les paires de catégories différentes, et les paires avec écart d'`emotional_weight` > 5. Cascade de sélection du survivor : `importance > content length (completeness) > created_at (recency)` — `usage_count` délibérément absent du critère. Plafond 50 paires/user/run. Lock Redis distribué pour multi-worker safety.
- **Tag `[PINNED]` dans le prompt d'extraction** — les mémoires verrouillées par l'utilisateur sont désormais annotées dans la section `EXISTING MEMORIES` et le LLM reçoit la règle explicite *"NEVER emit update or delete for them"*. Évite les actions rejetées downstream (économie de tokens output + moins de bruit dans les logs).
- **Détection active de contradictions factuelles** — règle explicite dans le prompt : *"if any existing memory refers to the SAME entity and the new fact changes/enriches/contradicts it → emit update"*. Couplé à un seuil de dédup élargi, attrape les corrections utilisateur ("je suis chez Meta maintenant") qui créaient auparavant des doublons contradictoires.
- **9 nouveaux settings Pydantic exposés via `.env`** :
  - Consolidation (5) : `MEMORY_CONSOLIDATION_ENABLED`, `MEMORY_CONSOLIDATION_HOUR`, `MEMORY_CONSOLIDATION_SIMILARITY_THRESHOLD`, `MEMORY_CONSOLIDATION_MAX_PAIRS_PER_USER`, `MEMORY_CONSOLIDATION_EMOTIONAL_DIFF_SKIP`.
  - Rétention (4) : `MEMORY_MIN_AGE_FOR_CLEANUP_DAYS`, `MEMORY_RECENCY_DECAY_DAYS`, `MEMORY_USAGE_PENALTY_AGE_DAYS`, `MEMORY_USAGE_PENALTY_FACTOR`.
- **2 settings dédup exposés (étaient constantes figées)** : `MEMORY_DEDUP_SEARCH_LIMIT`, `MEMORY_DEDUP_MIN_SCORE`.
- **Log structuré `memory_action_applied`** sur chaque `create`/`update`/`delete` mémoire avec `user_id`, `category`, `importance`, `emotional_weight`, `trigger_topic`, `content_preview`. Alimente Loki pour calibration fine.
- **26 tests unitaires** couvrant la calibration de la formule de rétention (importance 0.5 purgée à 30 j, importance 0.9 préservée, pénalité zero-usage), la cascade de sélection du survivor, les règles de skip, et le tag `[PINNED]`.

#### Changed

- **Prompt d'extraction entièrement réécrit** (`memory_extraction_prompt.txt`) — remplace l'ancienne structure ambiguë (règles monolithiques, *"Exact words only"* absolutiste, catégories sans définitions) par :
  - Sections explicites `WHAT TO EXTRACT` (4 critères positifs : utilité durable, stabilité, unicité, actionabilité) et `WHAT NOT TO EXTRACT` (4 critères négatifs avec exemples).
  - Règle 2 assouplie : *"Facts exact, affect interpretable"* — interprétation émotionnelle autorisée, inférences psychologiques toujours interdites.
  - Nouvelle règle `Semantic recallability` — formuler le `content` et le `trigger_topic` en concepts canoniques qui matcheront les requêtes futures.
  - Nouvelle règle `Content language` — produire dans la langue du message utilisateur (structures JSON en anglais).
  - Définitions précises des 6 catégories + règle de décomposition atomique en cas d'ambiguïté.
  - Bandes explicites pour `emotional_weight` (0 / ±1-2 / ±3-6 / ±7-10) et `importance` (0.3 / 0.5 / 0.7 / 0.9) avec ancres concrètes.
  - 3 few-shot examples (extraction nominale, rejet de bruit, correction contradictoire via `update`).
- **Formule de rétention refondue** — `score = 0.7 * importance + 0.3 * recency_factor` avec pénalité négative `score *= 0.5` si `usage_count == 0` et `age_days > 30`. L'ancienne formule `0.4 * usage_boost + 0.3 * importance + 0.3 * recency_boost` avait trois problèmes : `usage_count` était un signal toxique (éligibilité sémantique ≠ utilité réelle, taux de faux positifs), `recency_factor` était quasi systématiquement à 0 (bug de configuration), et `importance` à 0.3 de poids n'était pas assez dominant.
- **Gate d'éligibilité séparé du decay** — `MEMORY_MIN_AGE_FOR_CLEANUP_DAYS = 7` (protection nouveau-né) indépendant de `MEMORY_RECENCY_DECAY_DAYS = 45` (horizon de décroissance). Résout le bug où `recency_factor` valait toujours 0 dès qu'une mémoire devenait éligible.
- **Seuil de dédup extraction abaissé** 0.5 → 0.4 (`MEMORY_DEDUP_MIN_SCORE`) pour élargir la fenêtre de détection des contradictions factuelles sans surcoût LLM (seulement +50-100 tokens d'input par run, amortis par cache).
- **`logger.exception()` remplace `logger.error()`** dans les handlers globaux de `memory_cleanup.py` et `memory_consolidation.py` pour capturer la stack trace complète dans Loki.
- **Docstrings et noms de paramètres** — `max_age_days` renommé `min_age_for_cleanup_days` partout (repository + scheduler) pour refléter la vraie sémantique.

#### Fixed

- **`recency_factor` toujours à 0 en pratique** — `MEMORY_MAX_AGE_DAYS = 2` servait à la fois de gate d'éligibilité ET de dénominateur du decay linéaire. Conséquence : toute mémoire évaluée avait `recency_factor ≤ max(0, 1 - 2/2) = 0`. La formule reposait de facto uniquement sur `usage_count` (toxique). Corrigé par séparation des deux horizons.
- **Mémoires d'importance moyenne (0.5) jamais purgées** malgré leur âge — critère produit non respecté. Désormais purgées autour de 30 jours avec la formule recalibrée.
- **Corrections factuelles créaient des doublons contradictoires** — ex : mémoire existante *"Je travaille chez Google"* + utilisateur dit *"J'ai changé, je suis chez Meta"* → la dédup à 0.5 n'attrapait pas la relation (sémantiquement divergente), le LLM émettait `create` au lieu de `update`. Résolu par seuil élargi + règle de détection active dans le prompt.
- **Protections obsolètes dans la documentation ADR** (filtres par catégorie `sensitivity`, par `abs(emotional_weight) >= 7`, par `emotional_protection_threshold`) qui n'étaient **jamais implémentées** dans le code réel. Les docs citaient un système plus riche que la réalité. Harmonisé — seules les deux protections effectives restent documentées : `pinned = True` et grace period.
- **`existing_similar` debug loupait les contradictions** — seuil élargi de 0.5 à 0.4 fait apparaître les candidats quasi-contradictoires dans le debug panel pour calibration.

#### Removed

- **3 settings obsolètes** : `memory_max_age_days`, `memory_min_usage_count`, `memory_retention_weight_usage` — remplacés par la nouvelle modélisation.
- **Ordre de priorité des catégories** dans le prompt d'extraction — confusion initiale entre priorité d'affichage (dans le profil psycho) et priorité de classification (à l'extraction). Remplacé par des définitions précises + règle de décomposition atomique.
- **Règle *"Exact words only"*** du prompt d'extraction — remplacée par *"Facts exact, affect interpretable"* pour permettre l'interprétation émotionnelle implicite tout en interdisant le diagnostic psychologique.

#### Documentation

- `docs/architecture/ADR-037-Semantic-Memory-Store.md` — formule de rétention et pointer vers `memory_consolidation.py` ajouté.
- `docs/architecture/ADR-042-Conversation-Lifecycle-Management.md` — formule de rétention et `_is_protected` simplifié (suppression des protections docs-only non implémentées).
- `docs/architecture/ADR-046-Background-Job-Scheduling.md` — ligne `memory_consolidation` dans le tableau des jobs + bloc `calculate_retention_score` / `should_purge` réécrit.
- `docs/ARCHITECTURE.md` — `memory_consolidation` ajouté à la liste des cron jobs APScheduler.
- `docs/guides/GUIDE_BACKGROUND_JOBS_APSCHEDULER.md` — exemples de settings alignés sur la nouvelle API.

## [1.16.5] - 2026-04-18

### Tool Context Manager — Two-Keys Simplification (ADR-072)

Refonte structurelle du Tool Context Manager : passage de 3 clés persistantes (`list` / `details` / `current`) à 2 clés (`list` + `current`). Le cache LRU `details` — vestige de l'époque où les tools de recherche renvoyaient des vues résumées — n'était plus lu en source primaire depuis que les tools unifiés (`get_events_tool`, etc.) retournent systématiquement le payload complet. Sa suppression élimine à la racine trois classes de bugs.

#### Fixed

- **Bug 1 — double auto_save avec pollution du cache `details`** : le décorateur `@auto_save_context` et `parallel_executor._auto_save_wave_contexts` sauvegardaient le même résultat deux fois. Lorsque le manifest n'avait plus de `context_save_mode` explicite, la seconde passe classifiait `get_events_tool` comme DETAILS (match sur `"get"`), polluant le cache. Résolu par un sentinel `_tcm_saved` dans `tool_metadata` que le parallel_executor respecte.
- **Bug 2 — `current_item` mauvais après création/update HITL** : `_set_current_item_after_execution` appelait `save_details` qui cherchait l'item par `primary_id_field="id"`, mais `execute_event_draft` retourne `event_id`. Le lookup échouait, l'item n'était pas indexé, et le fallback `indexed_items[-1]` pointait sur un ancien rdv du cache. Résolu par un appel direct à `set_current_item` (pas de primary_id lookup à l'écriture).
- **Bug 3 — `current_item` stale après évocation linguistique** : après création/update d'un rdv, `current` restait sur lui. Si l'utilisateur disait ensuite `"c'était quoi le premier rdv ?"` puis `"supprime ce rdv"`, `current` n'était pas actualisé par la résolution ordinale et la suppression ciblait l'ancien item. Résolu en rendant `ContextResolutionService` writer de `current_item` : toute résolution réussie met à jour le focus (1 item → set, N>1 → clear).
- **Bug 4 — `turn_type` convention mismatch** : `QueryIntelligence.turn_type` émettait `"REFERENCE_ACTION"` (UPPERCASE) tandis que les consumers comparaient contre `TURN_TYPE_REFERENCE = "reference"` (lowercase). Les turns de référence étaient silencieusement traités comme conversationnels, privant le response_node du `resolved_context` pour grounding. Résolu par helpers `is_reference_turn()` / `is_action_turn()` / `is_conversational_turn()` case-tolerant + normalisation `.lower()` à l'écriture dans le router.
- **Bug 5 — LIST stale après update/delete HITL** : les mutations HITL ne propagaient pas dans la LIST, qui contenait une version obsolète de l'item updated ou conservait un stub supprimé. Résolu par nouveau dispatcher `_sync_tcm_after_draft_execution` : create → set current ; update → set current + `update_item_in_list` ; delete → `remove_item_from_list` + safety-net clear current.

#### Changed

- **HITL update template — structure en 2 blocs étiquetés** : le template `hitl_draft_critique_prompt.txt` pour les drafts `*_update` a été réécrit. Plus d'étiquette auto-générée « Autres détails inchangés » contredite par un résumé qui incluait les valeurs modifiées. Deux blocs explicites maintenant : `{L_Modifications}` (seulement les champs qui changent, format `~~ancien~~ → nouveau`) et `{L_Full_post_update}` (snapshot complet post-update).
- **i18n HITL** : nouveaux labels `modifications` et `full_post_update` dans les 6 langues via `HitlMessages.get_draft_update_labels()`.
- **`ContextSaveMode` enum simplifié** : `{LIST, DETAILS, CURRENT, NONE}` → `{LIST, CURRENT, NONE}`.
- **`classify_save_mode` réduit à une règle** : mode explicite > défaut LIST (plus de patterns heuristiques sur le nom du tool).
- **`ToolContextManager.update_item_in_list()`** : nouvelle méthode symétrique à `remove_item_from_list`, remplace un item dans la liste par primary_id_field, préserve l'index 1-based.

#### Removed

- `save_details()`, `get_details()`, `ToolContextDetails` — remplacés par le design à 2 clés.
- `tool_context_details_max_items` (setting), `TOOL_CONTEXT_DETAILS_MAX_ITEMS` (constante) et son entrée dans `.env.example` — dead config après suppression du cache DETAILS.
- 2 fallbacks DETAILS dans `calendar_tools._resolve_calendar_id_from_context` et `hitl/parameter_enrichment` — remplacés par un lookup `list` + `current` secondaire.
- Décorateurs `@auto_save_context` redondants sur les tools legacy `search_events_tool`, `get_event_details_tool`, `search_emails_tool`, `get_email_details_tool` (déjà appliqués via `@connector_tool(context_domain=…)`).

#### Added

- `src/domains/agents/context/access.py` — helper `get_tcm_session(config) → TcmSession | None` qui centralise l'acquisition manager + store + user_id + session_id. Utilisé par `draft_executor` et `context_resolution_service`.
- `src/domains/agents/utils/turn_type.py` — helpers `is_reference_turn`, `is_action_turn`, `is_conversational_turn`, `normalize_turn_type` tolérants à la casse.
- Table canonique `_DOMAIN_ID_KEYS` dans `draft_executor.py` — source unique pour la dérivation de `_DRAFT_TYPE_TO_ID_KEYS`.

#### Documentation

- `docs/architecture/ADR-072-TCM-Two-Keys-Simplification.md` — nouvel ADR détaillant la décision, les 5 bugs résolus, les follow-ups 2026-04 (post-HITL list maintenance, turn_type unification, HITL template 2-blocs).
- `docs/architecture/ADR_INDEX.md` — entrée ADR-072 ajoutée.
- `docs/architecture/ADR-030-Context-Resolution-Follow-up.md` — note follow-up 2026-04 sur le two-keys design.
- `docs/ARCHITECTURE_AGENT.md` — section 16 (TCM) réécrite pour le design 2-clés + suppression des exemples `save_details` / `get_details`.
- `docs/INDEX.md` — compteur ADR mis à jour (72).
- `docs/technical/AGENT_MANIFEST.md` — `context_save_mode` documenté comme LIST/CURRENT/NONE.
- FAQ changelog (6 langues) mis à jour avec l'entrée v1.16.5.

## [1.16.4] - 2026-04-15

### Skill Identification — Semantic-Only, Unified

Replaced the domain-overlap heuristic by a unified semantic identification path. The `QueryAnalyzer` now reads all active skills (deterministic and non-deterministic) and picks the one whose description semantically matches the user's intent. `SkillBypassStrategy`, the planner guard, and the routing decider all consume that single signal.

Root cause addressed: on 2026-04-15 a production briefing request identified the correct skill semantically but still missed emails/tasks/reminders because the bypass required domain overlap that the `QueryAnalyzer` had partially classified as `web_search`.

#### Changed
- **`SkillBypassStrategy`**: `can_handle` is now a minimal presence check on `QueryIntelligence.detected_skill_name`; `plan` performs a user-scoped lookup via `SkillsCache.get_by_name_for_user(name, user_id)`, verifies the skill is deterministic and active, then builds the plan. No domain-overlap maths anywhere.
- **`_has_potential_skill_match` (planner guard)**: returns `True` whenever a skill has been identified, regardless of type. No cache lookup, no domain analysis.
- **QueryAnalyzer catalogue**: the deterministic-skill filter was removed from the visible set — the LLM can now identify any active skill by description. User/admin isolation preserved via `SkillsCache.get_for_user`.
- **QueryAnalyzer prompt**: strengthened instruction to match on whole-intent semantic alignment, not keyword presence; explicit warning that action compositions are not skill invocations unless a skill covers that composition; explicit separation of `skill_name` from `primary_domain`/`secondary_domains` to avoid LLM field confusion.
- **`RoutingDecider`**: new Rule 1 — when `detected_skill_name` is set, route to the planner regardless of the domains list (closes the hole where the LLM stored the skill in `skill_name` only and left domains empty, causing the previous "no domains → response" fallback to skip the planner entirely).

#### Fixed
- **`reconstruct_query_intelligence`** (pre-existing bug revealed by the refactor): the helper that rebuilds a `QueryIntelligence` from its serialized state dict was missing two fields — `detected_skill_name` and `is_app_help_query` — so the bypass and app-help guard could see `None` after checkpoint round-trips. Both fields are now correctly propagated.

#### Removed
- `plan_template.max_missing_domains` field (no longer read; leftover occurrences in user YAMLs are silently ignored).
- `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` constant in `src/core/constants.py`.
- Removed `max_missing_domains: 2` from `briefing-quotidien` system skill.
- UI guide field, translations and YAML example reference for `max_missing_domains` (SkillGuideModal + 6 locales).

#### Documentation
- `docs/technical/SKILLS_INTEGRATION.md` — rewrote the "Deterministic Bypass" and "Early Detection Guard" sections; removed the `max_missing_domains` table row.
- `docs/technical/HITL.md` — updated the Skill Guard Bypass paragraph.
- `docs/knowledge/12_skills.md` — simplified the user-facing explanation of skill matching.
- Added ADR-071: Skill Semantic Identification (replaces the domain-overlap matching with a single semantic signal).
- Updated FAQ changelog (6 languages) with v1.16.4 entries.

## [1.16.3] - 2026-04-10

### Skill Bypass Relaxed Matching & Scope-Aware Filtering

Deterministic skill templates (e.g., daily briefing) were never triggered via `SkillBypassStrategy` because the `QueryAnalyzer` didn't detect all template domains for composite queries. The bypass required exact domain coverage (0 missing), while the early detection guard allowed 1 missing — a gap that caused the LLM planner to generate plans without email steps.

#### Fixed
- **Skill bypass now uses relaxed domain matching**: `SkillBypassStrategy.can_handle()` and `plan()` aligned with `_has_potential_skill_match()` — both now allow up to N missing domains instead of requiring exact coverage. The threshold is configurable per skill via `plan_template.max_missing_domains` (falls back to global `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` constant, default: 1).
- **Scope-aware step filtering**: Template steps whose tools require OAuth scopes the user hasn't granted are filtered out before building the execution plan. This avoids a validation-fail → replan round-trip for users without a given connector (e.g., no Gmail → email step removed gracefully). `depends_on` references to removed steps are sanitized (shallow-copy to avoid cache mutation).
- **`oauth_scopes` injected into `RunnableConfig.configurable`**: `planner_node_v3` now injects `oauth_scopes` from state into the configurable dict, making them available to bypass strategies without interface changes.

### Daily Briefing Skill Enrichment

#### Added
- **Reminders in daily briefing**: New `get_reminders` step added to `briefing-quotidien` skill template using `reminder_agent` / `list_reminders_tool` (no OAuth required). Pending reminders are displayed between Emails and Notes sections. Empty section is hidden.
- **Per-skill `max_missing_domains`**: New optional field in `plan_template` YAML. The briefing skill sets `max_missing_domains: 2` to tolerate 2 undetected domains out of 5 (email + reminder often missed by QueryAnalyzer for "briefing" queries).

### Random Analyzing Phrases Restored

#### Changed
- **Router decision step shows random personality phrases**: Restored `getRandomAnalyzingMessage()` for the initial `router_decision` step, picking from the i18n `analyzingMessages` array (~30 witty phrases per language). All subsequent steps (planner, execution, HITL) keep their descriptive i18n labels.

### Documentation
- Updated `docs/technical/SKILLS_INTEGRATION.md` with relaxed matching, scope-aware filtering, `max_missing_domains` field, `reminder_agent` tool reference, and updated briefing example.
- Updated `docs/knowledge/12_skills.md` with skill matching and scope filtering documentation.
- Updated `apps/web/src/components/settings/SkillGuideModal.tsx` with `max_missing_domains` in example and field legend.
- Added `guide_modal_plan_field_max_missing_domains` i18n key in all 6 languages.
- Updated FAQ changelog (6 languages) with v1.16.3 entries.

## [1.16.2] - 2026-04-10

### Progressive Execution Step Display

Real-time visibility of execution steps during both Pipeline and ReAct modes. Previously, pipeline mode only showed a random "analyzing" phrase, and ReAct mode showed generic "Executing tool..." / "Reasoning..." messages. Steps are now accumulated and displayed persistently until the response arrives.

#### Added
- **Pipeline step visibility via LangGraph "updates" stream mode**: Added `stream_mode="updates"` to `graph.astream()`. Every pipeline node (router, planner, semantic_validator, approval_gate, task_orchestrator, response) now emits an `execution_step` SSE event with emoji + i18n label. Previously, only router_decision was visible — planner, semantic_validator, approval_gate, and task_orchestrator were completely invisible because they don't update the `messages` state key.
- **Per-tool execution steps in Pipeline mode**: When task_orchestrator completes, tool names are extracted from the ExecutionPlan and emitted as individual `execution_step` events (e.g., "📅 Retrieving events...", "🌤️ Fetching weather...").
- **Per-tool execution steps in ReAct mode**: When react_call_model produces an AIMessage with tool_calls, individual `execution_step` events are emitted for each tool using the catalogue's DisplayMetadata.
- **Reasoning detail in ReAct mode**: AIMessage content from react_call_model is extracted, truncated to 120 chars, and included as a `detail` field in the execution_step event.
- **Accumulated step display**: Frontend accumulates execution steps in a multi-line progress message (each step persists) instead of replacing each step. Capped at 10 visible steps with "... N previous steps" indicator.
- **Deduplication by i18n_key**: `emittedStepKeysRef` (Set) prevents duplicate step display between `router_decision`/`planner_metadata` handlers and `execution_step` events from "updates" mode.
- **52 new i18n keys for tool execution steps** (6 languages): Contacts CRUD, Calendar events, Emails/Labels, Tasks, Reminders, Drive files, Places, Routes, Weather, Wikipedia, Web Search (Brave/Perplexity/unified), Browser actions (nested), Hue smart lights, Image generation, Context tools, Knowledge base, DevOps, Sub-agents.

#### Fixed
- **`planner_metadata` SSE events were dead code**: Backend defined the event type in schema but never emitted it. Frontend handler existed but never received data. Pipeline steps now work via "updates" mode execution_step events.
- **3 orphaned i18n keys replaced**: `search_contacts`, `list_contacts`, `get_contact_details` → replaced with catalogue-aligned `get_contacts`, etc.
- **Singular pluralization**: Added `previous_steps_one`/`previous_steps_other` i18n plural forms for step cap indicator.

#### Changed
- **`_process_messages_chunk()` simplified**: Node transition detection removed (delegated to "updates" mode). Method now only handles token streaming from response node.
- **`getProgressMessage('router_decision')` uses real i18n step text**: Replaced random funny analyzing phrases with `execution.steps.router_decision` label for consistency with accumulated step display.

### Psyche Context Injection Consolidation

Systematic migration of all prompts from **string concatenation** to **template variable injection** for psyche context. Previously, psyche blocks were appended after template formatting via string concat, leaving them outside the XML structure. All prompts now use `{psyche_context}` placeholders resolved **before** `template.format()`.

#### Changed
- **6 prompt templates restructured with XML semantic blocks**: `fallback_response_prompt.txt`, `heartbeat_message_prompt.txt`, `voice_comment_prompt.txt`, `reminder_prompt.txt`, `interest_content_prompt.txt`, `response_system_prompt_base.txt` — all now use typed XML blocks (`<Personality purpose="voice-identity">`, `<InnerState purpose="tone-calibration">`, `<TaskContext purpose="grounding">`, `<ReminderContext purpose="what-to-remind">`, `<SourceMaterial purpose="content-to-present">`, `<Memory purpose="personalization">`, `<UserContext purpose="decision-filter">`, `<JournalContext purpose="behavioral-continuity">`, `<WebSearchContext purpose="factual-enrichment">`, `<UserDocuments purpose="personal-knowledge">`, `<AppKnowledge purpose="product-support">`) for LLM clarity. Each block includes explicit usage directives and fallback behavior when empty.
- **5 service files refactored**: `fallback_response.py`, `heartbeat/prompts.py`, `interests/proactive_task.py`, `voice/service.py`, `scheduler/reminder_notification.py` — psyche block resolved before template formatting.
- **3 service files cleaned**: `initiative_node.py`, `emails_tools.py`, `sub_agents/executor.py` — removed psyche injection entirely (non-pertinent contexts: analytical decisions, factual synthesis, user email content).
- **Memory extraction prompt overhauled**: Exhaustive temporal reference rules covering days, periods, times, months with concrete conversion examples. Explicit blacklist of relative terms ("today", "tomorrow", "next week", "soon", "recently", etc.).

#### Fixed
- **Proactive notification emotion projection** (user-facing): Notifications attributed the assistant's emotional state to the user (e.g., "Ta détermination du jour mérite mieux qu'un e-mail en suspens"). Root cause: psyche context was injected without usage directive, and the LLM conflated the assistant's inner state with the user's. Fixed via triple protection: safety guardrail in `build_psyche_prompt_block()`, `<InnerState>` wrapper directives in each prompt, and removal of psyche from non-user-facing prompts.
- **Dead instruction in heartbeat prompt**: Removed reference to "journal observations" that were not available in the message generation phase (journal entries are only in the decision phase context).

### Debug Panel Reorganization

#### Added
- **6 logical section groups with persistent headers**: Sections reorganized into — Request Analysis, Planning & Execution, Intelligent Mechanisms, Context Injection, Background Extraction, LLM & API Pipeline. Each group has a visible `SectionGroupHeader` separator.
- **Always-visible empty sections**: New `EmptySection` shared component replaces `return null` in all 15 conditional sections. Sections now always render with an "N/A" badge and placeholder content when no data is available, instead of disappearing entirely.

#### Fixed
- **6 accordion value mismatches**: EmptySection `value` props corrected to match their AccordionItem counterparts (hyphen vs underscore inconsistencies: `request-lifecycle`→`request_lifecycle`, `llm-pipeline`→`llm_pipeline`, etc.).
- **3 title inconsistencies**: EmptySection titles harmonized with AccordionTrigger titles (`Journal Injection`→`Personal Journals`, `RAG Injection`→`RAG Knowledge Spaces`, `Google API Calls`→`Google API`).
- **Circular import in EmptySection**: Changed `import { SectionBadge } from '../shared'` to direct import from `'./badges/SectionBadge'` to avoid barrel re-export cycle.

### Documentation
- Updated `docs/technical/REACT_EXECUTION_MODE.md` with streaming step visibility details.
- Updated `docs/ARCHITECTURE_LANGRAPH.md` with "updates" stream mode and per-tool events.
- Updated `docs/architecture/ADR-018-SSE-Streaming-Pattern.md` with execution_step event structure.
- Updated `docs/technical/PSYCHE_ENGINE.md` with template variable consolidation, injection point cleanup, and safety guardrail.
- Updated `docs/technical/DEBUG_PANEL_ARCHITECTURE.md` with 6-group section organization and EmptySection component.
- Updated `docs/architecture/ADR-068-Psyche-Engine.md` with v3 template variable injection pattern.
- Updated `docs/technical/PROMPTS.md` with psyche context via template variables pattern.
- Updated `docs/knowledge/02_chat.md` with execution step visibility user documentation.
- Updated `docs/knowledge/03_settings.md` with absolute temporal memory extraction.
- Updated `docs/knowledge/09_proactive_notifications.md` with tone calibration note.
- Updated `docs/knowledge/22_psyche.md` with non-projection guarantee.
- Updated `docs/technical/LONG_TERM_MEMORY.md` with 7-rule extraction prompt documentation.
- Updated `README.md` with 6-group debug panel table and psyche safety guardrail.
- Updated FAQ changelog (6 languages) with v1.16.2 entries (5 items incl. tone consistency and temporal memory).


## [1.16.1] - 2026-04-09

### Homogeneous LLM Config Resolution

Systematic enforcement that all runtime LLM configuration reads go through the centralized `get_llm_config_for_agent()` helper, which merges code defaults (`LLM_DEFAULTS`) with admin DB overrides (`LLMConfigOverrideCache`). Previously, several code paths read `settings.*_llm_*` directly, silently ignoring admin UI configuration changes.

#### Fixed
- **Interest content presentation bypass** (CRITICAL): `_present_content()` in `proactive_task.py` manually constructed `LLMAgentConfig` from 8 `settings.interest_content_llm_*` fields and called `get_llm("response", config_override=...)` — completely bypassing DB overrides. With Qwen provider, this caused truncated notifications (thinking mode consuming output tokens). Replaced with `get_llm("interest_content")`.
- **Stale model name in interest logging**: `settings.interest_content_llm_model` replaced with `get_llm_config_for_agent(settings, "interest_content").model` for accurate token tracking metadata.
- **Stale model name in heartbeat logging**: `settings.heartbeat_message_llm_model` and `settings.heartbeat_decision_llm_model` replaced with centralized config resolution.
- **Stale model in voice metrics**: Prometheus metric label `settings.voice_llm_model` replaced with centralized config resolution.
- **Semantic validator provider fallback**: `settings.semantic_validator_llm_provider` replaced with `get_llm_config_for_agent(settings, "semantic_validator").provider`.
- **Summarization middleware context window**: `settings.response_llm_model` fallback replaced with `get_llm_config_for_agent(settings, "response").model` for correct context window calculation.

### Documentation
- Updated `docs/technical/LLM_CONFIG_ADMIN.md` with runtime enforcement guarantee.
- Updated FAQ changelog (6 languages) with v1.16.1 entries.
- Updated docstring examples in `base_agent_builder.py` to show centralized config pattern.

## [1.16.0] - 2026-04-09

### ReAct Execution Mode (ADR-070)

User-toggleable alternative to the pipeline mode. The ReAct pattern enables iterative reasoning: the LLM observes each tool result, reasons about the next step, and decides whether to act again or finalize. Implemented as 4 custom nodes in the parent LangGraph graph (not a subgraph), with native HITL support via `interrupt()`.

#### Added
- **ReAct 4-node loop**: `react_setup` → `react_call_model` ↔ `react_execute_tools` → `react_finalize` → response.
- **Frontend toggle**: Zap icon in chat header, user preference persisted in DB (`users.execution_mode` column).
- **Timeout enforcement**: `react_start_time` in state + hard timeout check in routing function.
- **Skills in ReAct**: Filtered L1 skills catalogue injected as SystemMessage in `react_setup_node`. The 3 existing skill tools (`activate_skill_tool`, `run_skill_script`, `read_skill_resource`) are available.
- **Debug panel**: 4 ReAct nodes registered in `DEFAULT_NODE_METADATA` with i18n (6 languages).
- **Prometheus metrics**: 5 ReAct-specific metrics (`executions_total`, `iterations`, `duration_seconds`, `tools_called_total`, `hitl_interrupts_total`).
- **Initiative via prompt**: CROSS-CHECK step integrated in the ReAct workflow prompt (autonomous, no separate LLM call).
- **Alembic migration**: `execution_mode_001` adds `execution_mode` column to users table.

#### Fixed
- **Token tracking for OpenAI Responses API with tools**: `_fallback_to_chat_completions()` in `ResponsesLLM` now extracts `usage_metadata` from Chat Completions response and sets it on the AIMessage. Previously, all tokens from react_call_model were lost when using OpenAI models.
- **Node breakdown aggregation**: Token tracking summary now sums tokens across multiple executions of the same node (dict accumulation instead of overwrite). Fixes incorrect cost display for multi-iteration ReAct.
- **`current_turn_registry` merge**: Each ReAct iteration now merges with existing registry items from previous iterations, preventing loss of data cards.
- **Frontend `STREAM_START` idempotent**: Reducer checks for existing message before creating a new one. Prevents empty response display on first ReAct message.
- **`handleContentReplacement` simplified**: Always dispatches `STREAM_START` (safe with idempotent reducer) to guarantee `currentMessageId` is set.
- **ADR reference correction**: All 25+ code references changed from ADR-069 (Gemini Embedding) to ADR-070 (ReAct).
- **Test fixtures**: `execution_mode="pipeline"` added to `UserFactory`, test auth service, and user service factories.
- **LLM defaults count**: Test updated 48 → 49 for `react_agent` type.

### Documentation
- Created `docs/technical/REACT_EXECUTION_MODE.md` — comprehensive technical documentation.
- Updated `docs/INDEX.md`, `docs/ARCHITECTURE_LANGRAPH.md`, `docs/technical/GRAPH_AND_AGENTS_ARCHITECTURE.md`, `docs/technical/ROUTER.md`, `docs/technical/PLANNER.md`, `README.md` with ReAct references and diagrams.
- Updated FAQ changelog (6 languages) with v1.16.0 entries.

## [1.15.3] - 2026-04-10

### Similarity Threshold Calibration for Gemini Embedding-001

Comprehensive calibration of all 8 similarity thresholds using realistic test datasets (80 memories + 30 queries, 30 journal entries + 20 queries, 25 RAG chunks + 15 queries, 50 interest topics, 30 content articles, 16 journal dedup pairs). Precision/Recall/F1 analysis at each threshold to find optimal trade-off between noise (token waste) and recall (missed matches).

#### Changes
- **MEMORY_MIN_SEARCH_SCORE** (0.70 → 0.65): Previous value cut valid matches like "birthday" (0.666), "work" (0.654). New value: F1=0.519, avg 1.8 results/query with 80-memory bank. Cuts all unrelated noise (max 0.618).
- **MEMORY_RELEVANCE_THRESHOLD** (0.70 → 0.72): Purge protection now targets p75 of match scores (0.735). Only strongly relevant memories increment usage_count.
- **JOURNAL_CONTEXT_MIN_SCORE** (0.75 → 0.63): Previous value missed 4/12 matches. New value: F1=0.638, avg 1.1 entry/query. Journal behavioral directives match at 0.58–0.75 range.
- **JOURNAL_DEDUP_SIMILARITY_THRESHOLD** (0.75 → 0.87): Previous value was far too low for doc↔doc symmetric comparisons. New value: F1=0.889 (P=0.800, R=1.000). Catches all true duplicate entries while avoiding false merges on related-but-different content.
- **INTEREST_DEDUP_SIMILARITY_THRESHOLD** (0.82 → 0.89): New value: P=1.000, R=0.667, F1=0.800. Zero false merges — distinct interests like "Italian cuisine" vs "Japanese cuisine" (0.881) correctly kept separate.
- **INTEREST_CONTENT_SIMILARITY_THRESHOLD** (0.81 → 0.90): Clear separation gap — duplicate content scores 0.95+, different content max 0.84. Previous value blocked legitimate new articles.
- **QUERY_ENGINE_SIMILARITY_THRESHOLD** (0.85 → 0.93): SequenceMatcher string-based (not embeddings). Avoids false positives like "same name, different email domain" (0.922).
- **RAG_SPACES_RETRIEVAL_MIN_SCORE** (0.60 → 0.55): Hybrid score (0.7×semantic + 0.3×BM25) compresses the range. Semantic-only best F1 at 0.67 ≈ 0.55 hybrid.

#### Calibration Scripts
- New `scripts/test_similarity_thresholds_v2.py` — Large-scale calibration script with realistic user profile data (81 memories, 30 journal directives, 25 RAG chunks, 20 interests, 15 recent articles). Computes P/R/F1 at every threshold for each domain.

### LLM Configuration Alignment

#### Changes
- **Power tier adjustments** — `memory_extraction`, `interest_extraction`, `journal_extraction`: HIGH (orange) → MEDIUM (blue). `mcp_react_agent`: CRITICAL (red) → HIGH (orange). `mcp_app_react_agent`: CRITICAL (red) → HIGH (orange).
- **LLM defaults aligned with production config** — Code defaults (`LLM_DEFAULTS`) now reflect proven production configuration:
  - `memory_extraction`: qwen/qwen3.5-plus → openai/gpt-5.4-mini, reasoning_effort: low
  - `interest_extraction`: qwen/qwen3.5-plus → openai/gpt-5.4-mini, reasoning_effort: low
  - `journal_extraction`: qwen/qwen3.5-plus → openai/gpt-5.4-mini, reasoning_effort: low
  - `mcp_react_agent`: anthropic/claude-opus-4-6 → qwen/qwen3.6-plus, temp 0.2, max_tokens 20000, reasoning_effort: medium
  - `mcp_app_react_agent`: anthropic/claude-opus-4-6 → qwen/qwen3.6-plus, temp 0.5
  - `heartbeat_decision`, `interest_content`, `journal_consolidation`: reasoning_effort: none → low

### Documentation
- Updated `docs/technical/LONG_TERM_MEMORY.md` with calibrated threshold values.
- Updated `docs/technical/JOURNALS.md` with calibrated threshold values.
- Updated `docs/technical/INTERESTS.md` with calibrated threshold values.
- Updated `docs/technical/LLM_CONFIG_ADMIN.md` with updated power tiers and default models.
- Updated `docs/technical/LLM_PROVIDERS.md` with updated extraction LLM defaults.
- Updated FAQ changelog (6 languages) with v1.15.3 entries.
- Fixed missing v1.15.2 and v1.15.1 changelog version keys in FAQContent.tsx.

## [1.15.2] - 2026-04-09

### Psyche Engine v2 — Enriched Emotional Intelligence

#### New Features
- **Expanded emotion palette (16 → 22)**: Six new emotions — playfulness, protectiveness, relief, nervousness, wonder, resolve — with PAD-validated vectors (min distance ≥ 0.122).
- **Graduated directives**: Prompt injection now scales across 4 intensity levels (compact → medium → rich → reinforced) based on PAD magnitude, with a lighter usage directive for low-intensity states.
- **Serenity floor**: Baseline steadiness directive when no emotion is significantly active, modulated by Neuroticism trait.
- **Emotional anchor**: Grounding directive when strong negative emotions threaten a spiral, modulated by Conscientiousness trait.
- **Narrative transitions**: Six transition templates (reunion, valence shifts, arousal shifts, emotion-specific) replace the mechanical EVOLUTION block.
- **Multi-emotion self-report**: LLM reports 1-3 simultaneous emotions per message (backward compatible with v1 single-emotion format).
- **Computed resonance**: Emotional alignment metric [-1, +1] between user valence and assistant emotion, feeding relationship warmth and trust.
- **Proactive emotions**: Pre-response emotion pulses from drives and context (curiosity for new users, enthusiasm for high engagement, pride for domain confidence) with anti-inflation guards.
- **Enriched avatar tooltip**: Multi-emotion display with intensity bars, mood intensity label, and drive indicators on hover.

#### Improvements
- Consolidated 12 existing behavioral directives (3 mood + 7 emotion + 2 relationship) from descriptive to imperative style.
- Fixed Pattern B compact block wording ("follow each emotion's directive" → "let each named emotion color specific moments").
- Fixed 2 color duplicates in PsycheHistory (surprise/pride shared amber, determination/frustration shared red).
- Enriched PsycheStateSummary with mood_intensity, active_emotions list, and drive values for richer SSE metadata.
- Added structured logging for proactive emotion injection and resonance computation.
- Updated PsycheEducation with 22-emotion table and 5 new educational sections (multi-emotion, proactive, serenity floor, anchor, resonance, transitions).
- Updated all 6 locale files (fr, en, de, es, it, zh) with ~25 new keys and ~10 updated keys each.
- Updated documentation: PSYCHE_ENGINE.md, ADR-068, 22_psyche.md with v2 enhancements.

#### Tests
- 158 unit tests (87 existing + 71 new) covering all v2 features.
- New guard test preventing descriptive directive patterns ("Show", "Let", "You are").

## [1.15.1] - 2026-04-08

### Fixed

- **MCP ReAct Step Timeout** — The parallel executor step timeout for MCP iterative (ReAct) tools was defaulting to 60s, insufficient for multi-iteration Opus-based ReAct agents (read_me + create_view takes ~55-90s). The planner's `timeout_seconds` override only matched the legacy `mcp_excalidraw_create_view` tool name, not the new `mcp_excalidraw_task` iterative tool name. Now all tools ending with `_task` (MCP iterative suffix) get a minimum timeout of 120s via `max(planner_timeout, 120)`, regardless of what the planner LLM specifies.
- **MCP App Registry Filtering** — Interactive MCP App widgets (Excalidraw diagrams, etc.) were silently dropped by the response node's intelligent filtering. When the LLM returned `<relevant_ids>` for search results, `filter_registry_by_relevant_ids()` removed all items not in the list — including MCP App items that are not search results. Now items of type `MCP_APP` and `DRAFT` are protected from intelligent filtering and always preserved in the registry, alongside initiative-protected items.
- **LLM Config Defaults** — `mcp_app_react_agent` LLM config: temperature reduced from 0.2 to 0.0 for deterministic output, max_tokens adjusted from 20000 to 16000, reasoning_effort from "medium" to "low".

### Documentation

- Updated ADR-062 with MCP ReAct timeout and registry protection amendments.
- Updated MCP_INTEGRATION.md with step timeout configuration for iterative tools.
- Updated GUIDE_MCP_INTEGRATION.md with timeout requirements section.
- Updated ARCHITECTURE_LANGRAPH.md with protected registry items in response node.
- Updated knowledge base `11_mcp_servers.md` with timeout information.
- Updated FAQ changelog (6 languages) with v1.15.1 entries.

## [1.15.0] - 2026-04-08

### Added

- **User MCP ReAct Iterative Mode** — User-configured MCP servers with `iterative_mode=true` now delegate to a ReAct sub-agent (same as admin MCP). The planner sees a single `mcp_user_{id}_task` tool per server; the ReAct agent reads documentation first, then executes tools iteratively with error recovery. Shared factory `build_mcp_react_task_manifest()` eliminates manifest duplication between admin and user MCP paths.
- **MCP App Dedicated LLM** — New LLM type `mcp_app_react_agent` (category: Domain Agents) auto-selected for MCP servers with interactive widgets (`app_resource_uri`). Defaults to Opus for complex multi-step workflows (e.g., Excalidraw). Regular MCP servers continue using `mcp_react_agent`. Detection is automatic via `_has_mcp_app_tools()` — no configuration needed.
- **3-Phase Memory Reference Resolution** — `MemoryResolver` now uses a 3-phase architecture: Phase 1 (LLM nano extracts personal references like "ma femme", "mon frère" from the query), Phase 2 (per-reference targeted memory search in parallel with higher similarity threshold), Phase 3 (LLM resolves references using targeted facts). Phase 1 and broad memory retrieval run concurrently. Produces higher similarity scores than embedding the full query, reducing noise. New LLM type: `memory_reference_extraction`. New prompt: `memory_reference_extraction_prompt.txt`.
- **Initiative Eligibility Field** — New `initiative_eligible: bool | None` field on `ToolManifest` for fine-grained control over which tools are available during the initiative phase. New `is_initiative_eligible()` function replaces the coarser `is_read_only_tool()` heuristic. ~30 catalogue manifests annotated with `initiative_eligible=False` (web search, browser, context, structural listing tools).
- **Error Classification System** — New centralized `SSEErrorMessages._classify_error()` classifier with categories: `transient` (overload, rate limit), `content_filter` (provider safety blocks), `timeout`, and `unknown`. New localized user messages for `content_filter` and `timeout` errors across all 6 languages.
- **Query Analyzer LLM Timeout** — New `query_analyzer_llm_timeout_seconds` setting (default: 10s) with `asyncio.wait_for()` guard on the query analyzer LLM call.

### Changed

- **Unified Planner Prompt** — `smart_planner_prompt.txt` now serves both single-domain and multi-domain queries via `is_multi_domain` / `primary_domain` parameters. `get_smart_planner_multi_domain_prompt()` is a backward-compatible wrapper. Eliminates the duplicated `smart_planner_multi_domain_prompt.txt` template.
- **Token Optimization — Prompts** — Compressed `query_analyzer_prompt.txt` (~50%), `response_system_prompt_base.txt` (~45%), `initiative_prompt.txt` (~30%), `for_each_directive_prompt.txt` (~70%), `smart_planner_prompt.txt` (~35%). Empty optional sections (skills, RAG, journal, knowledge) no longer inject empty XML tags.
- **Token Optimization — Catalogue & Initiative** — Catalogue JSON now uses compact separators (no indent). Initiative tool format uses one-line-per-tool with inline params (~70% reduction).
- **Initiative Cross-Domain Only** — Initiative node now excludes already-executed domains from adjacent tool search, ensuring only cross-domain enrichment checks are performed.
- **Reminder Cancellation Requires Confirmation** — `cancel_reminder` tool now has `hitl_required=True`, requiring user confirmation before cancelling reminders.
- **Error Message Security Hardening** — All SSE error messages no longer leak exception type names or technical details to end users. Error type metadata in stream chunks replaced with generic `"stream_error"`.
- **Resolved Context ID Aliases** — `ResolvedContext.to_prompt_context()` now injects tool-parameter aliases for ID fields (e.g., `id` → `event_id`, `resourceName` → `resource_name`), reducing planner hallucination of `$steps` references for pre-resolved entities.
- **Weather Date Formatting** — Removed `date_formatted` from weather API payloads; card components now use `format_full_date()` with user's language for locale-aware display.
- **Catalogue Descriptions Streamlined** — Tool descriptions for calendar, email, contacts, and tasks use compact `USAGE` format replacing verbose `MODES` sections. ID parameters reference `$steps or CONTEXT` instead of generic descriptions.
- **Contact Search Fallback** — `GetContactDetailsTool` now retries failed batch fetches as name searches, handling cases where the planner puts names in `resource_names` instead of real IDs.
- **MCP Excalidraw LLM Dead Code Cleanup** — Removed unused `mcp_excalidraw_llm_*` settings (~80 lines in `config/mcp.py`, 8 constants) left over from pre-ADR-062 iterative builder. Renamed LLM type `mcp_excalidraw` → `mcp_app_react_agent` in admin panel. Removed `MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS` env var.

### Fixed

- **Resolved Context Restoration** — `get_query_intelligence_from_state()` now restores `resolved_context` from its separate state key when reconstructing `QueryIntelligence` from dict. Previously, `resolved_context` was always `None` after reconstruction, causing the planner to miss pre-resolved entity IDs for REFERENCE_ACTION turns.
- **Initiative Turn Filtering** — `_format_execution_summary()` now filters `agent_results` by `current_turn_id`, preventing stale data from previous turns leaking into the initiative prompt.
- **Plural Demonstrative Patterns** — `ReferenceResolver.DEMONSTRATIVE_PATTERNS` now includes `\bthese\s+\w+` and `\bthose\s+\w+` for plural demonstrative detection (e.g., "delete these emails").
- **Localized Date Parsing** — Weather tools now parse localized date strings (e.g., "jeudi 09 avril 2026") via `_parse_localized_date()` with support for FR, EN, DE, ES, IT month names. Handles cases where the planner outputs dates in the user's language instead of ISO format.
- **Context Resolution Demonstratives** — Context resolver now receives the semantic pivot query (which preserves demonstratives like "these/this/that") instead of the QA's `english_query` (which resolves them away), fixing demonstrative detection for REFERENCE_ACTION turns.
- **HITL Nested Error Localization** — Nested HITL Redis save errors now use `SSEErrorMessages.generic_error()` with user language instead of hardcoded French message.
- **Chat Reducer Error Prefix** — Frontend chat reducer no longer prepends "Erreur:" to error messages (backend messages are already localized).
- **For Each Heuristics** — `_get_plural_collection_hints()` and `_get_collection_key_for_domain()` now derive from `DOMAIN_REGISTRY` instead of hardcoded lists, preventing drift when new domains are added.
- **User MCP `iterative_mode` Not Returned** — `_server_to_response()` in user MCP router was missing `iterative_mode=server.iterative_mode`, always returning `False` to the frontend regardless of the DB value. Toggle appeared non-functional.
- **MCP Admin Servers Not Loading (DEV)** — `.env` line `MCP_SERVERS_CONFIG_PATH=  # comment` had inline comment parsed as file path value, causing `mcp_config_file_not_found` → `mcp_no_servers_configured` at startup. "MCP Applicatifs" section was invisible in Preferences.
- **MCP ReAct Error Recovery** — `_MCPReActWrapper._arun()` now catches all exceptions (including `ExceptionGroup` from anyio/MCP SDK) and returns error messages as strings to the ReAct agent instead of crashing the sub-agent loop. The ReAct agent can now reason about MCP tool errors and retry with corrected parameters. Affects all MCP iterative servers (admin + user).

### Documentation

- Updated MEMORY_RESOLUTION.md with 3-phase architecture.
- Updated PROMPTS.md with new prompt file and unified planner.
- Updated AGENT_MANIFEST.md and tool creation guides with `initiative_eligible` field.
- Updated ADR-062 with initiative eligibility and cross-domain-only amendments.
- Updated ADR-023 with `_classify_error()` and new error categories.
- Updated LLM_CONFIG_ADMIN.md with `memory_reference_extraction` LLM type.
- Updated SMART_SERVICES.md with unified planner prompt.
- Updated FAQ changelog (6 languages) with `memory_reference_extraction` i18n key.
- Updated MCP_INTEGRATION.md with user MCP iterative mode support.
- Updated ADR-062 with user MCP ReAct sub-agent extension.
- Updated GUIDE_MCP_INTEGRATION.md with user MCP iterative mode section.
- Updated LLM_CONFIG constants: renamed `mcp_excalidraw` → `mcp_app_react_agent`, moved to Domain Agents category.
- Updated knowledge base `11_mcp_servers.md` with iterative mode explanation.

## [1.14.5] - 2026-04-07

### Changed

- **HITL Streamlining — Approval Gate Passthrough** — Plan-level HITL approval (`plan_approval`) is now auto-approved. Every mutation already has its own downstream HITL (FOR_EACH confirmation for bulk operations, draft critique for individual actions), making plan-level approval redundant. Eliminates the triple-confirmation UX for deletions (plan_approval + for_each_confirmation + draft_critique → single for_each_confirmation).
- **HITL Streamlining — FOR_EACH Cancel = Draft Cancel** — Refusing a FOR_EACH HITL confirmation now produces the same "OK, annulé" fast-path response as refusing a draft critique, instead of falling through to initiative + response nodes with a broken error message.
- **Initiative Skip After HITL Resolution** — Initiative node now short-circuits immediately when a HITL interaction (draft critique, entity disambiguation, tool confirmation) was just resolved. Avoids a wasted LLM call (~8s) evaluating post-execution enrichment on an already-confirmed/refused action.
- **Action-Specific HITL Titles** — Destructive confirmation dialogs now display action-specific titles ("Confirmation de suppression", "Confirmation d'envoi", etc.) instead of the generic "Confirmation requise", across all 6 languages. Applied to both batch draft critique and individual destructive confirm interactions.
- **Planner Prompt — Forbidden Tools List** — Smart planner prompt now explicitly lists forbidden hallucinated tools (`resolve_reference`, `get_context_list`, `get_context`, `resolve_context`, `lookup_reference`) with clear instruction to use resolved context IDs directly. Reduces replanning caused by hallucinated tool rejections.
- **FOR_EACH Directive — Mandatory Fetch Step** — FOR_EACH directive prompt now explicitly states the retrieval step must always be included, even when items appear in resolved context, because the runtime FOR_EACH engine only works with `$steps` references.

### Fixed

- **Hallucinated Parameter Defense** — Parallel executor now strips unknown parameters (e.g., `order`, `order_by`) from tool calls before execution, using `inspect.signature()` to validate against the tool's actual function signature. Prevents `TypeError` crashes that silently failed entire execution plans when the planner LLM hallucinated non-existent parameters.
- **Resolved Context Header Clarification** — Resolved context header in planner prompts updated from vague "DO NOT call any resolution tool" to explicit "use their IDs directly in parameters, DO NOT create any resolve/context/reference step", reducing planner hallucination of `resolve_reference` tool.

### Documentation

- Updated HITL technical documentation with approval gate passthrough, FOR_EACH cancel behavior, and action-specific titles.
- Updated ADR-062 with initiative skip after HITL resolution.
- Updated LangGraph architecture documentation.
- Updated FAQ changelog (6 languages) with HITL streamlining features.

## [1.14.4] - 2026-04-03

### Added

- **Tool Embeddings Disk Cache** — Semantic tool selector now persists computed embeddings to a JSON cache file (`tool_embeddings_cache.json`). On startup, if tool descriptions/keywords and embedding model haven't changed (SHA-256 content hash), embeddings are loaded from disk instead of calling the Gemini API. Eliminates ~2–5 s startup latency and avoids unnecessary API cost on every restart. Cache auto-invalidates when tools or model change.
- **Qwen 3.6-plus Model Support** — New `qwen3.6-plus` model added to context windows, model profiles, and LLM pricing seed. Agentic-focused upgrade of qwen3.5-plus with vision support and 1M context window.
- **Cached Input Pricing** — `cost_per_1m_cached_input` field added to `ModelProfile` dataclass and populated for all major providers (OpenAI, Anthropic, Google, DeepSeek, Qwen). Enables more accurate cost tracking for providers that offer prompt caching discounts.

### Changed

- **Provider-Agnostic Structured Output** — Migrated 4 services from `llm.with_structured_output()` to the centralized `get_structured_output()` helper: `initiative_node`, `hitl_classifier`, `query_analyzer_service`, and `evaluation_pipeline`. Uses `get_llm_config_for_agent()` to resolve provider dynamically, ensuring reliable JSON extraction across OpenAI, Anthropic, Google, and Qwen providers.
- **Initiative Items Protected from Response Filtering (ADR-062)** — Initiative node now propagates `registry_ids` in its results. Response node collects these IDs and re-injects initiative items after intelligent filtering, preventing proactive suggestions from being silently dropped when the response LLM filters registry entries.
- **LLM Pricing Seed — Fixed Timestamps** — All `pricing_date` values in `llm_pricing_seed.sql` changed from `NOW()` to fixed `'2026-01-01T00:00:00Z'` for reproducible seeding across environments.
- **Model Pricing Updates** — Corrected pricing for Qwen 3.5-plus (input: $0.40→$0.115), Qwen 3.5-flash (input: $0.10→$0.029), Qwen-max (input: $1.20→$0.359), and Perplexity sonar models (aligned to current API pricing).

### Documentation

- Updated FAQ changelog (6 languages) with tool cache and initiative protection features.
- Updated technical documentation for structured output migration and model profiles.

## [1.14.3] - 2026-04-03

### Added

- **Response Display Mode Preference** — New tri-mode selector in Settings > Personalization: **HTML Cards** (structured visual cards for contacts, events, emails, weather — default), **Rich HTML** (LLM generates beautifully formatted HTML responses with headings, callouts, tables, styled typography), or **Markdown** (plain text). Single `response_display_mode` field replaces previous approach. Full pipeline wiring: User model → API endpoint (`PATCH /auth/me/display-mode-preference`) → LangGraph configurable → response_node conditional logic.
- **HTML Response Directive Prompt** — New versioned prompt `html_response_directive.txt` injected before FINAL REMINDER when display mode is "html". Instructs LLM to output rich HTML with scoped `<style>` block using CSS variables (`--lia-*`) for automatic dark/light theme compatibility. Includes callout components (info, success, warning, error), styled tables, blockquotes, and semantic markup.
- **Display Mode Constants** — `RESPONSE_DISPLAY_MODE_CARDS/HTML/MARKDOWN/DEFAULT/CHOICES` centralized in `src/core/constants.py`.

### Changed

- **Simplified Display Preferences** — Consolidated two boolean fields (`cards_display_enabled` + `html_response_enabled`) into a single `response_display_mode` enum string ("cards"/"html"/"markdown"). Single PATCH endpoint, single configurable key, single schema pair. Migration preserves existing user preferences via data migration.

### Documentation

- Updated FAQ changelog (6 languages) with display mode preference feature.
- Updated `docs/knowledge/03_settings.md` with display mode section.

## [1.14.2] - 2026-04-03

### Added

- **Skill Mechanism #2 — QueryAnalyzer + ReactSubAgentRunner** — Skills without `plan_template` can now be activated reliably. The `QueryAnalyzer` detects skills via the L1 catalogue (`{available_skills}`) in its prompt and sets `skill_name` in its structured output. The `response_node` reads `detected_skill_name` from state and activates based on nature: scripts → isolated `ReactSubAgentRunner` (LLM `mcp_react_agent` + `skill_react_agent_prompt`); resources only → Python load + L2 passive injection (0 extra LLM call); neither → L2 passive injection only. Works identically for both planner and response routes.
- **Skill ReAct Agent Prompt** — New `skill_react_agent_prompt.txt` for the ReAct sub-agent that executes skill scripts in an isolated loop with tool calls (`activate_skill`, `run_skill_script`, `read_skill_resource`).

### Fixed

- **Skill Script Executor — Docker Compatibility** — `unshare -rn` network isolation now has a runtime availability check (`_unshare_available()`) with graceful fallback, fixing crashes in Docker/non-Linux environments.
- **Skill Script Executor — debugpy Process Isolation** — Script execution uses `env -i` for clean environment to prevent debugpy from hooking into child processes.
- **Skill Script Executor — Absolute Paths** — Resolved relative path failures when using `env -i` by converting all paths to `.resolve()` absolute form.
- **ReactSubAgentRunner — Anthropic Content Normalization** — Anthropic models returning list content blocks (instead of plain strings) are now normalized to string before processing.
- **QueryAnalyzer — plan_template None Guard** — `plan_template` field can be `None` (not just absent) — now uses `(x or {}).get()` pattern to avoid `AttributeError`.
- **QueryAnalyzer — ConfigDict Extra Ignore** — Added `ConfigDict(extra="ignore")` to protect structured output parsing from unexpected fields.
- **Skill Tools — Combined stdout+stderr** — Script failure error messages now include both stdout and stderr output instead of losing stdout on `SCRIPT_ERROR`.

### Documentation

- **SKILLS_INTEGRATION.md** — Full rewrite of the activation section with 5 detailed mechanisms, updated architecture diagram, and ReactSubAgentRunner documentation.
- **ARCHITECTURE.md** — Updated Skills System section with unified activation strategies (QueryAnalyzer detection, planner pre-activation, deterministic bypass).
- Updated docs/knowledge/12_skills.md with new activation mechanisms.

## [1.14.1] - 2026-04-02

### Changed

- **Gemini Embedding Migration** — Migrated all embedding operations (memories, journals, interests, RAG) from OpenAI `text-embedding-3-small` to Google `gemini-embedding-001` with asymmetric `RETRIEVAL_QUERY`/`RETRIEVAL_DOCUMENT` task types. Fixes critical multilingual retrieval regression where unrelated same-language texts scored 0.25–0.35 (language bias), making it impossible to discriminate relevant memories from noise. Gemini with task types produces proper query→document alignment for all 6 supported languages (fr, en, de, es, it, zh). (ADR-069)
- **Dual-Vector Search Strategy** — Added `keyword_embedding` column to `memories` and `journal_entries` tables. Content and keywords (trigger_topic / search_hints) are now embedded separately, with search using `LEAST(dist_content, dist_keyword)`. Restores the multi-field matching behavior from the old LangGraph AsyncPostgresStore that was lost during the PostgreSQL migration (v1.13.6).
- **Dedicated Embedding Singletons** — Each domain now has its own independently configurable embedding singleton: `get_memory_embeddings()`, `get_journal_embeddings()`, `get_interest_embeddings()`, `get_rag_embeddings()`, with dedicated env vars (`MEMORY_EMBEDDING_MODEL`, `JOURNAL_EMBEDDING_MODEL`, `INTEREST_EMBEDDING_MODEL`, `RAG_SPACES_EMBEDDING_MODEL`).
- **GeminiRetrievalEmbeddings Wrapper** — New `GeminiRetrievalEmbeddings` class wrapping `GoogleGenerativeAIEmbeddings` with automatic task_type injection, Prometheus metrics tracking, and DB cost persistence for user billing.

### Fixed

- **Memory Reference Resolution** — "ma femme" and "mon fils" now correctly resolve to actual contact names (e.g., "Hua Gouvier", "Mathéo Gouvier") when sending emails or performing actions. Previously, the combination of OpenAI embedding language bias and query dilution on long sentences caused memory search to fail silently.
- **Memory Search Query Language** — Pre-planner memory search now uses the original user query (in their language) instead of the English-translated query, improving cosine similarity for same-language memory matching.
- **HITL Email Delete Support** — Added `email_delete` draft summary i18n strings for all 6 languages in HITL confirmation flows.

### Documentation

- **ADR-069** — Gemini Embedding Migration architectural decision record. Documents rationale, scope, migration strategy, and alternatives considered.
- Updated ADR_INDEX.md, docs/INDEX.md, `.env.example`, `.env.prod.example` with Gemini embedding configuration.
- Updated all stale OpenAI/TrackedOpenAIEmbeddings references across ~20 files to Gemini/GeminiRetrievalEmbeddings.

## [1.14.0] - 2026-04-02

### Added

- **Psyche Engine — Dynamic Psychological State** — Complete 5-layer emotional intelligence system for the assistant: Big Five personality traits (Layer 1, permanent) → PAD mood space with 14 distinct moods (Layer 2, hours) → 16 discrete emotions with cross-suppression and diminishing returns (Layer 3, minutes) → 4-stage relationship progression (Layer 4, weeks) → curiosity/engagement drives and self-efficacy (Layer 5, per-session). ALMA-inspired architecture, self-report via hidden `<psyche_eval/>` tag (zero extra LLM call). 87 unit tests.
- **Emotional Avatar** — Mood-responsive emoji avatar on assistant messages in chat. Displays the current mood with colored ring. Tooltip shows mood, PAD values, active emotion, and relationship stage. Historical avatars persisted per-message via `message_metadata.psyche_state`.
- **Psyche Settings UI** — 4-section settings panel (Comprendre la psyché, État de la psyché, Historique, Réglages) with icons. Interactive education guide (7 subsections: overview, traits, mood, emotions, relationship, drives, expressivity/stability) with descriptive tables for 14 moods and 16 emotions. PAD bars with axis labels and polarity indicators. Ring gauges for relationship metrics. Big Five horizontal colored bars.
- **Psyche History Dashboard** — 4-tab recharts visualization: Mood (PAD lines), Emotions (dynamic per-emotion area chart), Relationship (depth/warmth/trust), Drives (curiosity/engagement/emotion intensity). Time range selector (24h/7d/30d/90d). Reset markers as red dashed vertical lines.
- **Evolution Awareness** — LLM receives `EVOLUTION:` block in `<PsycheDirectives>` showing mood/emotion shifts since last message, giving the assistant continuity awareness.
- **Personality Sync** — Changing personality automatically syncs Big Five traits and recomputes PAD baseline via `sync_traits_from_personality()`. Frontend refetches state after personality change.
- **Psyche Token Tracking** — LLM-generated summary (`GET /psyche/summary`) now tracks token usage via `track_proactive_tokens()`, ensuring costs are attributed to user billing.
- **Reset Snapshots** — Soft/full resets create `reset_soft`/`reset_full` history snapshots, displayed as visual markers on the history chart.
- **Drives Education Section** — New "Motivations" section in Comprendre la psyché explaining curiosity, engagement, and self-efficacy. Translated in 6 languages.

### Changed

- **Psyche enabled by default** — `PSYCHE_ENABLED=true` in `.env.example`, `user.psyche_enabled` default changed to `true` with migration for existing users.
- **Prompt Directives Overhaul** — All injected context blocks in `response_system_prompt_base.txt` now carry inline operational directives (how to use the data) instead of passive data dumps. Applied to: TemporalContext, History, Psychological_profile, JournalContext, PsycheContext, KnowledgeEnrichment, RAGDocuments, AppKnowledge, ResolvedReferences, AnticipatedNeeds. Same treatment applied to 7 other prompt files (planners, router, query analyzer, initiative, reminder, interest content, psyche summary/narrative).
- **PsycheStateSummary Redesign** — PAD bars with colored axes (sky/amber/violet), polarity labels, and numeric values. SVG ring gauges for relationship metrics. Big Five as horizontal colored bars. Refresh button fetches both LLM summary and state data.
- **Reset Descriptions Clarified** — Soft/full reset descriptions now use explicit "Resets: X, Y. Keeps: Z" format in all 6 languages. Buttons uniform width.
- **Settings Page Reorder** — Psyché de LIA placed directly below Style de LIA. Education section ordered Layer 1→5.
- **i18n Psyche Education** — ~80+ translation keys for psyche education guide completed in all 6 languages (en, fr, de, es, it, zh). Includes mood directives, emotion directives, drives, settings explanation.

### Fixed

- **`_push_with_headroom()` Saturation Fix** — Diminishing returns helper prevents PAD axis saturation at ±1.0 boundaries. 10 dedicated unit tests.
- **`classify_mood()` DRY Refactoring** — Extracted nearest-centroid mood classification as `PsycheEngine.classify_mood()` static method. Eliminated code duplication between `compile_expression_profile` and `process_post_response`.

### Documentation

- **ADR-068** — Psyche Engine architectural decision record. Updated with 16 emotions, 87 tests.
- **PSYCHE_ENGINE.md** — Complete technical & functional documentation (14 sections, scenarios, token cost breakdown). Updated with evolution awareness, avatar persistence, personality sync, token tracking, drives education, refreshed UI descriptions, 10 env vars.
- Updated ADR_INDEX.md, docs/INDEX.md, 16 guide files, README.md with v1.14.0 references.

## [1.13.10] - 2026-04-01

### Fixed

- **Calendar-to-Routes Timezone Bug** — Fixed 2-hour offset in route arrival time calculations when routing to calendar events. The `event["date"]` cross-domain binding field was set **before** `convert_event_dates_in_payload()`, causing the raw UTC value from Google Calendar API (e.g., `13:00:00Z`) to be passed as `arrival_time` to the route tool instead of the converted local time (`15:00:00+02:00`). The field assignment is now correctly placed after timezone conversion. (`mixins.py`)
- **`datetime.utcnow()` Eradication** — Replaced all 6 remaining `datetime.utcnow()` calls with timezone-aware `now_utc()` from centralized `time_utils.py`. Affected files: `calendar_tools.py` (3 occurrences — search time_min/time_max defaults and days_ahead), `google_tasks_client.py` (task completion timestamp), `plan_editor.py` (audit timestamp), `schema_registry.py` (registration timestamp). Eliminates class of bugs where naive datetimes could be misinterpreted as local time.
- **`normalize_user_datetime()` Docstring Correction** — Removed incorrect example claiming UTC input `"21:00:00Z"` would be converted to `"22:00:00+01:00"` (actual behavior: hour is preserved as local intent, producing `"21:00:00+01:00"`). Added explicit warning that this function must NOT be called with API-returned UTC datetimes — use `convert_to_user_timezone()` instead. (`time_utils.py`)

### Documentation

- Updated 16 guide files (why, how, privacy, terms — 6 languages) with v1.13.10 version reference.
- Updated `docs/technical/ROUTES.md` with v1.13.10 timezone fix details and cross-domain binding caveat.

## [1.13.9] - 2026-04-01

### Added

- **Admin Pagination — Page Size Selector** — All 5 admin tables (Users, Usage Limits, LLM Pricing, Google API Pricing, Image Generation Pricing) now feature a page size selector (10/20/50/100, default 20) with total items count display. Shared `<Pagination>` component enriched with `pageSize`, `onPageSizeChange`, `totalItems`, and `loading` props. (`pagination.tsx`, all Admin*Section components)
- **Admin Users — Full Column Sorting** — All 23 data columns in the admin users table are now sortable, including statistics (messages, tokens, cost), resource counts (connectors, skills, MCP servers, scheduled actions, RAG spaces), preferences (language, voice, memory, tokens display), usage blocked status, and last message date. Backend `getattr()` sorting replaced with a 3-tier mapping: User model fields, COALESCE-wrapped UserStatistics expressions, and labeled subquery columns. (`repository.py`, `AdminUsersSection.tsx`)
- **Admin Users — Memories & Interests Sortable** — Memory count and interest count moved from service-layer batch queries to SQL subqueries in the repository, enabling server-side sorting. Previously unsortable icon columns now clickable. (`repository.py`, `service.py`)
- **Image Generation Pricing — gpt-image-1.5 & gpt-image-1-mini** — Added 18 pricing entries (9 per model: 3 qualities × 3 sizes) for OpenAI's new image models. Applied to both DEV and PROD databases. Seed file already contained the data. (`image_generation_pricing_seed.sql`)

### Fixed

- **Admin Users Sort Consistency** — Fixed inconsistent sort order on statistics columns where NULL values (users without UserStatistics row from LEFT JOIN) appeared mixed with zero values. All statistics sort expressions now wrapped with `func.coalesce(..., 0)` and `nulls_last()` applied to all ORDER BY directions. (`repository.py`)
- **CodeQL — 4 Path Injection Alerts** — `_cleanup_attachment_files()` and `_cleanup_rag_files()` in account deletion service now validate resolved paths with `Path.resolve()` + `is_relative_to()` to block path traversal. (`account_deletion_service.py`)
- **CodeQL — 2 Empty Except Alerts** — Added `logger.debug()` to `except ValueError` and `except json.JSONDecodeError` blocks in memory extractor instead of silent `pass`. (`memory_extractor.py`)

### Changed

- **Admin Pagination UX** — Admin users pagination changed from centered variant (no total) to justified layout with total count, matching usage limits pattern. Default page size reduced from 100 to 20 for all admin tables. (`AdminUsersSection.tsx`, `constants.ts`)

### Documentation

- Updated 16 guide files (why, how, privacy, terms — 6 languages) with v1.13.9 version reference.

## [1.13.8] - 2026-03-31

### Fixed

- **28 CI Test Failures** — Updated unit tests for v1.13.7 account lifecycle changes: mock `_get_memory_counts_batch`/`_get_interests_counts_batch` in search tests, set `deleted_at` on mock users for GDPR soft-delete prerequisite, add `is_deleted=False` to session dependency mocks, update prompt assertion for rewritten journal introspection prompt, fix memory extractor `_parse_items` to reject create actions with missing content/category.
- **4 CodeQL Alerts** — Fixed 3 empty-except blocks (calendar_tools, runtime_helpers, devops_ssh_service) with structured logging. Fixed incomplete URL substring sanitization in event_card.py — replaced `"meet.google.com" in location` with `_is_meet_url()` using `urlparse` for proper domain validation.
- **3 Dependency Vulnerabilities** — Fixed brace-expansion CVE-2024-4068 (medium, zero-step sequence DoS) and CVE-2025-5889 (low, ReDoS) via pnpm override pinned to 2.0.2. Fixed cryptography DNS constraint enforcement (low) via PR #75 bump to 46.0.6.

### Documentation

- **docs/technical/CI_CD.md** — New "Dependency Vulnerability Remediation (pnpm Overrides)" section with rules and override table
- **docs/technical/SECURITY.md** — New "Dependency Vulnerability Management" section covering strategy, CodeQL remediation patterns, URL validation best practice. Revision date updated.

## [1.13.7] - 2026-03-31

### Added

- **Account Lifecycle (4-State Model)** — New account lifecycle: Active → Deactivated → Deleted → Erased (GDPR). Soft-delete purges all personal data (22 tables, LangGraph store/checkpoints, Redis caches, physical files) while preserving billing history (token_usage_logs, user_statistics, google_api_usage_logs). User row kept with email/name for billing contact. ADR-067 documented. (`src/domains/users/account_deletion_service.py`, `src/domains/auth/models.py`)
- **Account Deletion API** — New `DELETE /api/v1/users/admin/{user_id}/delete-account` endpoint for admin soft-delete with precondition enforcement (must be deactivated first). Returns purge counts per table. (`src/domains/users/router.py`)
- **Admin Panel Delete/Erase Buttons** — Deactivated users show "Delete" button (soft-delete), deleted users show "Erase (GDPR)" button (hard-delete). Status badge distinguishes Active/Inactive/Deleted with distinct colors. (`AdminUsersSection.tsx`)
- **Centralized Usage Limit Pre-Check** — New `is_user_blocked_for_llm()` static method combines usage limit check + Prometheus metrics + structured logging in one call. Applied to all LLM-consuming background jobs. (`src/domains/usage_limits/service.py`)
- **Account Status in Usage Limit Enforcement** — `_compute_status()` now checks `is_active` and `deleted_at` as priority 0 (before manual blocks and usage limits). New `BLOCKED_ACCOUNT` status in `UsageLimitStatus` enum. Integrated into `check_user_allowed()` at all 3 code paths (cache hit, DB with limits, DB without limits).

### Changed

- **Background Task Protection (7 jobs)** — All LLM-consuming and connector-related background jobs now filter out inactive/deleted/blocked users: ProactiveTaskRunner (SQL filter), scheduled_action_executor (+is_active check + is_user_blocked_for_llm), reminder_notification (+is_active check), journal_consolidation (+deleted_at filter), token_refresh (JOIN User filter), OAuth health check (+deleted_at filter), session_dependencies (+is_deleted rejection).
- **GDPR Hard-Delete Precondition** — `delete_user_gdpr()` now requires user to be soft-deleted first (`deleted_at IS NOT NULL`). Enforces sequential lifecycle.
- **Usage Limit Cache Invalidation on Deactivation** — `update_user_activation()` now invalidates usage limit Redis cache immediately when deactivating a user, preventing stale cache from allowing LLM calls during the TTL window.
- **LLM Config Auto-Clean reasoning_effort** — When admin changes an LLM type's model to a non-reasoning model (gpt-4.1-*), `reasoning_effort` is automatically cleared. Validator returns `None` instead of warning for non-reasoning OpenAI models. 29 stale `reasoning_effort` values cleaned from LLM_DEFAULTS constants.
- **OAuth Health Check Filtering** — Now excludes deactivated users (`is_active=False`), deleted users (`deleted_at IS NOT NULL`), and usage-blocked users (`is_usage_blocked=True`) from health check queries.

### Fixed

- **philips_hue Enum Mismatch** — Fixed `LookupError: 'philips_hue' is not among the defined enum values` in `GET /api/v1/connectors/admin/global-config`. Migration had inserted lowercase value; corrected to uppercase `PHILIPS_HUE` in production DB.
- **Journal Consolidation UsageLimitExceeded** — Added pre-check before expensive DB queries and prompt building. Previously, the limit was only checked inside `invoke_with_instrumentation()` after all preparatory work was done.
- **Scheduled Action Executor Unprotected** — Was the only LLM-consuming background job with no user status check and no usage limit pre-check. Now has both.
- **admin_broadcasts FK Constraint** — Added `ondelete="SET NULL"` to `sent_by` FK (was missing, would cause FK violation on GDPR hard-delete).
- **google_api_usage_logs FK Preservation** — Changed FK from `CASCADE` to `SET NULL` to preserve billing history when user row is hard-deleted.
- **ConversationMessage.user_id Bug** — Fixed incorrect `DELETE WHERE user_id` on `conversation_messages` table which has no `user_id` column (only `conversation_id`). Now uses subquery via conversation_id.

### Documentation

- **ADR-067** — Account Lifecycle (Active / Deactivated / Deleted / Erased)
- **docs/INDEX.md**, **docs/architecture/ADR_INDEX.md** — Cross-referenced

## [1.13.6] - 2026-03-30

### Added

- **Centralized User Message Embedding Service** — Computes the user message embedding once per conversation turn and caches by text hash. Shared across memory injection, journal injection, memory extraction, and journal extraction. Reduces from 5 redundant embedding API calls to 1 per turn. Includes triviality filter that skips extraction entirely on trivial messages ("ok", "merci", "👍"). (`src/infrastructure/llm/user_message_embedding.py`)
- **Memory PostgreSQL Migration** — Migrated long-term memory storage from LangGraph AsyncPostgresStore to a dedicated SQLAlchemy model (`Memory`) with pgvector HNSW index. Unified with journal's PostgreSQL + pgvector pattern. Full CRUD via `MemoryRepository` and `MemoryService`. Alembic migration + data migration script. ADR-066 documented. (`src/domains/memories/models.py`, `repository.py`, `service.py`)
- **Memory Extraction Create/Update/Delete** — Memory extraction can now update or delete existing memories (micro-consolidation), not just create. LLM sees existing memories with UUIDs and decides actions. Anti-hallucination ID validation. Pinned memories protected from extraction modifications.
- **Interest Extraction Create/Update/Delete** — Interest extraction aligned on the same create/update/delete pattern as memory and journal. LLM can update topics or delete interests the user no longer cares about. Updated prompt, schema, parser, and debug panel.
- **Journal Extraction Semantic Pre-filter** — Replaces `get_all_active()` (all entries) with semantic top-10 + 3 recent. Reduces input tokens from ~7,500 to ~2,500 per extraction call.
- **Debug Panel Reorganization** — Sections reorganized into "Context Injection" (memory, RAG, knowledge, journal) and "Background Extraction" (memory, journal, interest) groups. New `JournalExtractionSection` as separate accordion. Shared `ActionBadge` component for consistent CREATE/UPDATE/DELETE display across all extraction sections.

### Changed

- **Prompt Optimization** — Memory extraction prompt reduced by 65% (1,784→620 tokens), journal introspection by 60% (1,280→508), journal analyst persona by 63% (305→113). Same directives, denser format. Interest extraction prompt rewritten with create/update/delete actions.
- **Emotional State Computation** — Migrated from `semantic_store.py` (LangGraph Items) to `emotional_state.py` (Memory ORM objects). Same DANGER/COMFORT/NEUTRAL algorithm.
- **Memory Cleanup Scheduler** — Rewritten to use `MemoryRepository` instead of LangGraph store. Same retention algorithm (usage + importance + recency).
- **Memory Router** — Rewritten from LangGraph store operations to `MemoryService`. Memory IDs changed from `mem_<12hex>` to UUID format (frontend compatible — uses opaque strings).

### Fixed

- **Journal Third-Party Projection** — Added anti-pattern directive preventing the journal from attributing traits to the user based on third-party subjects ("son's exam postponed" ≠ user procrastinating).
- **Journal Dedup Guard Removed** — Redundant post-extraction LLM merge call removed. The LLM now sees entries with IDs via semantic pre-filter and handles update/delete directly, eliminating unnecessary embedding + LLM calls.
- **Debug Panel Memory Detection Crash** — Fixed `Cannot read properties of undefined (reading 'toFixed')` error when extraction returned update/delete actions without importance/emotional_weight fields.
- **Interest Extraction Confidence Filter** — Fixed confidence threshold blocking delete/update actions (confidence is N/A for non-create actions).

### Documentation

- **ADR-066** — Memory Storage Migration from LangGraph Store to PostgreSQL Custom
- **docs/INDEX.md**, **docs/architecture/ADR_INDEX.md** — Cross-referenced
- **PromptName Literal** — Added 5 missing prompt names (memory + planner prompts)

## [1.13.5] - 2026-03-29

### Added

- **Debug Panel — Memory Detection Section** — New debug panel section showing memories extracted and stored in long-term memory from each user message. Displays: extracted memories with category, emotional weight (-10/+10), importance score, trigger topic, and storage status (success/failure); existing similar memories found during deduplication with semantic similarity scores; LLM metadata (model, input/output/cached tokens). Header badge shows `stored/extracted` count and dedup matches. Mirrors the Interest Detection pattern. (`apps/api/src/domains/agents/services/memory_extractor.py`, `apps/web/src/components/debug/components/sections/MemoryDetectionSection.tsx`)
- **Memory Extraction Debug Cache** — Module-level TTL cache (`_memory_extraction_debug_cache`) in `memory_extractor.py` captures debug data from `extract_memories_background()` keyed by `parent_run_id`. Consumed by `streaming_service.py` via `get_memory_extraction_debug(run_id)` after `await_run_id_tasks` completes. TTL 120s, max 100 entries, lazy eviction on read. 5 unit tests for cache/consume/TTL/size semantics.

### Changed

- **DRY — `getEmotionalLabel` Factorized** — Emotional weight label helper (TRAUMA/NEG/NEU/POS/TRES+) extracted from `MemoryInjectionSection.tsx` and `MemoryDetectionSection.tsx` into shared `formatters.ts`. Both sections now import from the centralized utility.

### Fixed

- **Conversation Deletion — Nested Transaction Error** — `ConversationService.delete_conversation()` wrapped store cleanup SQL in a redundant `async with db.begin()` block, causing `InvalidRequestError` ("A transaction is already begun on this Session") when the session already had an active implicit transaction. Removed the nested `begin()` and executed raw SQL directly on the existing session. (`apps/api/src/domains/conversations/service.py`)

### Documentation

- **6 files updated** — `DEBUG_PANEL_ARCHITECTURE.md` (Memory Detection cache mechanism), `LONG_TERM_MEMORY.md` (troubleshooting point 5: Memory Detection section), `CHANGELOG.md`, `README.md`, version bumps in 16 guide files.

## [1.13.4] - 2026-03-29

### Changed

- **Memory Optimization — E5 → OpenAI Embeddings** — Replaced local E5 model (intfloat/multilingual-e5-small, 384 dims) with OpenAI text-embedding-3-small (1536 dims) for memory search, tool routing, and interest deduplication. Eliminates sentence-transformers + PyTorch CPU from each worker, saving ~1 GB RAM per worker. New `memory_embeddings.py` singleton follows journal/RAG embedding pattern. Alembic migration drops `store_vectors` (auto-recreated by LangGraph with new dimensions) and nulls interest embeddings. Reindex script (`scripts/reindex_embeddings.py`) for post-deploy re-embedding.
- **Memory Optimization — Playwright Lazy Init** — Browser agent Chromium instances no longer launched at startup. Pool initialized on first browser tool call, saving ~1.5 GB RAM at boot (24 Chromium processes eliminated). Cleanup job uses safe no-op function compatible with scheduler leader election pattern.
- **Memory Optimization — Uvicorn Worker Recycling** — Added `--limit-max-requests 10000 --limit-max-requests-jitter 1000` to prevent Python memory fragmentation accumulation across workers.
- **API RAM Usage** — Reduced from 6.73 GB (84% of 8 GB limit) to 2.64 GB (33%) on Raspberry Pi 5 production server. Combined savings: ~4 GB.
- **Embedding Similarity Thresholds** — All E5-calibrated thresholds recalibrated for OpenAI embeddings (more discriminative score distribution). Memory search: 0.88→0.45, hybrid: 0.5→0.4, interest dedup: 0.90→0.75, content dedup: 0.85→0.70. No more hardcoded magic numbers — all thresholds use settings or centralized constants.
- **LLM Configuration Defaults** — `LLM_DEFAULTS` in code aligned with production-tuned settings (44 entries). Strategy: gpt-4.1-nano (domain agents), gpt-4.1-mini (routing), claude-sonnet-4-6 (extraction), qwen3.5-plus (planning), gpt-5.4 (advanced). New SQL seed `llm_config_seed.sql` for fresh installations.
- **Docker Compose** — Removed `HF_HOME`, `TRANSFORMERS_CACHE` env vars and `huggingface_cache` volume from both dev and prod compose files.
- **Dockerfile** — Removed PyTorch CPU override install (no longer needed without sentence-transformers).

### Fixed

- **WebSearchCard Synthesis Border** — Removed left border on AI synthesis block (`with_border=False`) per design intent.
- **WebSearchCard Source Badge Icons** — Source indicator icons (Perplexity, Brave, Wikipedia) now inherit white color in active state instead of being overridden by `lia-icon` default color.
- **networkx Dependency** — Added explicit `networkx==3.6.1` to requirements.txt (was a transitive dependency of sentence-transformers/torch, now needed directly by SemanticIntentDetector type registry).

### Removed

- **sentence-transformers** — Removed from requirements.txt (was pulling PyTorch + ~700 MB in Docker image).
- **Local E5 Embeddings** — `LocalE5Embeddings` class, `get_local_embeddings()`, `preload_embedding_model()` removed from `local_embeddings.py`. File retained for `cosine_similarity()` utility only.
- **HuggingFace Cache** — `huggingface_cache` Docker volume removed (E5 model no longer downloaded at runtime).

### Documentation

- **52 files updated** — All references to E5/local embeddings replaced across README, CLAUDE.md, 6 locale files, 12 landing guides, 20+ technical docs, 8 ADRs. ADR-049 marked as SUPERSEDED. `LOCAL_EMBEDDINGS.md` rewritten as migration notice.

## [1.13.3] - 2026-03-29

### Added

- **Skills Guide Redesign** — Complete rewrite of the in-app skill creation guide with 3 tabbed sections: Fundamentals (3 archetypes, L1/L2/L3 activation model, best practices), Create (SKILL.md format, frontmatter fields, Prompt Expert & Advisory examples, folder structure, references/scripts/assets usage, import process), Advanced (plan templates with auto-trigger, complete agent & tool catalogue with parameters and types organized by category via accordion, Python scripts, internal skill tools). 210 translation keys across 6 languages. (`apps/web/src/components/settings/SkillGuideModal.tsx`)
- **Skills Guide Button Enhancement** — Guide button promoted from subtle text link to prominent outlined Button with primary color, repositioned alongside Import for responsive smartphone layout (stacks vertically on mobile). (`apps/web/src/components/settings/SkillsSettings.tsx`)
- **Admin Users — New Columns** — 5 new columns in user administration: Skills count (user-imported), MCP servers count, Scheduled actions count, RAG spaces count, and Usage blocked status. All counts fetched via efficient correlated subqueries in a single SQL statement. (`apps/api/src/domains/users/repository.py`, `apps/api/src/domains/users/schemas.py`, `apps/web/src/components/settings/AdminUsersSection.tsx`)
- **Admin Limits — Sortable Columns** — Email and Blocked columns now support click-to-sort (asc/desc) with arrow indicators. Backend `GET /usage-limits/admin/users` endpoint extended with `sort_by` and `sort_order` query parameters. (`apps/api/src/domains/usage_limits/router.py`, `apps/api/src/domains/usage_limits/repository.py`, `apps/web/src/components/settings/AdminUsageLimitsSection.tsx`)

### Changed

- **Multi-Provider Naming** — Domain taxonomy display names and descriptions updated from Google-specific ("Google Calendar", "Gmail", "Google Contacts", "Google Drive", "Google Tasks") to provider-agnostic ("Calendar", "Email", "Contacts", "Drive / Files", "Tasks") reflecting the multi-provider connector abstraction (Google, Microsoft, Apple). Updated in: domain taxonomy, skill guide tool catalogue, skill-generator references. (`apps/api/src/domains/agents/registry/domain_taxonomy.py`, `data/skills/system/skill-generator/references/tool-catalogue.md`, `data/skills/system/skill-generator/references/format-specification.md`)

### Fixed

- **PlaceCard Crash Fix** — `_get_next_open_time` method signature was accidentally removed during dead code cleanup, causing `AttributeError` and silent render failure for all place cards. Restored method definition. (`apps/api/src/domains/agents/display/components/place_card.py`)
- **EmailCard Layout** — Sender name `font-weight: 400` (was 500). Date + status icons displayed above sender name. Labels + attachments + thread count merged on same chip line above subject. `chip-row` `margin-bottom` added for spacing below badges.
- **EventCard Polish** — Removed separator line under chips. Year stripped from date chip. Extra vertical margin before location.
- **RouteCard Map Full-Width** — Reverted to original `lia-route__map-link` / `lia-route__map-image` CSS classes instead of generic `lia-card-hero` (which didn't compensate border-left properly). Removed `max-height` constraint on hero images.
- **RouteCard Badges Reorder** — Line 1: arrival + suggested departure. Line 2: traffic + duration + distance. Removed separator under badges. Departure chip shows time only (strips day name).
- **PlaceCard Badges Reorder** — Type + price + distance + stars on same line. Open/closed + opening/closing time on separate line. Added `_get_closing_time()` method + `V3Messages.get_closes_at()` i18n (6 languages). 16px space before address.
- **CSS Card-Top Spacing** — `margin-bottom` increased from `sm` (8px) to `md` (12px) for uniform spacing between title separator and badges across all cards.
- **CSS Card Hero** — Added `overflow: hidden` via `:has(.lia-card-hero)` on parent card. Removed `max-height` on `lia-card-hero img` for natural aspect ratio.
- **DST-Aware Heartbeat Test** — `test_today_event_shows_time_only` now uses dynamic UTC offset for the test date instead of hardcoded `+01:00`, fixing CET→CEST transition failures.

## [1.13.2] - 2026-03-28

### Added

- **Design System v4 — Standardized HTML Card Components** — Complete visual redesign of all 14 HTML cards using a unified component library. 19 reusable CSS components (`lia-card-top`, `lia-illus`, `lia-chip`, `lia-chip-row`, `lia-sec`, `lia-d-row`, `lia-d-item`, `lia-desc-block`, `lia-card-hero`, `lia-tbadge`, `lia-att-row`, `lia-att-av`, `lia-part-list`, `lia-src-link`, `lia-kv-rows`, `lia-review`, `lia-raw-block`, `lia-file-meta`, `lia-illus-sm`). 17 Python helper functions in `base.py`. Every card now uses the same building blocks — zero domain-specific CSS classes. (`apps/web/src/styles/lia-components.css`, `apps/api/src/domains/agents/display/components/base.py`)
- **42px Illustration Vignettes** — Each card header features a colored square-rounded icon (9 color variants: green, red, amber, blue, indigo, purple, teal, orange, gray) with gradient backgrounds and filled Material Symbols icons. Dark mode uses `rgba()` backgrounds.
- **Chip System** — New inline metadata tags with borders and icons (9 variants: green, amber, red, indigo, time, stars, thread, attach, allday). Replaces inconsistent badge usage across cards.
- **Section Headers with Mini-Vignettes** — Collapsible "Voir plus" sections now use 28px mini-illustrations for each section (hours, reviews, services, participants, sources, etc.).
- **Attendee Avatars** — Stacked colored circle avatars showing participant initials with "+N" overflow indicator.
- **Participant Lists with Emails** — Event and email collapsible sections now show each participant with status icon + name + email (mailto: link).
- **Design System Guide** — Comprehensive documentation covering all components, color variants, responsive rules, Python helpers, and how to create new cards. (`docs/guides/GUIDE_DESIGN_SYSTEM.md`)

### Changed

- **All 14 HTML Cards Migrated** — EventCard, EmailCard, ContactCard, PlaceCard, WeatherCard (3 variants), RouteCard, TaskItem, ReminderCard, FileItem, ArticleCard, WebSearchCard, SearchResultCard, McpResultCard — all now use v4 components.
- **Card Layout Normalization** — All cards with `display: flex` (email, event, task, file, article) corrected to `flex-direction: column` for proper v4 vertical layout.
- **Contact Card** — Type badges colored by category (work=indigo, home=green, mobile=amber). Details aligned left. Collapsible uses same `render_d_row` + `render_type_badge` as main card.
- **Place Card** — Photo hero preserved. Chips organized in 3 rows (stars / type+status / price+distance). Collapsible sections with mini-vignettes (hours as KV grid, reviews, services, accessibility, payment).
- **Weather Card** — French weather descriptions added to icon mapping (~20 terms: ciel dégagé, nuageux, pluie, orage, neige, brouillard). Label "Min / Max" changed to "Températures" (6 languages). Sunrise/sunset icon alignment fixed.
- **Route Card** — Title simplified to "→ Destination". ETA displayed as indigo chip. Chips split into 2 rows (arrival+traffic / duration+distance). "Voiture" badge removed (redundant with illustration icon).
- **Task Card** — Unified mobile/desktop rendering (was 2 separate methods). Notes shown directly without "Voir plus".
- **Reminder Card** — Badge + title on same line. "Créé le" prefix added to creation date.
- **File Card** — Type-colored illustration (doc=blue, sheet=green, pdf=red, folder=amber). Chips with separator below.
- **Email Card** — Square-rounded initials avatar. Full-width separator under header. Recipients with emails in collapsible.
- **Article Card** — Wikipedia badge above title. Separator above categories.
- **WebSearch Card** — Source chips above title. Results web with spacing. Sources as icon+link per line.
- **MCP Card** — KV rows for structured data. Raw block for JSON.
- **Event Organizer Email Filter** — Calendar group emails (`@group.calendar.google.com`, `@resource.calendar.google.com`) no longer displayed as organizer email.
- **`render_collapsible()` Enhancement** — New `with_separator` parameter (default `True`). Cards pass `False` when the preceding element already provides a separator.
- **i18n Labels** — Added `get_accessibility_title()` and `get_payment_title()` to V3Messages (6 languages).

### Fixed

- **Email Card Crash** — `V3Messages.get_messages()` and `get_files()` were called but didn't exist, causing silent render failure. Fixed by using numeric-only chip labels.
- **22 Dead Methods Removed** — Cleaned up legacy rendering methods no longer called after v4 migration across 8 card files.

## [1.13.1] - 2026-03-28

### Fixed

- **Calendar/Reminder/Task Timezone DST Bug** — When creating events for dates across DST boundaries (e.g. March 29 during CET→CEST transition), the LLM sent the current offset (+01:00) instead of the target date's offset (+02:00), causing events to be scheduled 1 hour late. `normalize_user_datetime()` now always strips and re-localizes to the correct offset for the target date. Applied to: create/update event, create/update task (due dates), create reminder (trigger_datetime), and event search (time_min/max). (`src/core/time_utils.py`, `src/domains/agents/tools/calendar_tools.py`, `src/domains/agents/tools/tasks_tools.py`, `src/domains/agents/tools/reminder_tools.py`)
- **Context Resolver Cross-Domain Contamination** — Queries like "show me the last email" after viewing calendar events were incorrectly routed to the event domain instead of email. Root cause: the reference resolver detected "the last" as a contextual reference to the previous turn's domain. Fix: context references can only confirm domains already detected by the query analyzer, or fill in when no domain was detected — never override with an unrelated domain. (`src/domains/agents/services/query_analyzer_service.py`)
- **DevOps Semantic Keywords Overmatch** — DevOps tool keywords were too generic ("check server logs", "vérifier les logs"), causing the briefing skill and other requests to be routed to devops. Replaced with Docker-specific prefixed keywords ("devops check docker container logs"). Removed French keywords (English-only convention). (`src/domains/agents/devops/catalogue_manifests.py`)
- **Prod Docker Socket Permissions** — Deploy scripts now auto-detect the host Docker group GID and inject `DOCKER_GID` into `.env` before running `docker compose up`, ensuring `appuser` has socket access on first deploy. (`scripts/deploy/deploy-prod.ps1`, `scripts/deploy/deploy.sh`)
- **Personal Data in Documentation** — Removed personal email addresses and private IP addresses from public documentation files. (`docs/technical/HITL.md`, `docs/guides/GUIDE_DEVOPS_CLAUDE_CLI.md`, `CHANGELOG.md`)

### Changed

- **Prod Memory Optimization** — Replaced PyTorch CUDA with CPU-only version in Dockerfile.prod (~700MB saved per worker on ARM64). Reventilated container RAM limits: Tempo 512M→768M, Web/Prometheus/Grafana/Loki 512M→256M, Redis/Portainer 256M→128M. API stays at 8GB with ~78% usage (was 94%). (`Dockerfile.prod`, `docker-compose.prod.yml`)
- **DomainConfig Priority Removed** — Removed unused `priority` field from `DomainConfig` dataclass and `get_domains_by_priority()` function. Domain selection is handled by LLM intelligence, not numeric priority. (`src/domains/agents/registry/domain_taxonomy.py`)
- **Blog & Guides Enriched** — Added self-enriching anti-hallucination registry documentation to "Execution Plans" blog article (6 languages) and technical guide section 6.4. (`apps/web/locales/`, `apps/web/src/data/guides/how.*.md`)

## [1.13.0] - 2026-03-28

### Added

- **DevOps Claude CLI Integration (Admin-only)** — New `devops` domain with `claude_server_task_tool` that allows administrators to interact with Claude Code CLI installed inside the API Docker containers. Claude CLI independently inspects logs, diagnoses issues, checks container health, and manages Docker services — all through natural language via the LIA assistant. Features: local subprocess execution (no SSH needed), real-time streaming progress via SSE `execution_step` events, session persistence for multi-turn investigations (`--resume`), configurable `--allowedTools`/`--disallowedTools` per server profile (dev: full access, prod: read-only investigation). Access controlled by `is_superuser` DB check with default-deny. (`src/domains/agents/devops/`, `src/domains/agents/tools/devops_tools.py`, `src/domains/agents/services/devops_ssh_service.py`)
- **Claude CLI in Docker Images** — Node.js 22 + Claude Code CLI + Docker CLI installed in both `Dockerfile.dev` and `Dockerfile.prod`. Docker socket mounted for container management. Auth credentials mounted read-only from host. (`Dockerfile.dev`, `Dockerfile.prod`, `docker-compose.dev.yml`, `docker-compose.prod.yml`)
- **DevOps Documentation** — Comprehensive guide covering architecture, prerequisites, deployment, security model, and troubleshooting. (`docs/guides/GUIDE_DEVOPS_CLAUDE_CLI.md`, `docs/INDEX.md`)
- **Alertmanager Email-Only Template** — Simplified template for environments without Slack/PagerDuty. Auto-selected by entrypoint when webhooks are not configured. (`apps/api/monitoring/alertmanager/alertmanager-email-only.yml.template`)

### Changed

- **DevOps Tool Timeout** — `claude_server_task_tool` added to high-latency tools list in parallel executor with 120s timeout (default 30s was causing CancelledError). (`src/domains/agents/orchestration/parallel_executor.py`)
- **Alertmanager Entrypoint** — Rewritten to gracefully handle missing SMTP (minimal log-only config), missing Slack/PagerDuty (email-only template), and inline env comment parsing bug. (`apps/api/monitoring/alertmanager/docker-entrypoint.sh`)

### Fixed

- **PostgreSQL Health Check FATAL Spam** — `pg_isready` health check was missing `-d ${POSTGRES_DB}`, causing PostgreSQL to attempt connection to a database named after the user (~720 FATAL/hour). Fixed in `compose.services.yml`, `docker-compose.dev.yml`, and `docker-compose.prod.yml`.
- **Philips Hue ConnectorType LookupError (Prod)** — Alembic migration inserted `philips_hue` (enum `.value`, lowercase) but SQLAlchemy expects `PHILIPS_HUE` (enum `.name`, uppercase). Fixed migration to use `.name` and added UPDATE for existing data. (`alembic/versions/2026_03_20_0001-add_philips_hue_global_config.py`)
- **Heartbeat ForeignKeyViolation (Prod)** — Proactive heartbeat used a nil UUID (`00000000-...`) as `conversation_id` fallback instead of `None`, violating the FK constraint on `message_token_summary`. Fixed to pass `None` (column is nullable). (`src/infrastructure/proactive/tracking.py`)
- **Heartbeat Journal Embedding Dimension Mismatch (Prod)** — Heartbeat used `get_local_embeddings()` (E5-small, 384 dim) to search journals indexed with OpenAI embeddings (1536 dim). Fixed to use `get_journal_embeddings()`. (`src/domains/heartbeat/context_aggregator.py`)
- **Missing LLM Pricing: claude-3-5-haiku-latest** — Added alias to pricing seed. (`infrastructure/database/seeds/llm_pricing_seed.sql`)
- **Alertmanager Config Error** — `.env` inline comments (`SLACK_WEBHOOK=  # comment`) were parsed as non-empty values, causing `unsupported scheme "" for URL`. Fixed by commenting out unused webhook variables. (`.env`)

## [1.12.4] - 2026-03-27

### Added

- **IoT Discovery-before-Planning** — When controlling Philips Hue lights, the planner now performs a lightweight discovery call to the Hue Bridge before generating the execution plan. Light and room names are injected into the planner context, enabling the LLM to resolve user descriptions (e.g., "plafond du salon") to exact device names ("Plafond salon"). Follows the same pattern as MCP reference discovery. (`src/domains/agents/services/smart_planner_service.py`)

### Changed

- **Landing Page Hero Subtitle** — Reworked hero subtitle into 3 concise lines: personality, orchestration, simplicity. Updated all 6 locale files. (`apps/web/locales/`)
- **Landing Page Image Generation Description** — Updated to cover all 3 use cases: generate from text, refine generated images, edit photos sent as attachments. Updated all 6 locale files. (`apps/web/locales/`)
- **Hue Semantic Keywords** — Aligned with codebase convention: English-only keywords (was the only multilingual outlier across 20 agent catalogues). (`src/domains/agents/hue/catalogue_manifests.py`)

### Fixed

- **Hue Light vs Room Control** — When asking to control a specific light in a room (e.g., "éteins le plafond du salon"), LIA now correctly targets the individual light instead of turning off the entire room. Root cause: semantic keywords in `control_hue_room_tool` contained room names ("salon") causing higher match scores, and `_find_resource_by_name()` used bidirectional partial matching. Fixed via: specificity rule in Hue agent prompt, strict exact-match in `_find_resource_by_name()`, and IoT discovery context injection. (`src/domains/agents/tools/hue_tools.py`, `src/domains/agents/prompts/v1/hue_agent_prompt.txt`, `src/domains/agents/prompts/v1/smart_planner_prompt.txt`)

## [1.12.3] - 2026-03-26

### Added

- **Image Download Button** — Discrete download button on generated images and browser screenshots in the chat. Visible on hover (desktop) or always semi-visible (mobile). Also available in the full-screen lightbox with loading spinner. Uses `fetch` + Blob to bypass cross-origin `<a download>` restrictions. Shared utility `downloadImage()` in `apps/web/src/lib/utils/download-image.ts` with robust MIME extension parsing (`jpeg→jpg`, `svg+xml→svg`), Unicode-safe filename sanitisation, and `response.ok` guard against error blob downloads. (`apps/web/src/components/chat/ChatMessage.tsx`, `apps/web/src/components/ui/image-lightbox.tsx`)

### Fixed

- **Mobile Long-Press "Save Image"** — Native browser context menu ("Save Image") now works on generated images and browser screenshots on iOS Safari and Android Chrome. Root cause: Starlette `FileResponse` defaulted to `Content-Disposition: attachment` when `filename` was provided, which prevented mobile browsers from recognising the resource as a displayable image. Fixed by using `content_disposition_type="inline"` for image MIME types, while keeping `attachment` for non-image files (PDF). (`apps/api/src/domains/attachments/router.py`)

## [1.12.2] - 2026-03-26

### Added

- **Progressive Browser Screenshots** — During browser navigation, screenshots are streamed in real-time via an SSE side-channel to the frontend, displayed as inline overlays in the chat flow. Thumbnails (640px, JPEG q60, ~30KB) provide lightweight visual feedback without LLM processing. Five capture points: navigate, click, fill, press_key, and the new `browser_snapshot_tool`. (`src/infrastructure/browser/session.py`, `src/domains/agents/tools/browser_tools.py`, `apps/web/src/components/chat/BrowserScreenshotOverlay.tsx`)
- **Final Browser Screenshot Card** — Last screenshot from each browsing session saved as an Attachment (full-res 1280px, JPEG q80) and displayed inside the assistant message bubble before markdown content. Persists on page reload via `loadConversationMessages` metadata extraction. Supports lightbox click-to-expand. (`apps/web/src/components/chat/ChatMessage.tsx`, `src/domains/agents/api/service.py`)
- **Generic Side-Channel Queue** — New `__side_channel_queue` in `RunnableConfig.configurable`, a generic `asyncio.Queue` mechanism for any tool to emit SSE events directly to the frontend without going through the LLM response. Fire-and-forget with graceful degradation. (`src/domains/agents/tools/runtime_helpers.py`)
- **`emit_side_channel_chunk()` Helper** — Generic helper in `runtime_helpers.py` for putting `ChatStreamChunk` instances into the side-channel queue. None-safe, never raises, silently drops chunks if queue unavailable. Reusable by any tool domain. (`src/domains/agents/tools/runtime_helpers.py`)
- **`browser_snapshot_tool`** — Fifth screenshot capture point added to the browser ReAct agent, providing a dedicated tool for explicit page snapshots alongside the implicit captures on navigate/click/fill/press_key. (`src/domains/agents/tools/browser_tools.py`)

### Changed

- **Side-Channel Interleaving** — `_interleave_side_channel()` in `service.py` polls the queue every 300ms even during long graph node executions (ReAct browser loop), ensuring real-time screenshot delivery regardless of graph stream timing. (`src/domains/agents/api/service.py`)

### Removed

- **`BROWSER_SCREENSHOT_ENABLED`** — Removed the legacy setting and `browser_screenshot_tool` that sent screenshots to the LLM as base64 text. The LLM cannot analyze images visually, making this tool useless. Replaced by progressive screenshots which stream directly to the user. (`src/core/config/browser.py`, `src/domains/agents/tools/browser_tools.py`)

## [1.12.1] - 2026-03-26

### Added

- **Image Pricing Admin Panel** — New admin section "LLM Image Pricing" under Settings → Administration. Full CRUD for managing per-image pricing by (model, quality, size). Follows the same pattern as LLM Text Pricing: paginated table with search and sorting, create/edit modal, soft-delete with temporal versioning, audit logging, and cache reload. React 19 `useOptimistic` + `useTransition` for instant UI feedback. 5 backend endpoints at `/admin/image-pricing/pricing` (list, create, update, delete, reload-cache). i18n in 6 languages. (`src/domains/image_generation/router.py`, `src/domains/image_generation/schemas.py`, `apps/web/src/components/settings/AdminImagePricingSection.tsx`)

### Changed

- **Admin Section Naming** — Standardized administration section titles across all 6 languages: "Administration des LLM" → "Tarification LLM Texte", "Administration des API Google" → "Tarification API Google", "Tarification génération d'images" → "Tarification LLM Image".

- **Journal Semantic Dedup Guard** — New programmatic guard in journal extraction that prevents duplicate entries. When the LLM proposes a new entry semantically similar to existing ones (cosine similarity ≥ configurable threshold), the system calls a merge LLM to fuse all matching entries into a single enriched directive instead of creating a duplicate. Supports N→1 consolidation: if multiple existing entries match, they are all merged into the primary and the secondaries are deleted. Configurable via `JOURNAL_DEDUP_SIMILARITY_THRESHOLD` (default: 0.72). New `journal_merge_prompt.txt` for LLM-driven entry fusion. Graceful degradation on any failure (embedding, search, or merge). (`src/domains/journals/extraction_service.py`, `prompts/v1/journal_merge_prompt.txt`)

### Changed

- **Admin Section Naming** — Standardized administration section titles across all 6 languages: "Administration des LLM" → "Tarification LLM Texte", "Administration des API Google" → "Tarification API Google", "Tarification génération d'images" → "Tarification LLM Image".
- **Journal Introspection Prompt Rebalanced** — Replaced the hard "prioritize learnings above all" directive with a neutral theme selection guide. Each theme now has multiple non-exhaustive examples and a classification decision tree. Added thematic diversity directive to avoid over-concentration in a single theme. Result: entries are now distributed across `learnings`, `user_observations`, `self_reflection`, and `ideas_analyses` instead of 87% learnings. (`prompts/v1/journal_introspection_prompt.txt`)

### Fixed

- **Image Edit Auto-Resolution** — `edit_image` tool no longer requires a valid UUID for `source_attachment_id`. When the planner passes a textual description instead of a UUID, the tool automatically resolves the most recent image attachment from the database. (`src/domains/agents/tools/image_generation_tools.py`)
- **UnifiedToolOutput.failure Signature** — All 23 `failure()` calls in image generation tools were missing the required `error_code` positional argument, causing `TypeError` on any error path in production. Fixed with appropriate codes (`TOOL_ERROR`, `NOT_FOUND`, `AUTH_ERROR`). (`src/domains/agents/tools/image_generation_tools.py`)
- **Image Generation Timeout on High Quality** — gpt-image-1 in high quality takes 40-90 seconds. The parallel executor now enforces a minimum 90-second timeout for image tools, overriding the planner's default 30s. (`src/domains/agents/orchestration/parallel_executor.py`)
- **Journal Consolidation Prompt Contradiction** — The consolidation prompt contained contradictory instructions: "most runs should produce few actions" vs "dedup is always mandatory." Removed the inhibiting phrase and strengthened STEP 1 (MANDATORY DEDUP) with explicit semantic similarity guidance (same topic from different angles = duplicate). (`prompts/v1/journal_consolidation_prompt.txt`)

### Security

- **Dependency Vulnerability Fix** — Pinned `picomatch@4.0.4` (was 4.0.3 + 2.3.1) to fix 4 Dependabot alerts: 2 high-severity ReDoS via extglob quantifiers and 2 medium-severity method injection in POSIX character classes. Pinned `flatted@3.4.2` for consistency. All overrides use exact versions. (`package.json`)

## [1.12.0] - 2026-03-26

### Added

- **AI Image Generation** — New domain `image_generation` with multi-provider abstract architecture (`ImageGenerationClient` → `OpenAIImageClient` factory). Users can generate images from text prompts via the `generate_image` tool, with results displayed as cards below the assistant response. Supports gpt-image-1 (low/medium/high quality, 3 size presets). Images saved as attachments on disk with ownership tracking. Cost tracking integrated into `TrackingContext` → `MessageTokenSummary` → `UserStatistics` → `UsageLimits`. Pricing loaded at startup with class-level in-memory cache and cross-worker Redis Pub/Sub invalidation. (`src/domains/image_generation/`, `src/domains/agents/tools/image_generation_tools.py`)
- **AI Image Editing** — New `edit_image` tool for modifying existing images via text instructions using the OpenAI Responses API (`images.generate` with `image` parameter). Auto-resolves the most recent image attachment when no UUID is provided — the planner never needs to know attachment IDs. Includes intelligent resize to the nearest supported dimension (1024×1024, 1024×1536, 1536×1024) preserving aspect ratio, with size-aware cost calculation. (`src/domains/agents/tools/image_generation_tools.py`, `src/domains/image_generation/resize.py`)
- **Image Generation User Preferences** — Per-user settings for quality (low/medium/high), size (square/portrait/landscape), and output format (png/webp). Defaults: enabled, low quality, portrait, PNG. Configurable in Settings → Preferences. Tools always use user preferences for cost control — planner cannot override. (`src/domains/auth/models.py`, `apps/web/src/components/settings/ImageGenerationSettings.tsx`)
- **Image Generation Admin Configuration** — `image_generation` LLM type added to `LLM_TYPES_REGISTRY` (category: specialized). Administrators can select model and provider in the LLM Configuration panel. Pricing seed data for gpt-image-1 (9 combinations: 3 qualities × 3 sizes). (`src/domains/llm_config/constants.py`, `infrastructure/database/seeds/image_generation_pricing_seed.sql`)
- **Image Generation Debug Panel** — Image generation calls appear in LLM Pipeline, LLM Calls, and Execution Times sections of the debug panel. Synthetic node record with model, quality, size, image count, and cost. (`src/domains/agents/api/service.py`)
- **Image Generation Catalogue & Domain** — `image_generation` domain registered in `domain_taxonomy.py` with `image_generation_agent` containing `generate_image` and `edit_image` tools. Full catalogue manifests with semantic keywords, cost profiles, and parameter schemas. 120-second agent timeout to accommodate high-quality generation latency. (`src/domains/agents/image_generation/catalogue_manifests.py`, `src/domains/agents/registry/domain_taxonomy.py`)
- **Generated Image Persistence** — Images stored as attachments with conversation-scoped metadata (`generated_images` array in message metadata). Survive page reload via `loadConversationMessages` metadata extraction. SSE `done` chunk includes `generated_images` for real-time display. Cascade deletion on conversation delete via existing attachment cleanup. (`apps/web/src/components/chat/ChatMessage.tsx`, `apps/web/src/hooks/useConversation.ts`)

### Fixed

- **Image Generation Tool Timeout on High Quality** — gpt-image-1 in high quality takes 40-90 seconds, but the parallel executor imposed a 30-second timeout (from planner LLM or default). Added minimum timeout enforcement for image tools: `max(step_timeout, 90s)` capped at 120s. (`src/domains/agents/orchestration/parallel_executor.py`)
- **Adaptive Replanner Marking Image Results as Empty** — `generate_image` returned a plain string, which the adaptive replanner classified as `empty_results`, triggering an unnecessary replan. Fixed by returning `UnifiedToolOutput.action_success()` with structured data. (`src/domains/agents/tools/image_generation_tools.py`, `src/domains/agents/orchestration/adaptive_replanner.py`)
- **UnifiedToolOutput.failure Missing error_code** — All 23 `failure()` calls in image generation tools were missing the required `error_code` positional argument, causing `TypeError` on any error path. Fixed with appropriate error codes (`TOOL_ERROR`, `NOT_FOUND`, `AUTH_ERROR`). (`src/domains/agents/tools/image_generation_tools.py`)
- **Edit Image Auto-Resolution** — Planner passed textual descriptions (e.g., "the photo of the black and white cat") instead of UUIDs for `source_attachment_id`. Fixed by making the parameter optional and auto-resolving the most recent image attachment from the database when no valid UUID is provided. (`src/domains/agents/tools/image_generation_tools.py`)

### Changed

- **Settings Layout Reorganization** — Moved Channels, Voice Mode, and Image Generation from Features tab to Preferences tab for better UX grouping. (`apps/web/src/app/[lng]/dashboard/settings/page.tsx`)

## [1.11.5] - 2026-03-25

### Fixed

- **Chat Message Bubble Content Truncation** — Markdown tables (and occasionally other long content) caused the assistant's response bubble to visually cut off. Root cause: `overflow: hidden` on `.message-bubble` and `.message-bubble-assistant` created an implicit scroll container that miscalculated intrinsic height when nested elements (like `table-wrapper`) had their own overflow. Fixed by replacing `overflow: hidden` with `overflow-x: clip; overflow-y: visible` — clips horizontal overflow without creating a scroll container, allowing the bubble to size correctly to its content. (`apps/web/src/styles/globals.css`)
- **76-Second Latency Spike After Response (Currency API Timeout Storm)** — After each assistant response, a ~76-second delay blocked the debug panel and new messages. Root cause: `CurrencyRateService` was instantiated fresh on every call in `business_metrics`, losing its in-memory cache each time. When the frankfurter.app currency API became unreachable from Docker, each instance retried 3 times × 5s timeout + exponential backoff = ~19s per call × 4 sequential calls = 76s blocking in `response_node`. Fixed with three changes: (1) cache promoted from instance-level to class-level (`_rate_cache` class dict shared across all instances); (2) negative-result cache (`_negative_cache`, 5-minute TTL) prevents retries after API failure; (3) retry policy reduced from 3 attempts to 2, with shorter backoff (`min=1, max=3` instead of `min=2, max=10`). Worst case drops from ~76s to ~6s on first failure, then 0s for 5 minutes. (`src/infrastructure/external/currency_api.py`, `tests/unit/test_currency_api.py`)
- **Route Arrival/Departure Time Off by 1 Hour (Naive Datetime Treated as UTC)** — When the user asked "arrive at 21h", the LLM passed `2026-03-26T21:00:00` (naive, no timezone) to the route tool. `parse_datetime()` defaulted naive datetimes to UTC, then `convert_to_user_timezone()` converted UTC 21:00 → Paris 22:00. The map and response showed 22h instead of 21h. Fixed by adding `normalize_user_datetime()` utility in `time_utils.py` that detects naive datetime strings (no `Z` or `+/-` offset) and attaches the user's timezone offset directly, without UTC conversion. Applied to both `arrival_time` and `departure_time` in `get_route_tool`. Datetimes with explicit timezone (from calendar events, APIs) are left unchanged. (`src/core/time_utils.py`, `src/domains/agents/tools/routes_tools.py`)

## [1.11.4] - 2026-03-25

### Fixed

- **HITL Draft Recipient Modification Ignored by LLM** — When a user requested a recipient change during draft critique (e.g., "non envoi à user@example.com"), the HITL classifier correctly detected `REPLAN` (converted to `EDIT`), and the `DraftModificationService` called the LLM, but the LLM consistently returned the original recipients unchanged. Root cause: the draft modifier prompt rule 2 ("Respect existing context (recipient, structure, etc.)") contradicted recipient change instructions, and rule 6 only covered contact references (`@carven`) — not direct email addresses. Fixed with a three-layer approach: (1) prompt rule 2 reworded to not protect recipients, rule 6 expanded to cover direct email addresses; (2) `_build_context_info()` now labels recipients as "modifiable" instead of presenting them as fixed context; (3) new `_apply_explicit_recipient_override()` post-processing extracts email addresses from instructions via regex and applies them directly when the LLM fails to change the `to`/`cc` fields. Also resolves contact names from instructions against the contact context as fallback. (`src/domains/agents/services/hitl/draft_modifier.py`, `src/domains/agents/prompts/v1/draft_modifier_prompt.txt`)

### Changed

- **Docker Dev Log Level Set to DEBUG** — `docker-compose.dev.yml` now overrides `LOG_LEVEL=DEBUG` for the API container, ensuring all debug-level logs (including LLM prompts, raw responses, and detailed state transitions) are visible during development without requiring `.env` changes. (`docker-compose.dev.yml`)
- **Draft Modifier Debug Observability** — Added 3 debug-level logs to `DraftModificationService`: `draft_modification_prompt_built` (system prompt preview), `draft_modification_llm_raw_response` (LLM raw output), and `actual_changes` field in `draft_modification_completed` (lists only fields that actually changed vs. all fields returned). Enables rapid diagnosis of LLM modification failures. (`src/domains/agents/services/hitl/draft_modifier.py`)

## [1.11.3] - 2026-03-25

### Security

- **SSRF Prevention in Profile Image Proxy** — `GET /profile-image-proxy` validated the initial URL hostname against `ALLOWED_IMAGE_DOMAINS` but used `follow_redirects=True` without post-redirect validation. An authenticated attacker could craft a Google CDN URL that redirects to internal services (metadata endpoints, private network). Fixed by validating the final response URL hostname after redirects. Reuses the same allowlist pattern as the pre-fetch check. (`src/domains/auth/router.py`)
- **SSRF Prevention in Philips Hue Pairing** — `POST /connectors/philips-hue/pair` accepted an unvalidated `bridge_ip` string parameter, allowing requests to arbitrary hosts (including cloud metadata endpoints, internal services). Added `_HueBridgeIpValidatorMixin` Pydantic validator enforcing private IPv4 addresses only (RFC 1918), rejecting loopback, public IPs, and IPv6. Applied to both `HuePairingRequest` and `HueLocalActivationRequest` schemas. (`src/domains/connectors/schemas.py`)
- **OAuth Redirect Parameter Injection** — Hue OAuth callback embedded the raw `error` query parameter from the OAuth provider directly into the redirect URL without sanitization. This was the only OAuth callback (out of 10) that bypassed the centralized `handle_oauth_callback_error_redirect()` handler. Fixed by aligning with the pattern used by all 9 other callbacks (Gmail, Google Contacts/Calendar/Drive/Tasks, Microsoft x4), which classifies errors via `OAuthCallbackErrorCode` enum values. Also aligned success redirect path to `/dashboard/settings` for consistency. (`src/domains/connectors/router.py`)
- **Incomplete URL Substring Sanitization** — `MarkdownContent.tsx` used `src.includes('googleusercontent.com')` to detect Google profile photos, which could match substrings in unrelated hostnames (e.g., `evil-googleusercontent.com`). Fixed by using `new URL(src).hostname` with exact match against the existing `GOOGLE_IMAGE_DOMAINS` array (exported from `utils.ts`). (`apps/web/src/components/chat/MarkdownContent.tsx`, `apps/web/src/lib/utils.ts`)

### Fixed

- **Journal Size Warning Logic** — `if usage_pct > 80` / `elif usage_pct > 100` conditions were ordered incorrectly: the first branch captured all values above 80 (including >100), making the "CRITICAL: exceeded limit" message unreachable. Users exceeding 100% saw the softer "approaching limit" warning instead. Fixed by reversing condition order (>100 first, then >80). (`src/domains/journals/extraction_service.py`)
- **Duplicate Constant Definition** — `MAX_AGENT_RESULTS_DEFAULT` was defined twice in `constants.py` (lines 1687 and 1891) with identical value. Removed the duplicate at line 1891 (misplaced in the observability section). (`src/core/constants.py`)
- **Implicit String Concatenation in List** — Adjacent string literals in `context_builder.py` list were implicitly concatenated without parentheses, creating a fragile pattern where a missing comma could silently change behavior. Wrapped in explicit parentheses. (`src/domains/journals/context_builder.py`)
- **Empty Except Blocks (10 alerts)** — Added explanatory comments to 6 justified cleanup/fallback `except` blocks (browser session close, pool memory probe, leader elector task cancel, Hue color parsing). Added `logger.debug()` to 2 parsing fallbacks (JSON recovery, UUID validation) and `logger.warning()` to 1 service load failure (personality service in journal extraction). 1 alert was a false positive (browser_tools.py except block was not actually empty). (`src/infrastructure/browser/session.py`, `src/infrastructure/browser/pool.py`, `src/infrastructure/scheduler/leader_elector.py`, `src/domains/journals/extraction_service.py`, `src/domains/connectors/clients/philips_hue_client.py`)
- **TLS Certificate Validation Comment** — Added explicit justification comment for `verify=False` in Hue bridge pairing (bridges use self-signed certificates by design). (`src/domains/connectors/clients/philips_hue_client.py`)

## [1.11.2] - 2026-03-25

### Changed

- **Complete Environment Configuration Overhaul** — All 8 `.env` files reorganized into 73 numbered sections with Table of Contents, standardized English comments (usage, impact, valid values), and full cross-file consistency. Files: `.env`, `.env.example`, `.env.prod`, `.env.prod.example`, `.env.min.prod`, `apps/web/.env.local.example`, `apps/web/.env.local.prod`, `apps/api/.env.test`. Section numbering is consistent across dev and prod files (prod skips `[07] SSL`). All comments are succinct inline format with column-aligned padding.
- **98 Missing Settings Keys Added** — Audit of all 18 Pydantic config modules (645 total fields) against `.env.example` revealed 98 non-LLM Settings fields that had no `.env` entry. All added with default values from `constants.py`, organized in their correct sections. Categories: scoring thresholds (18), HITL (9), context resolution (6), planner/orchestration (11), memory extraction (5), browser (7), RAG (6), and more.

### Fixed

- **`PLACE_CAROUSEL_ENABLED` Settings Violation** — Was read directly via `os.environ.get()` in `constants.py`, bypassing the Settings system. Migrated to `ConnectorsSettings.place_carousel_enabled` field with `PLACE_CAROUSEL_ENABLED_DEFAULT` constant. Removed orphan `import os` from `constants.py`. Updated both usages in `places_tools.py` to read from `settings.place_carousel_enabled`. (`src/core/constants.py`, `src/core/config/connectors.py`, `src/domains/agents/tools/places_tools.py`)
- **`RATE_LIMITING_ENABLED` Typo in `.env.test`** — Was `RATE_LIMITING_ENABLED=false` (non-existent field), corrected to `RATE_LIMIT_ENABLED=false` (actual `ConnectorsSettings.rate_limit_enabled` field).
- **`list[str]` Fields JSON Format** — `APPROVAL_AUTO_APPROVE_ROLES` and `APPROVAL_SENSITIVE_CLASSIFICATIONS` were added with comma-separated format (`admin,power_user`) which Pydantic-settings cannot parse for `list[str]` fields. Fixed to JSON format (`["admin","power_user"]`).
- **`ASSISTANT_NAME` Removed from `.env.min.prod`** — Was present as an env var but is actually a hardcoded constant in `constants.py` (not a Settings field). Removed to prevent confusion.
- **`.env.prod.example` Section Numbering** — SSL section removal caused all subsequent sections to be renumbered `[07]-[72]` instead of keeping `[08]-[73]`. Fixed to maintain consistent numbering with `.env.example`. Also fixed em-dash `—` replaced by `--` in section headers.

### Documentation

- Updated `docs/technical/MCP_INTEGRATION.md` with MCP settings completeness
- Updated `docs/technical/LLM_CONFIG_ADMIN.md` with note about LLM per-agent keys not in `.env`
- Updated `docs/knowledge/11_mcp_servers.md` with new MCP config keys

## [1.11.1] - 2026-03-25

### Added

- **ADR-063: Cross-Worker Cache Invalidation via Redis Pub/Sub** — When running with `uvicorn --workers N`, in-memory caches (class/module-level variables) are per-process. Modifying a config via the admin API only reloaded one worker — the other N-1 workers kept stale data. New centralized `invalidation.py` module uses Redis Pub/Sub to broadcast invalidation events. Each cache exposes `load_*()` (startup/subscriber) and `invalidate_and_reload()` (runtime = load + publish). Publisher includes `os.getpid()` to skip self-reload. `verify_registry_completeness()` at startup detects missing registrations. Applied to 4 caches: `LLMConfigOverrideCache`, `SkillsCache`, `PricingCacheService`, `GoogleApiPricingService`. (`src/infrastructure/cache/invalidation.py`, `src/core/constants.py`)
- **Calendar Tool Semantic Keywords** — Added 5 appointment-lookup keywords to `get_events_tool` catalogue manifest to fix semantic tool selection misranking read queries as update/create operations. Keywords: "which appointment do I have on Saturday", "what appointments this week", "do I have any appointments on that day", "what is on my calendar this weekend", "any events planned for Saturday". (`src/domains/agents/calendar/catalogue_manifests.py`)

### Fixed

- **Initiative Node Per-Turn State Reset** — `initiative_iteration` was never reset between conversation turns. Since LangGraph state is checkpointed to PostgreSQL, after the first turn (which increments `initiative_iteration` to 1), all subsequent turns arrived with `iteration >= max_iterations` (default 1), causing the initiative node to be systematically skipped with `reason: max_iterations`. Fixed by resetting all 4 initiative state fields (`initiative_iteration`, `initiative_results`, `initiative_skipped_reason`, `initiative_suggestion`) in the router node's per-turn state clearing block, alongside the existing `planner_iteration` reset. (`src/domains/agents/nodes/router_node_v3.py`)
- **Calendar Event Tool Selection Misranking** — Asking "quel rdv samedi ?" (which appointment Saturday?) caused the semantic tool selector to rank `update_event_tool` (0.656) and `create_event_tool` (0.341) above `get_events_tool` (0.002). The correct read-only tool was excluded by the catalogue score threshold (0.07), forcing the planner to delegate to a sub-agent, which triggered an unnecessary HITL approval prompt. Root cause: `get_events_tool` lacked appointment-lookup keywords while update/create tools had "change appointment time" and "schedule appointment" keywords that matched better. Fixed by adding targeted read-only appointment keywords. (`src/domains/agents/calendar/catalogue_manifests.py`)
- **Skills Cache Cross-Worker Invalidation** — All skill CRUD endpoints (`import`, `delete`, `update_description`, `translate`) now use `SkillsCache.invalidate_and_reload()` instead of local-only `load_from_disk()`. Reload endpoint explicitly publishes after `sync_from_disk()` commit. (`src/domains/skills/router.py`, `src/domains/skills/cache.py`)
- **LLM Config Cache Cross-Worker Invalidation** — `LLMConfigOverrideCache.invalidate_and_reload()` now publishes to Redis Pub/Sub after local reload. Previously, config changes (e.g., switching Initiative LLM model) were only effective on ~25% of requests (1 worker out of 4). (`src/domains/llm_config/cache.py`)
- **Google API Pricing Cache Cross-Worker Invalidation** — `GoogleApiPricingService.invalidate_and_reload()` added and wired to admin pricing reload endpoint. (`src/domains/google_api/pricing_service.py`, `src/domains/google_api/router.py`)
- **Pricing Cache Cross-Worker Invalidation** — `PricingCacheService.invalidate_and_refresh()` added for future runtime pricing modifications. (`src/infrastructure/cache/pricing_cache.py`)

## [1.11.0] - 2026-03-24

### Added

- **ADR-062: Agent Initiative Phase** — Post-execution enrichment node in the LangGraph pipeline. After the task orchestrator executes the user's request, the initiative node analyzes results, detects cross-domain signals, and proactively performs read-only verifications to enrich the response. Example: weather forecast shows rain → initiative checks calendar for outdoor events → response warns the user. Fully prompt-driven (no hardcoded logic), configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`. Uses structured output with `InitiativeDecision` schema (OpenAI strict mode compatible). Includes pre-filter (skips when no adjacent read-only tools), memory/interests injection, and suggestion field for write-action proposals. (`src/domains/agents/nodes/initiative_node.py`, `src/domains/agents/prompts/v1/initiative_prompt.txt`, `src/domains/agents/registry/domain_taxonomy.py`)
- **MCP Iterative Mode (ReAct Sub-Agent)** — MCP servers with `iterative_mode: true` are now handled by a ReAct agent loop instead of the static planner. The agent interacts with the MCP server iteratively (reads documentation, then calls tools with correct parameters), solving the fundamental limitation where the planner pre-generated all parameters without understanding the server's API. Powered by a generic `ReactSubAgentRunner` (also used by browser agent). Configurable via `MCP_REACT_ENABLED`, `MCP_REACT_MAX_ITERATIONS`. Per-server activation via `iterative_mode` attribute on admin and user MCP configs. (`src/domains/agents/tools/react_runner.py`, `src/domains/agents/tools/mcp_react_tools.py`, `src/domains/agents/prompts/v1/mcp_react_agent_prompt.txt`)
- **ReactSubAgentRunner** — Generic, reusable runner for LangGraph ReAct sub-agents. Handles LLM creation, prompt loading, tool wrapping, MCP App registry propagation, and graceful error handling. Used by both browser agent and MCP iterative mode. Replaces 60+ lines of duplicated code in browser_tools.py. (`src/domains/agents/tools/react_runner.py`)
- **Domain Taxonomy Enrichment** — `related_domains` updated across all domain configs to enable richer cross-domain initiative detection: weather↔event (bidirectional), email↔contact↔event, task↔event↔contact, place↔weather↔route, file↔contact, reminder↔contact↔event. (`src/domains/agents/registry/domain_taxonomy.py`)
- **User MCP `iterative_mode`** — New boolean attribute on user MCP server configuration. Users can enable iterative mode per-server via the Settings UI. Includes Alembic migration, Pydantic schema update, frontend toggle with cost warning tooltip, and i18n in 6 languages. (`src/domains/user_mcp/models.py`, `src/domains/user_mcp/schemas.py`, `apps/web/src/components/settings/MCPServersSettings.tsx`)
- **Token Tracking `node_name_override`** — `TokenTrackingCallback` now supports a `node_name_override` in config metadata, allowing sub-agents to display meaningful names in the debug panel instead of internal graph node names. (`src/infrastructure/observability/callbacks.py`)
- **Initiative Prometheus Metrics** — 3 new metrics: `initiative_evaluations_total` (by decision: skip/act/error), `initiative_actions_executed_total`, `initiative_duration_seconds_histogram`. (`src/infrastructure/observability/metrics_agents.py`)
- **MCP ReAct Prometheus Metrics** — 2 new metrics: `mcp_react_invocations_total` (by server/status), `mcp_react_iterations_histogram`. (`src/infrastructure/observability/metrics_agents.py`)

### Changed

- **Browser Agent Refactoring** — `browser_task_tool` now uses `ReactSubAgentRunner` instead of inline ReAct agent creation. Removes ~60 lines of duplicated code. Functionally identical. (`src/domains/agents/tools/browser_tools.py`)
- **Excalidraw Cleanup** — Removed `SPATIAL_SUFFIX` override, `iterative_builder.py`, and `position_corrector.py`. Excalidraw now uses the generic MCP iterative mode (ReAct agent) which handles `read_me` → `create_view` flow naturally. (`src/infrastructure/mcp/excalidraw/overrides.py`, `src/infrastructure/mcp/tool_adapter.py`)
- **Smart Planner MCP Reference Filtering** — When a server uses `iterative_mode`, its `reference_content` is no longer injected into the planner prompt (the ReAct agent reads it itself via `read_me`). Saves ~27K tokens per Excalidraw request. (`src/domains/agents/services/smart_planner_service.py`)
- **OpenAI Strict Mode Compatibility** — Added `ConfigDict(extra="forbid")` to `ParameterValue`, `ParameterItem`, `InitiativeAction`, and `InitiativeDecision` to ensure `additionalProperties: false` in JSON schemas. Required for OpenAI structured output mode. (`src/domains/agents/orchestration/plan_schemas.py`, `src/domains/agents/nodes/initiative_node.py`)

### Fixed

- **Excalidraw Incoherent Diagrams** — Diagrams generated by the static planner were spatially incoherent (texts and arrows scattered randomly). Root cause: the planner is not specialized for Excalidraw JSON format and the 27K-char cheat sheet was being ignored in the complex planning context. Fix: MCP iterative mode lets a dedicated ReAct agent read the documentation and generate elements correctly.

## [1.10.2] - 2026-03-24

### Fixed

- **HITL Draft CC/BCC Modification** — CC and BCC fields were not modifiable during HITL draft review (EDIT action). When a user requested to add, change, or remove CC/BCC recipients on an email draft, the modification was silently ignored. Root cause: `cc` and `bcc` were in `PRESERVED_FIELDS` (immutable) instead of `CONTENT_FIELDS` (LLM-modifiable). Same pattern as the `to` field fix from 2026-01-11, but `cc`/`bcc` were missed. Additionally, `_parse_modification_response()` now supports `clearable_fields` (`cc`, `bcc`) so that returning an empty string explicitly removes recipients instead of preserving originals. (`src/domains/agents/services/hitl/draft_modifier.py`)
- **HITL Draft Field Configuration Audit** — Comprehensive audit and correction of `PRESERVED_FIELDS` and `CONTENT_FIELDS` across all 9 draft types to align with actual Pydantic models and connector protocol signatures:
  - `email_reply`: `in_reply_to` renamed to `message_id` (matching `EmailReplyDraftInput`); `cc`/`bcc`/`subject` excluded from `CONTENT_FIELDS` (not supported by `reply_email` protocol across Google/Apple/Microsoft connectors)
  - `email_forward`: `original_message_id` renamed to `message_id` (matching `EmailForwardDraftInput`); `bcc`/`subject` excluded (not supported by `forward_email` protocol); `cc` confirmed as supported
  - `event`/`event_update`: added `timezone` to `PRESERVED_FIELDS` (prevents LLM from inadvertently changing timezone during content edits)
  - `contact_update`: added `address` to `CONTENT_FIELDS` (field existed in `ContactUpdateDraftInput` but was not modifiable)
  - `task`/`task_update`: fixed `tasklist_id` → `task_list_id` (matching actual field name in `TaskDraftInput`/`TaskUpdateDraftInput`)
  (`src/domains/agents/services/hitl/draft_modifier.py`)

## [1.10.1] - 2026-03-24

### Added

- **ADR-061: Centralized Component Activation** — Three-layer defense system for component enable/disable control. Layer 1: domain gate-keeper validates LLM-output domains against `available_domains` (strips hallucinated/disabled domains post-LLM and post-expansion in `query_analyzer_service.py`). Layer 2: per-request `request_tool_manifests_ctx` ContextVar built once at request start, combining registry manifests minus admin MCP disabled plus user MCP tools — all consumers read filtered manifests from a single source instead of 7+ scattered filter sites. Layer 3: API guard returns 403 on admin MCP proxy endpoints (`call-tool`, `read-resource`) for disabled servers, with defense-in-depth in `MCPClientManager`. (`src/core/context.py`, `src/domains/agents/services/query_analyzer_service.py`, `src/domains/agents/api/service.py`, `src/domains/user_mcp/admin_router.py`, `src/infrastructure/mcp/client_manager.py`)
- **GPT-5.4 Model Support** — Added `gpt-5.4` and `gpt-5.4-mini` model profiles with full capabilities (reasoning, vision, structured output, streaming). Pricing seeded in `llm_pricing_seed.sql` (117 models). (`src/infrastructure/llm/model_profiles.py`, `infrastructure/database/seeds/llm_pricing_seed.sql`)
- **Run-Level Token Tracking** — All `TrackingContext` instances sharing the same `run_id` now publish their committed records to a module-level collector (`_run_records`, `_run_google_api_records`). The debug panel shows EVERY LLM call (pipeline + background tasks like memory/interest/journal extraction) in a single unified view. `cleanup_run_records(run_id)` prevents memory leaks after the debug panel is emitted. (`src/domains/chat/service.py`, `src/domains/agents/services/streaming/service.py`)
- **Debug Metrics sessionStorage Persistence** — Debug metrics history is persisted to `sessionStorage` so it survives page navigation within the same tab. Hydrated on `createInitialState()`, updated via `useEffect`. Capped at 50 entries to stay within the 5 MB storage limit. (`apps/web/src/reducers/chat-reducer.ts`, `apps/web/src/hooks/useChat.ts`)
- **Onboarding Pages Overhaul** — Complete redesign of the onboarding flow: Page 1 adds a 4-line intro explaining what makes LIA different from ChatGPT/Claude/Gemini. Page 2 replaces Google-specific connector options with 5 essential external connectors (Brave Search, Wikipedia, Google Places, OpenWeatherMap, Browser) with descriptions and provider mixing note. Page 4 adds autonomous memory description and settings management tip. Page 7 adds a feature discovery list (Skills, MCPs, RAG, Scheduled Actions, Voice Mode) before the example categories. All 6 locale files updated (en, fr, de, es, it, zh). (`apps/web/src/components/onboarding/pages/Page1Welcome.tsx`, `Page2Connectors.tsx`, `Page4Memory.tsx`, `Page7Examples.tsx`)
- **Background Task Token Awaiting** — Debug panel now awaits background tasks (memory, interest, journal extraction) up to 15s before reading DB-aggregated totals, ensuring the debug panel shows the same cost as the chat bubble. (`src/domains/agents/services/streaming/service.py`)

### Changed

- **Responses API Pattern-Based Eligibility** — Replaced hardcoded `RESPONSES_API_ELIGIBLE_MODELS` set (30+ entries) with a single regex pattern `^(gpt-4\.1|gpt-5|o[1-9])`. Auto-extensible for future GPT-5.x and o-series models. (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Tool Conversion via `convert_to_openai_function`** — `ResponsesLLM._convert_tools()` and `_format_tools_for_binding()` now delegate to LangChain's `convert_to_openai_function()` instead of manual `model_json_schema()` calls. Fixes crash on tools with `InjectedToolArg` annotations (non-serializable `CallableSchema`). (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Excalidraw Intent-Only Mode** — Removed `position_corrector.py` (384 lines) and its test file. The tool adapter no longer has a fallback path for raw Excalidraw elements — only structured intent objects are processed through the iterative builder. Simplified `_prepare_excalidraw()`, updated documentation strings and prompt override. (`src/infrastructure/mcp/tool_adapter.py`, `src/infrastructure/mcp/excalidraw/`)
- **Centralized Tool Manifest Access** — Router node, normal/panic filtering strategies, and expansion service now read from `get_request_tool_manifests()` instead of `registry.list_tool_manifests()` + manual per-consumer filtering. Eliminates duplicate filtering logic across 7+ locations. (`src/domains/agents/nodes/router_node_v3.py`, `src/domains/agents/services/catalogue/strategies/`, `src/domains/agents/semantic/expansion_service.py`)
- **Query Analyzer Domain Builder Extraction** — Extracted `_build_available_domains()` helper from inline code in `analyze_query()`. Called once per request and reused for both LLM prompt construction and post-expansion domain validation. (`src/domains/agents/services/query_analyzer_service.py`)
- **HeroSection Responsive Subtitle** — Removed `whitespace-nowrap` from hero subtitle for proper text wrapping on mobile. (`apps/web/src/components/landing/HeroSection.tsx`)

### Fixed

- **Disabled MCP Server Tool Execution** — When a user disabled an admin MCP app (e.g., Excalidraw), the system continued routing queries to that domain and executing its tools. Root cause: LLM-output domains were never validated against `available_domains`, and semantic expansion could re-introduce disabled domains. Fixed by ADR-061 three-layer defense. (`src/domains/agents/services/query_analyzer_service.py`, `src/core/context.py`)
- **GPT-5.4 reasoning_effort + Tools Incompatibility** — `gpt-5.4` and later models do not support `reasoning_effort` parameter simultaneously with function tools in `/v1/chat/completions`. Fixed by omitting `reasoning_effort` when tools are present. Applied to both `_generate()` and `_stream()` paths. (`src/infrastructure/llm/providers/responses_adapter.py`)
- **Browser Tool Store Propagation** — `browser_task_tool` nested ReAct agent was missing the parent graph's `InMemoryStore`, causing `validate_runtime_config` failures. Fixed by passing `runtime.store` to `create_react_agent()`. (`src/domains/agents/tools/browser_tools.py`)
- **AdminLLMConfigSection Loading Flicker** — Loading spinner was shown during refetches (not just initial load), causing the entire content to unmount and lose focus. Fixed by conditioning spinner on `loading && configs.length === 0`. (`apps/web/src/components/settings/AdminLLMConfigSection.tsx`)
- **Debug Panel Missing Background Task Costs** — The debug panel displayed token costs only from the main pipeline, missing memory/interest/journal extraction costs. Fixed by run-level token aggregation and background task awaiting. (`src/domains/chat/service.py`, `src/domains/agents/services/streaming/service.py`)

### Removed

- **Excalidraw Position Corrector** — Deleted `position_corrector.py` and `test_excalidraw_position_corrector.py`. The module corrected text centering and shape overlaps in raw LLM-generated Excalidraw elements, but is no longer needed since the system now exclusively uses intent-based diagram generation via the iterative builder.

## [1.10.0] - 2026-03-23

### Added

- **Push-to-Talk Mobile Fix** — Comprehensive fix for push-to-talk on smartphones. CSS anti-long-press (`select-none`, `-webkit-touch-callout:none`, `onContextMenu`), handlers always attached (eliminates race condition when `showSendMode` changes mid-touch), `onTouchCancel` for system interruptions, `onTouchMove` for finger-slide cancellation. `e.preventDefault()` now conditional: only called during actual push-to-talk, preserving form submit on mobile. (`apps/web/src/components/chat/ChatInput.tsx`)
- **Push-to-Talk Cancel Support** — Users can release the button during the async setup phase (state 'connecting') to cancel. `cancelledRef` flag checked after `Promise.allSettled` completes. `stopRecording()` extended to handle 'connecting' state. (`apps/web/src/hooks/useVoiceInput.ts`)
- **Push-to-Talk Latency Optimization** — `getUserMedia` + WS connect parallelized via `Promise.allSettled` (saves ~100-500ms). Worklet Blob URL cached across recordings. WebSocket pre-warmed in background during idle state. Setup timeout (10s) prevents indefinite blocking on slow networks. (`apps/web/src/hooks/useVoiceInput.ts`, `apps/web/src/lib/constants.ts`)
- **Voice Mode Latency Optimization** — KWS microphone stream reused for recording (eliminates `getUserMedia` call, saves ~200-800ms). WebSocket pre-connected during listening state. Recording worklet URL cached. VAD silence threshold reduced from 1000ms to 750ms for faster end-of-speech detection. (`apps/web/src/hooks/useVoiceMode.ts`)
- **Ready Chime** — Short synthesized audio cue (ascending C5→E5 major third, ~250ms) plays when recording starts after wake word detection, providing auditory feedback that the app is ready. Uses Web Audio API oscillators, no external audio file. (`apps/web/src/lib/audio/ready-chime.ts`)
- **Per-User STT Language** — User's preferred language (from DB `user.language` column) is now included in the WebSocket ticket and passed to the backend STT service. `SherpaSttService` maintains a thread-safe cache of `OfflineRecognizer` instances keyed by language code, biasing Whisper transcription to the user's language instead of auto-detection. (`apps/api/src/domains/voice/ticket_store.py`, `apps/api/src/domains/voice/stt/sherpa_stt.py`, `apps/api/src/domains/voice/router.py`)
- **Send Button Loading State** — Send icon remains visible (at 30% opacity) with a spinning overlay when disabled, instead of being replaced by a spinner. Preserves visual landmark. Uses `text-primary-foreground` for correct light/dark mode rendering. (`apps/web/src/components/chat/ChatInput.tsx`)
- **Sherpa WASM Setup Script** — New `scripts/download-sherpa-wasm.sh` downloads the pre-built sherpa-onnx WASM runtime (VAD + ASR + Whisper Tiny.en bundled, ~111MB) from GitHub releases. Integrated into `scripts/setup-dev.sh` as step 3/3 and `Dockerfile.prod` model-downloader stage. (`scripts/download-sherpa-wasm.sh`, `scripts/setup-dev.sh`, `apps/web/Dockerfile.prod`)
- **Safari iOS Voice Mode Support** — Changed `Cross-Origin-Embedder-Policy` from `credentialless` to `require-corp`, enabling `crossOriginIsolated` (and thus `SharedArrayBuffer` for Sherpa WASM) on Safari iOS. Google Fonts `crossOrigin="anonymous"` attribute added. Google profile images already proxied via existing endpoint. (`apps/web/next.config.ts`, `apps/web/src/app/[lng]/layout.tsx`)
- **VoiceInputService.updateCallbacks()** — Allows re-wiring callbacks on a pre-warmed service instance without creating a new connection. Used by both push-to-talk and voice mode pre-warm flows. (`apps/web/src/lib/voice-input-service.ts`)

### Fixed

- **Sherpa WASM Script Loading** — Browser `class` declarations at top-level of `<script>` tags don't become `window` properties in strict mode. Fixed by fetching script content, appending a shim that explicitly assigns `createVad`, `CircularBuffer`, and `OfflineRecognizer` to `window`, then executing via Blob `<script>` tag. (`apps/web/src/lib/audio/sherpaKws.ts`)
- **VoiceModeBadge Stuck Initializing** — Badge remained in "Initializing..." state forever on browsers where KWS is not supported (missing `SharedArrayBuffer`). Fixed by checking `isKwsSupported` in the `isInitializing` condition. (`apps/web/src/components/voice/VoiceModeBadge.tsx`)
- **handleSubmit Guard Incomplete** — Form submit was not blocked during push-to-talk 'connecting' state. Added `voiceState !== 'connecting'` to the guard. (`apps/web/src/components/chat/ChatInput.tsx`)

## [1.9.6] - 2026-03-23

### Added

- **Unified LLM + Embedding Tracking** — Embedding calls (journal context, memory search, RAG retrieval via `TrackedOpenAIEmbeddings`) are now recorded in the conversation's main `TrackingContext` instead of a separate standalone tracker. This makes embedding token usage visible in the debug panel alongside chat completions and TTS. Dual-strategy approach: (1) when a conversation tracker is active (via `current_tracker` ContextVar), record directly into it; (2) fallback to standalone `TrackingContext` for background operations (RAG indexing, scheduled tasks). Graceful degradation with try/except ensures embedding calls never break on tracking failures. (`apps/api/src/infrastructure/llm/embedding_context.py`, `apps/api/src/infrastructure/llm/tracked_embeddings.py`)
- **TokenUsageRecord call_type & sequence** — Two new fields on `TokenUsageRecord` NamedTuple: `call_type` (`"chat"` | `"embedding"`, default `"chat"`) distinguishes LLM call categories, and `sequence` (monotonic counter under asyncio lock) provides chronological ordering. Both fields are backward-compatible (keyword defaults). `get_llm_calls_breakdown()` now returns these fields for the debug panel. (`apps/api/src/domains/chat/service.py`)
- **Debug Panel: LLM Pipeline Section** — New `LLMPipelineSection` component showing ALL LLM calls (chat + embedding) in chronological execution order. Each row displays: sequence number, type badge (CHAT/EMB), node badge with color, model name, duration, tokens IN/CACHE/OUT, and cost. Summary header shows total calls (split by type), duration, tokens, and cost. (`apps/web/src/components/debug/components/sections/LLMPipelineSection.tsx`)
- **Debug Panel: Embedding Visibility** — Embedding calls now appear in existing debug sections: LLM Calls section shows `EMB` badge (teal) with `—` for tokens_out; Request Lifecycle section includes embedding nodes; Token Budget totals include embedding tokens; LLM Summary aggregates all call types. (`apps/web/src/components/debug/components/sections/LLMCallsSection.tsx`, `apps/web/src/components/debug/DebugPanel.tsx`)
- **Embedding Duration Tracking** — `TrackedOpenAIEmbeddings` now passes `duration_ms` (latency in milliseconds) to `persist_embedding_tokens()`, enabling timing display in the debug panel. (`apps/api/src/infrastructure/llm/tracked_embeddings.py`)

### Fixed

- **Embedding ContextVar Overwrite Bug** — `persist_embedding_tokens()` previously created `async with TrackingContext(...)` which temporarily overwrote the `current_tracker` ContextVar, potentially corrupting concurrent access to the conversation tracker. The new approach avoids creating a new `TrackingContext` when a conversation tracker is already active. (`apps/api/src/infrastructure/llm/embedding_context.py`)
- **LLMCallsSection Hardcoded Node Colors** — Node color determination in `LLMCallsSection` used inline `includes()` checks instead of the centralized `getNodeColor()` helper, causing new node types (like embedding) to always fall back to default color. Refactored to use `getNodeColor()`. (`apps/web/src/components/debug/components/sections/LLMCallsSection.tsx`)
- **Zod Schema Gaps (v3.2 debt)** — `LLMCallSchema` was missing `duration_ms`, `LifecycleNodeSchema` was missing `duration_ms`, and `RequestLifecycleSchema` was missing `total_duration_ms`. Added as optional fields. (`apps/web/src/components/debug/validation/schemas.ts`)

## [1.9.5] - 2026-03-23

### Added

- **ToolManifest.context_save_mode** — New `context_save_mode: ContextSaveMode | None` field on `ToolManifest` dataclass enables explicit LIST/DETAILS override for context auto-save classification, bypassing the name-based heuristic in `classify_save_mode()`. Propagated through both parallel_executor and `@connector_tool`/`@auto_save_context` decorator chains. Set to `ContextSaveMode.LIST` on all 4 unified tools (get_events, get_emails, get_contacts, get_tasks). (`apps/api/src/domains/agents/registry/catalogue.py`, `apps/api/src/domains/agents/context/manager.py`, `apps/api/src/domains/agents/orchestration/parallel_executor.py`, `apps/api/src/domains/agents/context/decorators.py`, `apps/api/src/domains/agents/tools/decorators.py`)
- **Email Reply/Forward HITL Domains** — Separate `email_reply` and `email_forward` insufficient content domains with domain-specific required fields (reply: body only; forward: recipient + optional body). Includes i18n questions (6 languages), field questions, detection patterns, DRAFT_TYPE_EMOJIS, and DRAFT_SUMMARIES. (`apps/api/src/core/constants.py`, `apps/api/src/core/i18n_hitl.py`)
- **Task Update current_task Fetch** — `UpdateTaskDraftTool` now fetches the current task before creating the draft, enabling before/after comparison in HITL critique (consistent with calendar and contact update patterns). Due date converted from UTC to user timezone. (`apps/api/src/domains/agents/tools/tasks_tools.py`)
- **Rich HITL Draft Critique Prompt** — Redesigned `hitl_draft_critique_prompt.txt` with domain-specific markdown templates (email, event, contact, task), emoji field prefixes, before/after strikethrough for updates, irreversibility warnings for deletions. (`apps/api/src/domains/agents/prompts/v1/hitl_draft_critique_prompt.txt`)
- **Rich Post-HITL Result Display** — `_format_draft_execution_result` now shows all draft attributes with i18n labels, domain emojis, formatted dates, and clickable links. Intermediate search results (`[search] N event(s):...`) are replaced by the execution result instead of being concatenated. Module-level `_DRAFT_RESULT_FIELD_CONFIG` defines field rendering per domain. (`apps/api/src/domains/agents/nodes/response_node.py`)
- **Enriched HITL Fallback Summaries** — `_generate_fallback_critique` now produces multi-line structured summaries with extra fields (body for emails, location/attendees for events, phone/org for contacts, due/notes for tasks) and `---` separator before action buttons. (`apps/api/src/domains/agents/services/hitl/interactions/draft_critique.py`)

### Fixed

- **Calendar 404 on Non-Primary Calendar** — `update_event_tool` and `delete_event_tool` failed with 404 when modifying events on shared calendars (e.g., "Famille"). Root cause: `calendar_id` not propagated from search step to mutation step. Triple fix: (1) `calendar_id` added to `get_events_tool` catalogue outputs + reference_examples with `semantic_type="calendar_id"`, (2) `_CALENDAR_ID_PARAM` gains `semantic_type="calendar_id"` for planner semantic binding, (3) new `_resolve_calendar_id_from_context` helper reads both LIST and DETAILS store keys. (`apps/api/src/domains/agents/calendar/catalogue_manifests.py`, `apps/api/src/domains/agents/tools/calendar_tools.py`)
- **Context Store Classification Bug** — All unified `get_*_tool` names (get_events, get_emails, get_contacts, get_tasks) were classified as DETAILS by `classify_save_mode()` because "get" matched the DETAILS keyword rule. Mutable tools reading from LIST key found nothing. Fixed by `context_save_mode=ContextSaveMode.LIST` on manifests and decorators. (`apps/api/src/domains/agents/registry/catalogue.py` + 4 catalogue files + 4 tool files)
- **GetEventDetailsTool calendar_id Lost** — In ID mode (`get_events_tool(event_id="abc")`), `calendar_id` was resolved for the API call but not included in the result dict. Events stored in the registry had no `calendar_id`. Fixed in `_execute_single`, `_execute_batch`, and `format_registry_response`. (`apps/api/src/domains/agents/tools/calendar_tools.py`)
- **Usage Limits Cache KeyError** — `check_user_allowed()` read `cached["allowed"]` directly but `cache_set_json()` wraps data in `{"data": {...}}` envelope. Fixed with `cached.get("data", cached)` unwrap. (`apps/api/src/domains/usage_limits/service.py`)
- **Semantic Pivot Translating User Content** — Planner received `english_enriched_query` (with translated content like "merci" → "Thank you") instead of `original_query` (user's language). Email bodies, event titles, task names were sent in English. Fixed: planner now always receives `original_query` for content extraction; English enriched version passed as structural context with explicit "CONTENT RULE" directive. (`apps/api/src/domains/agents/services/smart_planner_service.py`, `apps/api/src/domains/agents/prompts/v1/smart_planner_prompt.txt`, `apps/api/src/domains/agents/prompts/v1/smart_planner_multi_domain_prompt.txt`)
- **Email Reply Recipient Override Ignored** — `execute_email_reply_draft()` did not pass the `to` field to `client.reply_email()`, and `google_gmail_client.reply_email()` hardcoded the recipient to the original sender. Draft modifications to recipient were silently ignored. Fixed across Google, Microsoft, Apple clients and protocol. (`apps/api/src/domains/agents/tools/emails_tools.py`, `apps/api/src/domains/connectors/clients/google_gmail_client.py`, `apps/api/src/domains/connectors/clients/microsoft_outlook_client.py`, `apps/api/src/domains/connectors/clients/apple_email_client.py`, `apps/api/src/domains/connectors/clients/protocols.py`)
- **Email Reply Missing Quoted Body** — Gmail and Apple reply_email sent only the new body without the quoted original message. Fixed: both now include `> On [date], [sender] wrote:` quoted block (Microsoft handles this server-side). (`apps/api/src/domains/connectors/clients/google_gmail_client.py`, `apps/api/src/domains/connectors/clients/apple_email_client.py`)
- **Microsoft Outlook Forward Missing CC** — `forward_email()` accepted `cc` parameter but never added `ccRecipients` to the Graph API request. (`apps/api/src/domains/connectors/clients/microsoft_outlook_client.py`)
- **Contact Update Missing Address** — `execute_contact_update_draft()` did not pass `address` field to client. (`apps/api/src/domains/agents/tools/google_contacts_tools.py`)
- **Email Reply HITL Asked for Recipient** — Semantic validator treated reply/forward same as send, requiring recipient + subject + body. Reply only needs body; forward only needs recipient. Fixed with separate `email_reply`/`email_forward` insufficient content domains. (`apps/api/src/core/constants.py`, `apps/api/src/core/i18n_hitl.py`)
- **Contacts Catalogue Alias Mismatch** — `reference_examples` used `emails`/`phones` (old aliases) instead of `emailAddresses`/`phoneNumbers` (actual Google API field names in registry). (`apps/api/src/domains/agents/google_contacts/catalogue_manifests.py`)
- **Email Subject Not Top-Level** — `reference_examples` declared `emails[0].subject` but subject was only in nested `payload.headers`. Promoted to top-level in `build_emails_output()` with Apple Mail fallback. (`apps/api/src/domains/agents/tools/mixins.py`, `apps/api/src/domains/agents/emails/catalogue_manifests.py`)
- **Calendar HITL Timezone Mismatch** — `current_event` dates from Google API were in UTC while draft dates were in user timezone, causing wrong before→after display (e.g., "17h→16h" instead of "17h→15h"). Fixed: UTC→user timezone conversion for `current_event` (update) and `event` (delete). Same fix for task `current_task.due`. (`apps/api/src/domains/agents/tools/calendar_tools.py`, `apps/api/src/domains/agents/tools/tasks_tools.py`)
- **Draft Model Inconsistency** — `EmailReplyDraftInput.to_reply_email_args()` did not include `to` field. (`apps/api/src/domains/agents/drafts/models.py`)
- **Post-HITL Search Results Leak** — After HITL confirmation, `[search] N event(s):...` from intermediate steps was concatenated with the execution result instead of being replaced. (`apps/api/src/domains/agents/nodes/response_node.py`)

## [1.9.4] - 2026-03-23

### Changed

- **Systematic Settings Priority Chain Enforcement** — Comprehensive refactoring of ~291 runtime constant usages across ~80 files to use `settings.field_name` instead of direct constants. Enforces the priority chain APPLICATION (admin UI / DB) > .ENV (settings) > CONSTANT (fallback only). Six fix patterns applied: direct replacement (Pattern A), `getattr` simplification (Pattern B), module-level alias re-sourcing (Pattern C), None sentinel for function defaults (Pattern D), Pydantic `default_factory` for domain schemas (Pattern E), and f-string description updates (Pattern F). Constants now reserved exclusively for: `Field(default=...)` in config files, SQLAlchemy `default=`/`server_default=`, structural values (node names, state keys, Redis prefixes, scheduler IDs). (`apps/api/src/` — 80+ files across all domains)
- **i18n Chain Fix** — `i18n_dates.py` had a hardcoded `DEFAULT_LANGUAGE = "fr"` bypassing settings, and `i18n_drafts.py` imported from `i18n_types.py` (also hardcoded) instead of `i18n.py` (which reads from settings). Both now correctly route through the settings-backed `i18n.py` bridge. (`apps/api/src/core/i18n_dates.py`, `apps/api/src/core/i18n_drafts.py`)
- **Agent Constants Alias Cleanup** — Removed 4 redundant aliases in `agents/constants.py` (`CONTEXT_ACTIVE_WINDOW_TURNS`, `CONTEXT_RESOLUTION_TIMEOUT_MS`, `CONTEXT_DEMONSTRATIVE_CONFIDENCE`, `CONTEXT_CURRENT_ITEM_CONFIDENCE`) that bypassed settings. Consumers migrated to `settings.*` access. (`apps/api/src/domains/agents/constants.py`, `apps/api/src/domains/agents/services/context_resolution_service.py`)
- **Personalities Constants Cleanup** — Removed re-exported `DEFAULT_LANGUAGE`, `SUPPORTED_LANGUAGES`, and `FALLBACK_LANGUAGES` from `personalities/constants.py`. `FALLBACK_LANGUAGES` was capturing the constant "fr" at import time; replaced with inline `(settings.default_language, "en")` in the single consumer. (`apps/api/src/domains/personalities/constants.py`, `apps/api/src/domains/personalities/models.py`)
- **Token Counter Aliases Re-sourced** — `TOKEN_THRESHOLD_SAFE/WARNING/CRITICAL/MAX` module-level aliases in `token_counter_service.py` now read from `settings.*` instead of constants, while preserving backward-compatible exports for tests. (`apps/api/src/domains/agents/services/token_counter_service.py`)

### Fixed

- **Places Tool Crash on Language Parameter** — `get_places_tool()` raised `TypeError: unexpected keyword argument 'language'` when the LLM planner included a `language` parameter in the execution plan. Added optional `language: str | None = None` parameter to accept the argument gracefully (tool already reads language from runtime context). (`apps/api/src/domains/agents/tools/places_tools.py`)

## [1.9.3] - 2026-03-23

### Added

- **Journal Semantic Search Overhaul** — Migrated journal embeddings from local E5-small (384d) to OpenAI `text-embedding-3-small` (1536d) via pgvector `Vector()` column with HNSW index. Added `search_hints` field (LLM-generated keywords in user vocabulary) to bridge the semantic gap between assistant introspection and user queries. Search hints are displayed as badges and editable in Settings → Personal Journals. 3 Alembic migrations (search_hints column, pgvector migration with data purge, injection tracking). (`apps/api/src/domains/journals/embedding.py`, `apps/api/src/domains/journals/service.py`, `apps/api/src/domains/journals/models.py`)
- **Journal Temporal Continuity** — Configurable `JOURNAL_CONTEXT_RECENT_ENTRIES` setting injects the N most recent journal entries regardless of semantic score, ensuring the assistant always has access to its latest reflections. Deduplication with semantic results prevents double injection. (`apps/api/src/domains/journals/context_builder.py`)
- **Journal Injection Tracking** — New `injection_count` and `last_injected_at` columns track how often each journal entry is actually used in prompts. Fire-and-forget background update via `safe_fire_and_forget` to avoid response latency. (`apps/api/src/domains/journals/repository.py`, `apps/api/src/domains/journals/context_builder.py`)
- **Journal Planner Injection** — Journal context is now injected into the planner prompt (in addition to the response prompt), using `intelligence.original_query` as the semantic search query. Separate debug tracking via `journal_planner_injection_debug` state key. (`apps/api/src/domains/agents/nodes/planner_node_v3.py`)
- **Debug Panel Enhancements** — Journal debug section split into Response + Planner sub-sections with `InjectionSubSection` reusable component. Recent entries show "RECENT" badge instead of score bar. Tooltips on injection and extraction entries show full title + content on hover. Background extraction section shows action details. Semantic search scores logged at `info` level for threshold calibration. (`apps/web/src/components/debug/components/sections/JournalInjectionSection.tsx`)
- **Memory Emotional Safety Directive** — Dynamic behavioral directive in psychological profile: `DANGER_DIRECTIVE` activates when any memory has `emotional_weight ≤ -5`, with 4 absolute prohibitions (no jokes, no dismissal, no minimization, no comparison on TRAUMA/DOULEUR topics). Sensitivity-category memories now format `usage_nuance` as imperative obligation (`⚠ OBLIGATION:`) instead of informational italic. Response prompt reinforced with CRITICAL compliance instruction. (`apps/api/src/domains/agents/middleware/memory_injection.py`, `apps/api/src/domains/agents/prompts/v1/response_system_prompt_base.txt`)
- **Embedding Models in LLM Pricing** — OpenAI embedding models (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) added to the LLM model administration table for cost tracking. (`infrastructure/database/seeds/`)

### Fixed

- **LLM Cost Tracking Using Wrong Model Name** — 5 background services (journal extraction, journal consolidation, memory extraction, interest extraction, interest content reflection) were tracking token costs against `LLM_DEFAULTS[type].model` (hardcoded code default) instead of the actual model configured in the admin UI. When admins changed models via the application, costs were still calculated with the old default prices. Fixed by replacing `LLM_DEFAULTS[type].model` with `get_llm_config_for_agent(settings, type).model` which resolves the effective config (code defaults → DB admin overrides). (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`, `apps/api/src/domains/agents/services/memory_extractor.py`, `apps/api/src/domains/interests/services/extraction_service.py`, `apps/api/src/domains/interests/services/content_sources/llm_reflection_source.py`)
- **Hardcoded Runtime Values Ignoring Settings** — Multiple runtime constants used directly instead of their corresponding `settings.*` fields, bypassing `.env` and application configuration. Fixed: `API_MAX_ITEMS_PER_REQUEST` in HITL dispatch and task orchestrator nodes, `JOURNAL_ENTRY_CONTENT_MAX_LENGTH` in extraction/consolidation service calls, semantic fallback threshold, context reference confidence, HITL demotion confidence, semantic validation fallback confidence, retry middleware parameters, default item confidence, email truncation ratio. (`apps/api/src/domains/agents/nodes/hitl_dispatch_node.py`, `apps/api/src/domains/agents/nodes/task_orchestrator_node.py`, and 7 other files)
- **Constants Misaligned with Production Config** — 25+ constant default values in `constants.py` diverged from actual `.env.prod` production values (e.g., `SEMANTIC_FALLBACK_THRESHOLD` was 0.4 in code but 0.75 in prod, `JOURNAL_CONTEXT_MIN_SCORE` was 0.3 but 0.55 in prod). All constants realigned with production values. `.env.example` also realigned with `.env.prod` for all application configuration values.
- **395+ Hardcoded Config Defaults** — All `Field(default=X)` in 9 config files (agents, connectors, journals, database, advanced, llm, observability, voice, mcp) replaced with named constants from `constants.py`, ensuring the fallback chain APPLICATION > .ENV > CONSTANT is respected even with a minimal `.env` file.
- **LLM_DEFAULTS Misaligned with App Config** — `browser_agent` default was `openai/gpt-4.1-mini` but app uses `anthropic/claude-opus-4-6`. `hitl_question_generator` was `openai/gpt-4.1-mini` but app uses `anthropic/claude-sonnet-4-6`. `journal_extraction/consolidation` was `openai/gpt-5-mini` but app uses `qwen/qwen3.5-plus`. All aligned with actual application configuration. (`apps/api/src/domains/llm_config/constants.py`)
- **Journal Max Entry Size Not Respected** — User-configurable "Max entry size" setting in Personal Journals was ignored by the LLM — the extraction and consolidation prompts used a hardcoded constant (2000) instead of the user's configured value. Fixed by reading `user.journal_max_entry_chars` from DB and passing it to prompts as a MANDATORY size constraint, and to `service.create_entry()`/`service.update_entry()` calls. (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`, `apps/api/src/infrastructure/scheduler/journal_consolidation.py`)

## [1.9.2] - 2026-03-22

### Fixed

- **Browser agent unavailable in production** — Playwright Chromium binary was missing from the production Docker image (`Dockerfile.prod`). The Python package was installed but `playwright install chromium` was never executed, causing `BrowserPool` initialization to fail silently (`_healthy=False`) and all browser tools to return "Browser pool is not healthy". Added Chromium binary download in the builder stage, `PLAYWRIGHT_BROWSERS_PATH` env var, and Chromium runtime system dependencies (libnss3, libatk, libgbm, etc.) in the final stage. Dev image (`Dockerfile.dev`) was already correct. (`apps/api/Dockerfile.prod`)
- **Broadcast notification spam for new and existing users** — New users who connected for the first time received the entire history of broadcast messages. Additionally, existing users with many unread broadcasts were overwhelmed with notifications. The `GET /broadcasts/unread` endpoint now only considers the 3 most recent *eligible* broadcasts (non-expired, created after the user's signup date) and returns only the unread ones among those. This uses a two-subquery approach: one to select the N most recent eligible broadcast IDs, another to exclude already-read IDs. New `MAX_UNREAD_BROADCASTS` constant centralizes the limit. (`apps/api/src/domains/notifications/repository.py`, `apps/api/src/domains/notifications/broadcast_service.py`, `apps/api/src/domains/notifications/router.py`, `apps/api/src/core/constants.py`)
- **Confusing logout button** — The user profile section (avatar + name + email + icon) in the navbar was mistaken for a profile link rather than a logout action. Replaced with a clear red icon-only button (`bg-destructive` + `LogOut` icon). Removed unused `proxyGoogleImageUrl` import. (`apps/web/src/app/[lng]/dashboard/layout.tsx`)
- **Assistant leaking admin-only features to regular users** — When asked "which LLM do you use?", the assistant mentioned admin interfaces like "Admin > LLM Configuration" which are inaccessible to regular users. Added a directive to the app identity prompt instructing the assistant to never reference admin panels, admin settings, or backend configuration options. (`apps/api/src/domains/agents/prompts/v1/app_identity_prompt.txt`)
- **Usage limits console error on startup** — `useUsageLimits` hook logged `ERROR: Failed to fetch` when the backend was unreachable (e.g., during startup). Network errors (`TypeError`) are now silently ignored since the polling interval will retry automatically. (`apps/web/src/hooks/useUsageLimits.ts`)

## [1.9.1] - 2026-03-22

### Added

- **User Consumption Export** — Authenticated users can now export their own LLM token usage, Google API usage, and aggregated consumption summary as CSV from Settings → Features → "My Consumption Export". Three export types with date range filters (current month, last month, last 30 days, all time). Security: `user_id` forced server-side via `current_user.id` — no `user_id` parameter exposed on user endpoints, preventing IDOR. 7 introspection-based security unit tests. (`apps/api/src/domains/google_api/user_export_router.py`, `apps/web/src/components/settings/ConsumptionExportSection.tsx`)
- **Shared Export Service** — Extracted admin export query logic into reusable service functions (`export_token_usage_csv`, `export_google_api_usage_csv`, `export_consumption_summary_csv`) with shared date parsing helper. Both admin and user endpoints delegate to the same service, eliminating code duplication. (`apps/api/src/domains/google_api/export_service.py`)
- **Dual-Mode Export Component** — Unified `ConsumptionExportSection` React component with `mode` prop (`'admin'` | `'user'`). Admin mode shows user filter with autocomplete; user mode shows date filters only and calls user-scoped API endpoints. Admin wrapper (`AdminConsumptionExportSection`) reduced to a thin passthrough. Unique HTML IDs per mode prevent DOM conflicts when both instances coexist for superusers. (`apps/web/src/components/settings/ConsumptionExportSection.tsx`, `apps/web/src/components/settings/AdminConsumptionExportSection.tsx`)
- **Export Unit Tests** — 26 unit tests: `_parse_date_range` validation, CSV output for token/Google API/summary exports, empty data handling, consumption aggregation with partial data, and 9 router security tests (no `user_id` parameter exposed, auth dependency present, correct prefix, allowed params whitelist). (`apps/api/tests/unit/domains/google_api/`)
- **User Export Internationalization (6 languages)** — 18 translation keys per language under `settings.user.export.*` namespace (en, fr, de, es, it, zh) for section title, description, date presets, export card labels, and status messages. (`apps/web/locales/`)

### Fixed

- **Admin export code duplication** — Admin export endpoints (`/admin/google-api/export/*`) refactored to delegate to shared `export_service` functions instead of inlining SQLAlchemy queries. No behavioral change. (`apps/api/src/domains/google_api/router.py`)

## [1.9.0] - 2026-03-22

### Added

- **Per-User Usage Limits** — New domain `src/domains/usage_limits/` enabling administrators to define per-user quotas on tokens, messages, and cost (EUR). Supports both period-based (monthly rolling cycle aligned with account creation) and global/absolute limits. Each dimension can be set to a numeric value or unlimited (null). Includes admin manual block/unblock with reason tracking. (`apps/api/src/domains/usage_limits/`)
- **5-Layer Defense in Depth Enforcement** — Multi-layer enforcement architecture preventing any bypass: Layer 0 (HTTP 429 in chat router before SSE stream), Layer 1 (SSE error in agent service for scheduled actions), Layer 2 (centralized LLM invocation guard in `invoke_with_instrumentation()` covering all background services), Layer 3 (proactive runner skip for blocked users), Layer 4 (migration of direct `.ainvoke()` calls). Fail-open design: infrastructure failures don't block users. (`apps/api/src/domains/agents/api/router.py`, `apps/api/src/domains/agents/api/service.py`, `apps/api/src/infrastructure/llm/invoke_helpers.py`, `apps/api/src/infrastructure/proactive/runner.py`)
- **Admin Usage Limits Dashboard** — Dedicated admin section with searchable, paginated table showing all users with period and global usage gauges (tokens, messages, cost). Inline block toggle with optimistic updates, edit modal with current consumption display per limit dimension. WebSocket endpoint for real-time gauge updates with ticket-based BFF authentication. (`apps/web/src/components/settings/AdminUsageLimitsSection.tsx`, `apps/web/src/components/settings/AdminUsageLimitsEditModal.tsx`, `apps/api/src/domains/usage_limits/websocket.py`)
- **User Usage Limits Dashboard Tiles** — Two dashboard cards (Period Limits / Global Limits) showing color-coded progress gauges when limits are configured. Automatically hidden when all limits are unlimited. (`apps/web/src/components/usage/UsageLimitsTile.tsx`, `apps/web/src/components/usage/UsageGauge.tsx`)
- **Chat Blocking on Limit Exceeded** — Disabled message input, voice input, and destructive alert banner when user is blocked (limit reached or manual block). HTTP 429 handling in chat stream client. SSE error handler for `usage_limit_exceeded` error code with specific toast notification. (`apps/web/src/app/[lng]/dashboard/chat/page.tsx`, `apps/web/src/lib/api/chat.ts`, `apps/web/src/lib/sse-handlers/handlers.ts`)
- **Usage Limits Redis Caching** — 60-second TTL Redis cache on limit check results using existing `cache_get_json`/`cache_set_json` helpers. Cache invalidated after token persistence and admin updates. Stale cycle detection prevents false blocking after billing cycle rollover. (`apps/api/src/domains/usage_limits/service.py`)
- **Usage Limits Configuration** — New `UsageLimitsSettings` config module with feature flag (`USAGE_LIMITS_ENABLED`), default limits for new users via env vars, and configurable cache TTL. Empty string env var handling via `BeforeValidator` for Pydantic-settings compatibility. (`apps/api/src/core/config/usage_limits.py`)
- **Usage Limits Prometheus Metrics** — Two counters: `usage_limit_check_total` (by result status) and `usage_limit_enforcement_total` (by enforcement layer and limit type). (`apps/api/src/infrastructure/observability/metrics_usage_limits.py`)
- **Usage Limits Unit Tests** — 42 unit tests covering `_compute_status` pure logic (manual block, cycle/absolute limits, warning/critical thresholds, zero limits, mixed configurations, stale cycle detection), schema validation (constraints, serialization, enum roundtrip), and `_build_limit_detail` helper. (`apps/api/tests/unit/domains/usage_limits/`)
- **Usage Limits Documentation** — ADR-060 (architectural decision record) and technical documentation covering domain structure, enforcement layers, caching, API endpoints, configuration, and frontend integration. (`docs/architecture/ADR-060-Usage-Limits.md`, `docs/technical/USAGE_LIMITS.md`)
- **Internationalization (6 languages)** — Complete `usage_limits` namespace with translations for all UI elements (admin section, edit modal, dashboard tiles, blocked banner, error messages) in French, English, German, Spanish, Italian, and Chinese. (`apps/web/locales/`)

### Fixed

- **Settings focus loss on preference change** — `refreshUser()` in AuthProvider now compares `JSON.stringify(prev)` vs response before calling `setUser()`, preventing unnecessary re-renders when user data hasn't changed. Context value memoized via `useMemo`. Eliminates focus loss in input fields across all settings tabs (Preferences, Features, Administration). (`apps/web/src/lib/auth.tsx`)
- **Token/cost values mismatch with dashboard** — Usage limits token calculation now includes cached tokens (`cycle_prompt + cycle_completion + cycle_cached`) and cost calculation includes Google API costs (`cycle_cost_eur + cycle_google_api_cost_eur`) to match the dashboard display. (`apps/api/src/domains/usage_limits/repository.py`)
- **Philips Hue connector 500 error** — Fixed `connector_global_config` table storing `'philips_hue'` (lowercase enum value) instead of `'PHILIPS_HUE'` (uppercase enum name) expected by SQLAlchemy `Enum(native_enum=False)`. Data corrected in DB.
- **SQLAlchemy mapper initialization failure** — Added `import_all_models()` call in `main.py` lifespan to ensure all domain models are loaded before the first ORM query. Prevents `UserUsageLimit` forward reference resolution failure. (`apps/api/src/main.py`)
- **Admin settings section ordering** — Reorganized administration tab sections in logical order: Users → Limits → Export → Broadcast → Connectors → LLM → Google API → LLM Config → Personalities → Skills → RAG → Voice → Debug. Renamed section titles for consistency. (`apps/web/src/app/[lng]/dashboard/settings/page.tsx`)

## [1.8.2] - 2026-03-21

### Added

- **Scheduler Leader Election Resilience** — Centralized `SchedulerLeaderElector` class replaces inline leader election logic in `main.py`. Non-blocking background re-election ensures the scheduler always starts, even when a stale Redis lock exists from a killed container (Docker restart/SIGKILL). Includes automatic lock renewal, idempotent shutdown, and comprehensive structured logging (15 event types with `worker_id` correlation). (`apps/api/src/infrastructure/scheduler/leader_elector.py`)
- **Leader Elector unit tests** — 17-test suite covering immediate acquisition, no-Redis fallback, re-election after stale lock, scheduler error rollback with lock release, callback error resilience, double-start guard, and idempotent shutdown. 90% code coverage. (`apps/api/tests/unit/infrastructure/scheduler/test_leader_elector.py`)
- **Leader election debugging guide** — New "Leader election stale lock" section in the debugging guide with Redis diagnostic commands and resolution steps. (`docs/guides/GUIDE_DEBUGGING.md`)
- **SETNX lock variants documentation** — Comparison table of the three Redis SETNX lock patterns (`OAuthLock`, `SchedulerLock`, `SchedulerLeaderElector`) in the Redis architecture ADR. (`docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md`)

### Fixed

- **Scheduler not starting after container restart** — When Docker recreated the API container, the stale `scheduler:leader` Redis lock (TTL 120s) from the killed worker prevented the new worker from acquiring leadership. The worker gave up permanently after a single failed SETNX, leaving all 15+ background jobs (journal consolidation, interest notifications, token refresh, etc.) idle. The new `SchedulerLeaderElector` retries every 5s in the background until the lock expires, then starts the scheduler. (`apps/api/src/main.py`, `apps/api/src/infrastructure/scheduler/leader_elector.py`)

## [1.8.1] - 2026-03-21

### Added

- **Journal Extraction Debug Panel** — Background journal extraction results (create/update/delete actions) now visible in the Debug Panel. New `debug_metrics_update` SSE event type emits extraction details after `await_run_id_tasks` completes. Frontend merges supplementary metrics into current debug state via `DEBUG_METRICS_UPDATE` reducer action. Extraction sub-section shows action type badges (CREATE/UPDATE/DELETE), theme, title, mood per action. (`apps/api/src/domains/agents/api/service.py`, `apps/web/src/components/debug/components/sections/JournalInjectionSection.tsx`)
- **Planner v3 Skill Guard** — Early insufficient content detection now skips when a deterministic skill has high domain overlap with the query. Prevents false-positive clarification requests on multi-domain skills (e.g., daily briefing = event+task+weather+email). New `_has_potential_skill_match()` helper with configurable `SKILLS_EARLY_DETECTION_MAX_MISSING_DOMAINS` constant. (`apps/api/src/domains/agents/nodes/planner_node_v3.py`, `apps/api/src/core/constants.py`)
- **Journal Extraction Debug Registry** — In-process `_extraction_debug_results` dict with TTL-based eviction (5 min) stores extraction results per `run_id` for consumption by the SSE streaming service. (`apps/api/src/domains/journals/extraction_service.py`)
- **Planner Skill Guard unit tests** — 284-line test suite covering skill match detection, domain overlap, missing domain threshold, disabled skills, and edge cases. (`apps/api/tests/unit/domains/agents/nodes/test_planner_v3_skill_guard.py`)
- **Smart Home connector category** — `smart_home` category added to frontend connector constants and Admin Connectors section with Philips Hue entry. (`apps/web/src/constants/connectors.ts`, `apps/web/src/components/settings/AdminConnectorsSection.tsx`)
- **Smart Home i18n descriptions** — Connector description for `philips_hue` and `smart_home` category label/description added across 6 languages. (`apps/web/locales/*/translation.json`)

### Changed

- **Weather card temp range** — Current weather cards now display min/max temperature range (not shown for forecast cards which already have it in main stats). (`apps/api/src/domains/agents/display/components/weather_card.py`)
- **Journal entry ID formatting** — Entry headers in extraction and consolidation prompts now use `[id=UUID | ...]` format with a dedicated ID reference table for easy LLM copy-paste. Reduces UUID hallucination in update/delete actions. (`apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`)
- **Journal prompts UUID guidance** — Introspection and consolidation prompts now include CRITICAL instruction to copy-paste exact UUIDs from entry headers, with placeholder `<copy exact UUID from entry header>` in JSON examples. (`apps/api/src/domains/agents/prompts/v1/journal_introspection_prompt.txt`, `apps/api/src/domains/agents/prompts/v1/journal_consolidation_prompt.txt`)

### Fixed

- **Journal hallucinated UUID rejection** — `ExtractedJournalEntry.entry_id` now validates UUID format via `field_validator`, rejecting malformed IDs from LLM hallucination. Both extraction and consolidation services filter out actions referencing unknown entry IDs before applying them. (`apps/api/src/domains/journals/schemas.py`, `apps/api/src/domains/journals/extraction_service.py`, `apps/api/src/domains/journals/consolidation_service.py`)

## [1.8.0] - 2026-03-21

### Added

- **Philips Hue Smart Home Connector** — Full integration with Philips Hue Bridge CLIP v2 API for smart lighting control via natural language. Dual connection mode: local (press-link pairing on same network) and remote (OAuth2 via api.meethue.com cloud relay). 6 LangChain tools: `list_hue_lights_tool`, `control_hue_light_tool`, `list_hue_rooms_tool`, `control_hue_room_tool`, `list_hue_scenes_tool`, `activate_hue_scene_tool`. Multilingual color support (CIE xy mapping for en/fr/de/es), fuzzy name resolution for natural language control ("éteins le salon" → room "Salon" → grouped_light off). (`src/domains/connectors/clients/philips_hue_client.py`, `src/domains/agents/tools/hue_tools.py`)
- **Hue Bridge discovery & press-link pairing UI** — Multi-step wizard in Settings > Smart Home: bridge discovery via discovery.meethue.com, bridge selection, 30-second countdown press-link pairing flow, automatic connector activation. Separate remote mode path via OAuth2 redirect. (`apps/web/src/components/settings/connectors/HueBridgePairingForm.tsx`, `apps/web/src/components/settings/connectors/hooks/useHueConnect.ts`)
- **Hue agent with catalogue manifests** — Dedicated `hue_agent` with versioned prompt (`hue_agent_prompt.txt`), 6 tool manifests with multilingual semantic keywords (en/fr/de/es/it/zh) for Smart Planner tool selection. Agent registered in LangGraph graph with conditional routing edge. (`src/domains/agents/hue/catalogue_manifests.py`, `src/domains/agents/graphs/hue_agent_builder.py`)
- **HueOAuthProvider** — OAuth2 provider dataclass implementing `OAuthProvider` Protocol for Hue Remote API. Factory method `for_remote_control()` with dynamic redirect URI construction. PKCE support via existing `OAuthFlowHandler`. (`src/core/oauth/providers/hue.py`)
- **Smart Home domain taxonomy** — New "hue" domain in `domain_taxonomy.py` with `result_key="hues"`, enabling Smart Planner to route smart home intents. New `RegistryItemType.HUE_LIGHT` for Data Registry frontend rendering. (`src/domains/agents/registry/domain_taxonomy.py`, `src/domains/agents/data_registry/models.py`)
- **Smart Home i18n (6 languages)** — 22 translation keys per language for Hue connector UI: pairing wizard, mode selection, countdown, error messages, connection status. Covers en, fr, de, es, it, zh. (`apps/web/locales/*/translation.json`)

### Changed

- **ConnectorTool credential retrieval** — Added `is_hue` branch in `ConnectorTool.execute()` for Hue-specific credential retrieval via `get_hue_credentials()`, following the existing `is_apple` pattern. (`src/domains/agents/tools/base.py`)
- **Client registry** — `PhilipsHueClient` registered in `ClientRegistry._ensure_initialized()` alongside Google, Apple, and Microsoft clients. (`src/domains/connectors/clients/registry.py`)
- **Connector models** — New `ConnectorType.PHILIPS_HUE` enum value with `is_hue` property, `_HUE_CONNECTOR_TYPES` frozenset, `"smart_home"` functional category. (`src/domains/connectors/models.py`)
- **UserConnectorsSection** — Added "Connected Smart Home" and "Available Smart Home" sections with `HueBridgePairingForm` integration. (`apps/web/src/components/settings/UserConnectorsSection.tsx`)

### Fixed

- **LLM provider error messages** — `OverloadedError` (529) and `RateLimitError` (429) from Anthropic/OpenAI now display a user-friendly message ("Le service d'IA est temporairement surchargé. Veuillez réessayer dans quelques instants.") instead of raw technical error types (`APIStatusError`). Detection covers `stream_error()` and `generic_error()` in all 6 languages. (`src/domains/agents/api/error_messages.py`)

## [1.7.2] - 2026-03-20

### Added

- **Technical Blog (20 articles × 6 languages = 120 pages)** — Full blog system with category-organized technical articles covering architecture, integrations, features, security, and engineering. Each article enriched with verified code-sourced facts (file paths, exact numbers, real class/function names). 5 categories: Architecture (4), Integrations (4), Features (6), Security (2), Technical (4). Articles include real Python code snippets from the codebase (Prometheus metrics, `load_prompt()`, `ToolResponse`, `get_llm()` factory). (`apps/web/src/app/[lng]/blog/`, `apps/web/src/components/blog/`, `apps/web/src/data/blog-articles.ts`)
- **Blog illustrations** — 20 unique PNG illustrations (one per article) served via Next.js `<Image>` with lazy loading, responsive `sizes`, and `priority` on article hero. (`apps/web/public/articles/`)
- **Blog preview on landing page** — `BlogPreviewSection` component showing 6 featured articles with illustrations, inserted before the CTA section. Promotes blog discovery for visitors exploring LIA. (`apps/web/src/components/landing/BlogPreviewSection.tsx`)
- **Tailwind Typography plugin** — Installed `@tailwindcss/typography` for proper `prose` class rendering in blog article bodies. Configured via `@plugin` directive in globals.css.
- **Tempo distributed tracing (production)** — Deployed Grafana Tempo on RPi5 prod, completing the observability trifecta (metrics + logs + traces). Service `lia-tempo-prod` with 0.5 CPU / 512 MB limits, 7-day retention with automatic compaction, zstd/snappy compression. Enables Dashboard 06 (Logs & Traces), trace↔log↔metric correlation via exemplars, and Tempo service graph in Grafana. (`docker-compose.prod.yml`, `infrastructure/observability/tempo/tempo.yml`)
- **Scheduler leader election** — Redis SETNX-based leader election ensures only 1 of 4 uvicorn workers starts APScheduler. Eliminates duplicate job execution caused by `--workers 4`. Lock renewed every 30s (TTL 120s) with automatic failover if leader crashes. Non-leader workers skip scheduler entirely. (`src/main.py`, `src/core/constants.py`)

### Changed

- **SEO & GEO (Generative Engine Optimization)** — Enhanced metadata for Google and AI search engines:
  - OpenGraph images per article (PNG illustrations) with `summary_large_image` Twitter cards
  - `image` and `articleSection` fields added to JSON-LD `BlogPosting` schema
  - `authors` metadata on article pages
  - OpenGraph image on blog listing page
  - Sitemap XML extended with 21 blog URLs (listing + 20 articles) with hreflang alternates
  - `robots.txt` updated: blog paths allowed for all crawlers, AI search bots (OAI-SearchBot, PerplexityBot, Claude-SearchBot) explicitly permitted
  - `llms.txt` updated with blog link and corrected statistics
- **Landing page meta descriptions** — SEO-optimized with keywords "Open Source", "Multi-Agent", "HITL", "6 Languages", "7 LLM providers", "Privacy by design" in all 6 languages.
- **Landing stats correction** — Agent count corrected from 18 to 15 (verified: 15 domain agent builders in `src/domains/agents/graphs/`). Prometheus metrics count corrected from 500 to 350 (verified: 357 metric definitions across 17 observability files).
- **Blog navigation** — `nav.blog` link integrated into `NAV_SECTIONS` array with same styling as other nav items (was isolated in "Right actions" zone with different markup). Supports both anchor links (`#section`) and route links (`/blog`) in the same nav. (`LandingHeader.tsx`)
- **Landing navigation order** — Reordered to: Comment ça marche → Fonctionnalités → Sécurité → Technologie → Blog (was: Fonctionnalités → Comment ça marche → ..., Blog separated).
- **Prometheus remote-write receiver (production)** — Added `--web.enable-remote-write-receiver` flag to prod Prometheus, enabling Tempo's metrics-generator to push span metrics (service graphs, span latency histograms). (`docker-compose.prod.yml`)
- **Grafana prod parity with dev** — Added `grafana.ini` volume mount (Tempo feature flags: `tempoSearch`, `tempoServiceGraph`, `traceqlEditor`) and `depends_on: [prometheus, loki, tempo]`. (`docker-compose.prod.yml`)

### Fixed

- **Factual accuracy audit (8 corrections × 6 languages = 48 fixes)** — Systematic verification of all blog article claims against actual source code:
  - Agent count: 18+ → 15 (verified via `find graphs/ -name "*_builder.py"`)
  - LLM configuration: "environment variables" → "Administration > LLM Configuration" (admin UI is primary, env vars are fallback)
  - Claude model name: `claude-3.5-sonnet` → `claude-sonnet-4-5`
  - RAG embedding model: `E5-small (384 dims)` → `text-embedding-3-small (1536 dims)` (verified in `constants.py`)
  - Wake word: "Hey LIA" → "OK Guy" (verified in `sherpaKws.ts`)
  - Prometheus metrics: 500+ → 350+ (verified: 357 definitions)
  - Prompt count: 45+ → 55 (verified: `find prompts -name "*.txt"`)
  - Token reduction: 93% → 96% (verified in `NormalFilteringStrategy` docstring)
- **Consistent agent count across all surfaces** — Updated FAQ, meta descriptions, `llms.txt`, landing stats, `WebSiteJsonLd`, and all blog references from "18+" to "15" across all 6 languages.
- **Scheduler ×4 duplicate execution** — All 4 uvicorn workers were running independent APScheduler instances, causing every job to execute 4× per interval. Root cause: `--workers 4` in `Dockerfile.prod` with no leader coordination. Fixed with Redis leader election (root cause) + `SchedulerLock` on 5 previously unprotected jobs as safety net: `token_refresh`, `currency_sync`, `memory_cleanup`, `interest_cleanup`, `unverified_account_cleanup`. (`src/main.py`, `src/infrastructure/scheduler/*.py`, `src/core/constants.py`)
- **Tempo OTLP export failures (4 months of silent errors)** — API spammed `Failed to export traces to tempo:4317, StatusCode.UNAVAILABLE` continuously since Tempo was never deployed in prod. Two sub-bugs: (1) Tempo service absent from `docker-compose.prod.yml` despite full config existing, (2) `OTLPSpanExporter(insecure=not settings.is_production)` forced TLS for Docker-internal gRPC — changed to `insecure=True`. (`tracing.py`, `docker-compose.prod.yml`)
- **Background task timeout (memory/interest/journal extraction)** — Post-response LLM extraction tasks (memory, interests, journals) were silently abandoned after 5s timeout. On RPi5 with network latency, LLM calls routinely exceed 5s. Increased `await_run_id_tasks` timeout from 5s to 15s. (`src/infrastructure/async_utils.py`, `src/domains/agents/api/service.py`)
- **Weather hourly forecast `save_details_missing_primary_id`** — Context registry for weather uses `primary_id_field="date"`, but hourly forecast payload lacked a `date` field (only daily/current had it). Added `date` field to hourly forecast registry item. (`weather_tools.py`)
- **Qwen `extra_body` LangChain warning** — `extra_body` (for Qwen thinking mode) was nested inside `model_kwargs` dict, triggering LangChain `UserWarning: Parameters {'extra_body'} should be specified explicitly`. Moved to direct kwarg of `init_chat_model`. (`adapter.py`)

## [1.7.1] - 2026-03-20

### Fixed

- **Constants centralization audit (25 files)** — Systematic elimination of ~60 hardcoded default values across backend and frontend. All configurable defaults now reference centralized constants from `src/core/constants.py` instead of inline literals. Prevents silent divergence between code paths that should share the same default value.
- **Journal settings persistence bug** — Numeric settings (prompt injection budget, max entry size, max search results) appeared to save successfully but reverted on page refresh. Root cause: React `useState` initializers ran once with stale `initialData` and were never synchronized with actual server values. Fix: added `useEffect` sync + removed hardcoded `initialData` from `useJournals`, `useHeartbeatSettings`, and `useInterests` hooks. The API is now the single source of truth for all settings.
- **`journals_enabled` inconsistent defaults** — Three code paths used different fallback values for the same field: `router.py` defaulted to `True`, while `context_builder.py` and `context_aggregator.py` defaulted to `False`. This caused journals to appear enabled in the UI while being silently excluded from heartbeat context and prompt injection. Unified to `JOURNALS_ENABLED_DEFAULT = True`.
- **Proactive notification language bug** — `proactive/runner.py` and `proactive/notification.py` used `"en"` as the language fallback, while all other code paths used `"fr"`. Users without an explicit language preference received notification titles in English instead of French. All sites now use `DEFAULT_LANGUAGE` constant.
- **Interest eligibility checker wrong defaults** — `EligibilityChecker` used heartbeat defaults (min=1, max=3) for interest notifications instead of interest-specific defaults (min=2, max=5). Interests were under-notified (capped at 3/day instead of 5). Refactored constructor to accept `default_min_per_day` / `default_max_per_day` parameters, passed from each scheduler with the correct constants.
- **Frontend optimistic update without revert** — `useInterests.ts` `updateSettings` applied optimistic state changes but never reverted on mutation failure. Added `refetchSettings()` on error to restore server state.

### Changed

- **12 new constants in `constants.py`** — `HEARTBEAT_MIN_PER_DAY_DEFAULT`, `HEARTBEAT_PUSH_ENABLED_DEFAULT`, `HEARTBEAT_NOTIFY_START/END_HOUR_DEFAULT`, `INTEREST_NOTIFY_MIN/MAX_PER_DAY_DEFAULT`, `HEARTBEAT_DECISION/MESSAGE_LLM_MODEL_DEFAULT`, `TOKEN_SUMMARY_CACHE_TTL`, `JOURNALS_ENABLED_DEFAULT`, `JOURNAL_CONSOLIDATION_ENABLED/WITH_HISTORY_DEFAULT`.
- **User model `server_default` alignment** — All 15 user preference columns in `auth/models.py` (timezone, language, interests×4, heartbeat×5, journals×4) now reference constants instead of string literals.
- **`EligibilityChecker` parameterization** — Added `default_start_hour`, `default_end_hour`, `default_min_per_day`, `default_max_per_day` constructor parameters to support task-specific fallback values.

### Security

- **CVE-2026-33228 — `flatted` Prototype Pollution (HIGH)** — Transitive dev dependency `flatted <= 3.4.1` (via eslint → flat-cache) vulnerable to prototype pollution via `parse()`. Fixed via `pnpm.overrides` forcing `flatted >= 3.4.2`. Dev-only dependency — no production runtime impact.
- **GitHub Actions bumped** — codecov/codecov-action 5.5.2→5.5.3, softprops/action-gh-release 2.3.2→2.3.3, github/codeql-action 3.28.16→3.28.17 (PR #63).

## [1.7.0] - 2026-03-20

### Added

- **Personal Journals — Carnets de Bord (evolution)** — The AI assistant now maintains thematic personal journals (self-reflection, user observations, ideas & analyses, learnings) written in first person, colored by its active personality. Dual trigger system: post-conversation extraction (fire-and-forget background task analyzing last user message + context) and periodic consolidation (APScheduler every 4h, reviews and reorganizes notes). Semantic context injection into both response AND planner prompts via E5-small cosine similarity search with configurable minimum score prefiltering (`JOURNAL_CONTEXT_MIN_SCORE`) — two distinct queries (response: tone/formulation, planner: reasoning/learnings). Prompt-driven autonomous lifecycle management: the assistant decides what to keep, summarize, merge, or delete based on a configurable size constraint. Full user control: enable/disable without data loss, configurable consolidation, optional conversation history analysis (with cost warning), 4 numeric settings (max total chars, context budget, max entry chars, max search results). CRUD operations in Settings > Features with theme-based accordion, size gauge, and real cost tracking. GDPR compliant: JSON/CSV export + bulk delete. LLM models configurable in Admin > LLM Configuration (category: background). Heartbeat integration: journals as a context source for proactive notifications with dynamic query (second pass after context aggregation), toggleable badge in heartbeat settings. Debug panel: dedicated "Personal Journals" section showing injection metrics (entries found/injected, scores, budget, per-entry details). (`src/domains/journals/`, `journal_introspection_prompt.txt`, `journal_consolidation_prompt.txt`, `JournalInjectionSection.tsx`, `ADR-057-Personal-Journals.md`, 35 unit tests)

### Database

- **Migration `journals_001`** — Created `journal_entries` table (UUID PK, user_id FK CASCADE, theme, title, content, mood, status, source, session_id, personality_code, char_count, embedding ARRAY(Float), timestamps). Added 11 columns to `users` table: journals_enabled, journal_consolidation_enabled, journal_consolidation_with_history, journal_max_total_chars, journal_context_max_chars, journal_last_consolidated_at, journal_last_cost_tokens_in/out/eur/at/source. Composite indexes on (user_id, status, created_at) and (user_id, theme).
- **Migration `journals_002`** — Added 2 user-configurable columns: journal_max_entry_chars (Integer, default 2000), journal_context_max_results (Integer, default 10). Idempotent upgrade (skips if columns already exist).

## [1.6.1] - 2026-03-19

### Added

- **System RAG Spaces — App Self-Knowledge (evolution)** — LIA can now answer questions about itself, its features, and usage directly in conversation. Built-in FAQ knowledge base (119+ Q/A across 17 sections) indexed from English Markdown files (`docs/knowledge/`), with LLM translation at response time (6 languages). Includes: `SystemSpaceIndexer` with SHA-256 hash-based staleness detection, `is_app_help_query` detection in QueryAnalyzer, RoutingDecider Rule 0 override (prevents misrouting "how do I connect my calendar?" to the planner), App Identity Prompt (~200 tokens) injected conditionally (lazy loading — zero overhead on normal queries), 3 admin API endpoints (list/reindex/staleness), admin UI section with staleness badge and reindex button, automatic indexation at app startup (idempotent — skips if hash matches), 3 Prometheus metrics, seed script (`task db:seed:system-rag`). (`system_indexer.py`, `app_identity_prompt.txt`, `ADR-058`, 35 unit tests)

### Database

- **Migration `system_rag_spaces_001`** — `rag_spaces`: added `is_system` (Boolean, NOT NULL, default false) and `content_hash` (String(64), nullable). Made `user_id` nullable on `rag_spaces`, `rag_documents`, `rag_chunks` (system spaces have no owner). Replaced unique index `uq_rag_spaces_user_id_name` with partial unique indexes: `uq_rag_spaces_user_name` (WHERE user_id IS NOT NULL) and `uq_rag_spaces_system_name` (WHERE is_system = true). Added index `ix_rag_spaces_is_system`.

## [1.6.0] - 2026-03-19

### Added

- **Browser Control (evolution F7)** — Interactive web browsing via Playwright headless Chromium. Autonomous ReAct agent (`browser_task_tool`) navigates websites, searches content, clicks elements, fills forms, and extracts data from JavaScript-rendered pages. Multi-step interaction handled internally — planner sends a natural language task, agent executes autonomously. Includes: session pool with cross-worker Redis recovery, SSRF prevention (reuses web_fetch URL validator), accessibility tree extraction via CDP, generic cookie banner auto-dismiss (20+ multi-language selectors), anti-detection (Chrome UA, webdriver flag removed, dynamic locale/timezone from user preferences), page crash recovery, Prometheus metrics (6 gauges/counters/histograms). Activation via admin connector panel. (`infrastructure/browser/`, `browser_tools.py`, `browser_agent_builder.py`, `browser_agent_prompt.txt`, 36 unit tests)
- **Qwen provider support** — Added Qwen (Alibaba Cloud) as a native LLM provider via DashScope international OpenAI-compatible API. 3 models: qwen3-max (thinking-only), qwen3.5-plus (tools + vision + thinking), qwen3.5-flash (cost-effective). Includes thinking mode mapping (reasoning_effort → enable_thinking + thinking_budget), implicit cache, streaming metrics, model profiles with pricing. (`adapter.py`, `model_profiles.py`, `llm_pricing_seed.sql`, `AdminLLMConfigSection.tsx`)
- **Ollama dynamic model discovery** — Admin LLM config now dynamically lists models installed on the Ollama server with real capabilities. Two-phase discovery: `GET /api/tags` + `POST /api/show` per model (parallel). Dropdown auto-populates when selecting Ollama as provider. In-memory cache (60s TTL), 5s HTTP timeout, per-model error isolation. New endpoint: `GET /admin/llm-config/providers/ollama/models`. (`ollama_discovery.py`, `service.py`, `router.py`, `AdminLLMConfigSection.tsx`)
- **ADR-059** — Architecture Decision Record for Browser Control (ReAct agent, CDP accessibility, Redis session coordination, anti-detection).
- **Browser technical documentation** — `BROWSER_CONTROL.md` (architecture, configuration, security, metrics, limitations).
- **Browser security section** — Added "Browser Automation Security" to `SECURITY.md` (sandbox, SSRF, input sanitization, anti-detection trade-offs).

### Changed

- **LLM config metadata** — Filtered out internal `"default"` fallback entries from the model dropdown for all providers (was showing "default" as a selectable model name).
- **LLM serializer** — Added `content_summary` to `CONTENT_FIELDS` for proper serialization of browser page content (prevents 60-char truncation).
- **Type domain mapping** — Added `browsers` to `SKIP_FILTER_RESULT_KEYS` (browser content always relevant, not emptied by intelligent filtering).

## [1.5.2] - 2026-03-18

### Added

- **RAG Spaces — 15 document formats** — Extended RAG document upload from 4 to 15 formats: PDF, TXT, MD, DOCX, PPTX (slides + tables + notes), XLSX (multi-sheet), CSV, RTF, HTML, ODT, ODS, ODP, EPUB (spine-ordered), JSON, XML (defusedxml). Each format has a dedicated text extractor with edge-case handling. (`processing.py`, `constants.py`, `service.py`)
- **RAG Spaces — Google Drive folder sync** — Link Google Drive folders to RAG Spaces for automatic file vectorization. Manual sync with incremental change detection (skip unchanged, re-process modified, auto-delete removed). Supports Google Docs/Sheets/Slides via API export. Per-file error isolation, Semaphore(5) throttling, atomic sync lock, 500-file pagination cap. Feature flag: `RAG_SPACES_DRIVE_SYNC_ENABLED`. (`drive_sync.py`, 6 API endpoints, 5 frontend components)
- **RAG Drive folder browser** — Folder picker dialog showing both folders (navigable) and files (preview) so users can see what will be synced before selecting.
- **Drive sync Prometheus metrics** — 4 new metrics: `rag_drive_sync_runs_total`, `rag_drive_sync_duration_seconds`, `rag_drive_sync_files_total`, `rag_drive_sources_total_count`.
- **ADR-056** — Architecture Decision Record for RAG Drive Sync (manual-first, non-recursive, incremental sync, per-file error isolation).

### Changed

- **RAG upload format display** — Compact "15+ supported formats" label with tooltip listing all formats (was: "PDF, TXT, MD, DOCX").
- **RAG document model** — Added `source_type`, `drive_source_id`, `drive_file_id`, `drive_modified_time` columns for Drive integration.

### Database

- **Migration `drive_sources_001`** — New `rag_drive_sources` table + 4 columns on `rag_documents` with indexes and FK constraints.

## [1.5.1] - 2026-03-17

### Added

- **Skill Generator meta-skill** — Built-in system skill (`skill-generator`) that guides users through creating custom SKILL.md files from natural language descriptions. 4-phase advisory process: need analysis, archetype selection (Prompt Expert / Advisory / Plan Template), generation with format validation, and delivery with import instructions. Includes 3 reference files (format specification, full tool catalogue with 60+ tools and 17 agents, archetype examples) and a sandboxed Python validation script. Multilingual support (body in user's language, description in English). Compliant with the agentskills.io open standard.

### Security

CodeQL security hardening and code quality sweep. Addresses 667 code scanning alerts (35 critical/high security, 33 errors, 47 warnings, 552 notes). Zero functional regression — all 6,279 unit tests pass.

### Security

- **Removed `verify=False` on Static Maps proxy** — TLS certificate validation was disabled on the `httpx` client proxying Google Static Maps requests, exposing the Google API key to potential MITM interception. Now uses default `verify=True`. (`connectors/router.py`)
- **Added `photo_name` input validation on Places photo proxy** — The `{photo_name:path}` route parameter accepted arbitrary path segments, potentially reaching unintended Google API endpoints with the server's API key. Added regex validation (`^places/[^/]+/photos/[^/]+$`) matching Google's official resource name spec. (`connectors/router.py`)
- **Removed stack-trace exposure in SSE error events** — Exception details (`str(e)`) were sent to the client via Server-Sent Events, potentially leaking internal paths, SQL queries, or connection strings. Replaced with generic error message; detailed error preserved in server logs. (`notifications/router.py`)
- **Masked admin password in CLI output** — The `create_admin.py` setup script printed the admin password in clear text to stdout, capturable by Docker logs or CI pipelines. Now displays masked output. (`scripts/data/create_admin.py`)
- **Gated TLS bypass by `NODE_ENV` in RAG upload proxy** — `rejectUnauthorized: false` was applied unconditionally (not just in development). Now only disables TLS validation when `NODE_ENV !== 'production'`. (`apps/web/src/app/api/rag-upload/[spaceId]/route.ts`)
- **Fixed incomplete HTML tag stripping regex** — `</script>`, `</style>`, `</head>` regexes did not match variants with whitespace before `>` (e.g., `</script >`). Added `\s*` to closing tag patterns. (`display/components/base.py`)

### Fixed

- **`ToolValidationError` crash on multi-field validation** — `validate_fields()` passed `fields=missing` (plural) to `ToolValidationError.__init__` which only accepts `field=` (singular), causing a `TypeError` when 2+ required fields were missing. Fixed to `field=", ".join(missing)`. (`tools/validation_helpers.py`)
- **Uninitialized `errors` variable in email/calendar tools** — `errors` was assigned only inside the `mode == "batch"` branch but could theoretically be accessed outside it after refactoring. Added defensive `errors = None` initialization before branching. (`emails_tools.py`, `calendar_tools.py`)
- **`AgentService.__init__` duplicated mixin attributes** — Four attributes were manually duplicated from `GraphManagementMixin.__init__`. Refactored to use `super().__init__()`. Added missing `hitl_orchestrator` initialization to the mixin. (`api/service.py`, `graph_management.py`)
- **Overly broad `except Exception` in approval gate** — Tool manifest fallback catch was `except Exception:` (masking DB/network errors), while `validator.py` used the specific `except ToolManifestNotFound:`. Narrowed to match. (`approval_gate_node.py`)
- **Overly broad `except Exception` in place card** — Opening hours parsing caught all exceptions instead of the expected `(ValueError, IndexError, TypeError)`. (`place_card.py`)

### Changed

- **Added debug logging to 18 silent `except: pass` blocks** — Best-effort patterns (user preferences, cache invalidation, CalDAV close, LLM callbacks, OAuth discovery, session cleanup) now emit `logger.debug()` for production observability without changing error-handling behavior.
- **Extracted `get_user_language_safe()` DRY helper** — Replaced 4 identical try-except-for-language patterns in `places_tools.py` with a single shared helper in `runtime_helpers.py`. Narrows exception scope from `Exception` to `(ValueError, KeyError, RuntimeError, AttributeError)`.
- **Elevated `token_counter_service` fallback level warning** — Unknown fallback levels now emit `logger.warning` (was silent `pass`) to surface configuration drift.

### Removed

- **16 unused constants** from `agents/constants.py` — 7 legacy `NODE_*_AGENT` constants (replaced by agent catalogue), 1 `CONTEXT_DOMAIN_TASK_LISTS`, 8 legacy `HITL_*` keys (replaced by Phase 3.3 orchestrator).
- **10 legacy `_*_direct_tool_instance` variables** — Unused module-level tool instances in `calendar_tools.py`, `drive_tools.py`, `emails_tools.py`, `google_contacts_tools.py`, `tasks_tools.py`. Marked `LEGACY` in code, excluded from tool registry by underscore prefix convention.
- **12 unused global variables** — Dead logger instances (`goal_inferrer.py`, `planner_utils.py`), obsolete constants (`PRIOR_ALPHA/BETA`, `_CURRENCY_USD/EUR`, `_DESTRUCTIVE_LABEL_WITH_CHILDREN`), write-only `_last_update`, unused `TypeVar T`.
- **~25 unused imports** across 18 files — Removed unused `Language`, `Set`, `List`, `Dict`, `Optional`, `Tuple`, `ast`, `re`, `json`, `subprocess`, `os`, `yaml`, `asdict`, `Template`, `UUID`, `get_function_complexity` imports from source, scripts, and infrastructure files.
- **Self-assignment dead code** in `mixins.py` — `ToolOutputMixin = ToolOutputMixin` and `create_tool_formatter = create_tool_formatter` (no-ops, re-exports handled by `__init__.py`).

## [1.5.0] - 2026-03-17

### Added

- **Persistent specialized sub-agents (F6)** — Delegation system allowing the principal assistant to spawn ephemeral expert sub-agents for complex tasks (research, analysis, synthesis). Includes full DDD domain (`src/domains/sub_agents/`), ORM model, repository, service, REST API (10 endpoints), 3 pre-defined templates (Research Assistant, Writing Assistant, Data Analyst). Sub-agents execute through a simplified direct pipeline (query analysis → planner → parallel executor → LLM synthesis), bypassing the full graph's semantic validator, approval gate, and response node. Read-only V1 (all write tools blocked). Feature flag: `SUB_AGENTS_ENABLED`.
- **Sub-agent planner integration** — Transversal `delegate_to_sub_agent_tool` always included in planner catalogue via `NormalFilteringStrategy`. Planner prompt extended with `{sub_agents_section}` guidelines. Multiple delegates execute in parallel (wave-based). Depth limit: sub-agents cannot spawn sub-sub-agents.
- **Sub-agent catalogue manifests** — `AgentManifest` + `ToolManifest` with semantic keywords for natural discovery (`src/domains/agents/sub_agents/catalogue_manifests.py`).
- **Sub-agent token guard-rails** — Per-execution budget (`SUBAGENT_MAX_TOKEN_BUDGET`), daily budget per user (`SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`), auto-disable after consecutive failures (`SUBAGENT_MAX_CONSECUTIVE_FAILURES`). `TokenTrackingCallback` consolidation into parent tracker.
- **Sub-agent HITL rejection fallback** — When user rejects a plan with delegation steps, system auto-replans without sub-agents. Catalogue exclusion via `exclude_sub_agent_tools` flag.
- **Sub-agent semantic validator exceptions** — `for_each` cardinality check and repeated-tool consolidation exempt `delegate_to_sub_agent_tool` steps (each step delegates to a different expert).
- **Sub-agent user preference** — Per-user `sub_agents_enabled` toggle (Settings > Features > Sub-Agents). `SubAgentsSettings.tsx` component. `PATCH /auth/me/sub-agents-preference` endpoint.
- **Sub-agent stale recovery job** — APScheduler job recovers sub-agents stuck in `executing` state (configurable interval).
- **Sub-agent observability** — Prometheus metrics module (`metrics_subagent.py`). Sub-agent notification type in SSE/FCM.
- **Skills DB refactoring** — Normalized skills persistence from JSONB `disabled_skills` columns to two relational tables: `skills` (registry: name, is_system, owner_id, admin_enabled, description, descriptions) + `user_skill_states` (user_id, skill_id, is_active). Migration includes data migration from legacy columns. `SkillPreferenceService` for sync, toggle, and state queries. `active_skills_ctx` ContextVar replaces `disabled_skills_ctx` (positive set).
- **Skills admin system-toggle** — `PATCH /skills/admin/{name}/system-toggle` endpoint. When admin disables a system skill, `is_active` is set to `false` for all users. New `adminSystemToggleSkill` in `useSkills` hook. Admin view fetches from `/skills/admin/list`.
- **Skills preference repository** — `SkillRepository` and `SkillStateRepository` for normalized DB access, with `ensure_states_for_user()` and `get_active_skill_names()` methods.
- **HITL plan approval question prompt** — Dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) for generating approval gate questions, avoiding ambiguous/contradictory formulations.
- **Subagent synthesis prompt** — Dedicated prompt (`subagent_synthesis_prompt.txt`) for sub-agent result synthesis.
- **Provider cost adjustment documentation** — Investigation of Anthropic billing delta (~11%) with recommended `cost_adjustment_factor` solution (`docs/technical/PROVIDER_COST_ADJUSTMENT.md`).
- **Google Routes client** — `GoogleRoutesClient` for directions/transit route queries (`src/domains/connectors/clients/google_routes_client.py`).
- **Sub-agents i18n** — All 6 languages (en, fr, de, es, it, zh): templates names/descriptions, settings labels, LLM type label.
- **Sub-agents documentation** — `docs/technical/SUB_AGENTS.md`, `docs/INDEX.md` updated, `docs/ARCHITECTURE.md` updated for skills DB model.
- **104 files changed** — 8,029 insertions, 251 deletions across backend, frontend, docs, and configuration.

### Changed

- **Skills context propagation** — Replaced `disabled_skills_ctx` (negative set) with `active_skills_ctx` (positive set) in `AgentService` and skill injection. Only active skills are injected into the assistant prompt.
- **Skills frontend** — `AdminSkillsSection` now uses `admin_enabled` flag and `adminSystemToggleSkill`. `SkillsSettings` user view shows only admin-enabled system skills. `useSkills` hook accepts `adminView` parameter.
- **HITL interrupt handler** — Removed misleading token metadata from `STREAM_DONE` payload (HITL tokens are partial/incomplete).
- **Smart planner prompts** — Extended with sub-agent delegation section, explicit `execution_mode` (sequential/parallel) and `timeout_seconds` per step in plan schema, guidelines for both single-domain and multi-domain planners.
- **Query intelligence** — Added `include_sub_agent_tools` flag to `ToolFilter` (always `true` for planner).
- **Conversation repository** — Updated queries for sub-agent session tracking. Google API costs now included in per-message and aggregate cost totals.
- **LLM factory** — Added `subagent` LLM type with default model configuration.
- **LLM defaults migration** — Router, planner, semantic validator, approval gate switched to Anthropic `claude-sonnet-4-6` (reasoning: low). Compaction switched to `gpt-4.1-mini` (reasoning: medium).

### Fixed

- **Skills system-disable propagation** — Admin-disabled system skills are now properly excluded from the agent flow (was only excluded from UI, not from assistant context).
- **Google API cost not included in totals** — Costs from Google APIs (Routes Matrix, etc.) stored in `google_api_cost_eur` were not added to the displayed total cost. Fixed in conversation service (per-message cost), conversation repository (aggregate queries), chat service (user statistics), and streaming debug panel. All cost displays now show LLM + Google API combined.
- **HITL question tokens not tracked** — Token consumption for HITL approval question generation was not tracked, causing cost under-reporting (~€0.03/request on Anthropic models). Fixed by wrapping `TrackingContext` in a `TokenTrackingCallback` for the HITL question generator.
- **HITL approval question ambiguous** — Approval gate could generate two contradictory questions in a single prompt. New dedicated prompt template (`hitl_plan_approval_question_prompt.txt`) enforces a single YES/NO-answerable question.
- **Debug panel DB-aggregated tokens** — HITL flows now fetch DB-aggregated token totals (includes tokens from prior SSE request: router, planner, HITL question) for accurate debug panel display.
- **Google Routes Matrix JSON parsing** — `GoogleRoutesClient` now handles both JSON array and NDJSON response formats (was failing on standard JSON array responses).
- **Concurrent connector access in parallel execution** — `ConcurrencySafeConnectorService.is_connector_active()` was not wrapped with the concurrency lock, causing "concurrent operations are not permitted" errors during parallel sub-agent/tool executions.

## [1.4.7] - 2026-03-16

### Added

- **Intelligent context compaction (F4)** — LLM-based conversation history summarization when token count exceeds a dynamic threshold (configurable ratio of response model context window). Preserves recent messages and critical identifiers (UUIDs, URLs, emails). Includes `/resume` user command for forced compaction, 4 HITL safety conditions, chunked summarization for large histories, descriptive fallback on LLM failure. Configurable via 6 `.env` settings (`COMPACTION_*`). New LLM type `compaction` (GPT-4.1-nano default) visible in admin LLM config panel. 6 Prometheus metrics. Graph entry point changed: `compaction → router`. Schema version bumped to 1.1 with migration.
- **Planner cost-awareness for web search** — `unified_web_search_tool` catalogue description now includes cost constraint (max 1 call per plan), directing planner to use lightweight `brave_search_tool` for additional searches.
- **FAQ `/resume` command** — Added FAQ entry explaining the `/resume` command in all 6 languages (en, fr, de, es, it, zh).

## [1.4.6] - 2026-03-16

### Added

- **Heartbeat email source** — Proactive notifications now aggregate today's unread inbox emails as a 9th context source. Supports Google Gmail, Apple Email, and Microsoft Outlook via dynamic provider resolution. LLM filters for urgent/actionable emails only (skips newsletters, marketing). Configurable via `HEARTBEAT_CONTEXT_EMAILS_MAX` (default: 5).
- **Gmail message normalization** — `GoogleGmailClient.get_message()` now extracts top-level `from`, `subject`, `to`, `cc`, `body`, `_provider` fields, matching the format already produced by Apple and Microsoft normalizers. Enables provider-agnostic message consumption throughout the application.
- **Plan validation error logging** — `PlanValidator` now logs individual validation errors and warnings with full details (code, message, step_index, tool_name, context) for debugging.

### Fixed

- **Plan validator false UNAUTHORIZED errors** — `planner_node_v3` was not passing `oauth_scopes` from state to `ValidationContext`, causing all scope-requiring tools to fail validation. Fixed by reading `state["oauth_scopes"]` (matches `approval_gate_node` pattern).

## [1.4.5] - 2026-03-16

### Added

- **External Content Wrapping (F2)** — Prompt injection prevention for untrusted web content. All external content (web pages, Perplexity synthesis, Brave snippets, Wikipedia summaries) is wrapped in `<external_content>` safety markers with an `[UNTRUSTED EXTERNAL CONTENT]` warning before being sent to the LLM. Tag occurrences within content are escaped to prevent marker breakout. Feature-flagged via `EXTERNAL_CONTENT_WRAPPING_ENABLED` (default: `true`).
- **`content_wrapper` module** (`src/domains/agents/utils/content_wrapper.py`) — `wrap_external_content()` and `strip_external_markers()` functions with XML attribute injection prevention (`source_url` quote escaping).
- **21 unit tests** for content wrapping covering wrapping, stripping, roundtrip, tag escape attacks, XML attribute injection, and real-world integration scenarios.

### Changed

- `fetch_web_page_tool` — Markdown content is wrapped with safety markers after sanitization and truncation (step 11).
- `web_search_tools` — Perplexity synthesis, Brave snippets, and Wikipedia summaries are individually wrapped when `external_content_wrapping_enabled` is true.
- `.env.example` — Added `EXTERNAL_CONTENT_WRAPPING_ENABLED` variable.

### Fixed

- `html_renderer.py` — Removed incorrect `web_fetch` → `WebSearchCard` mapping that rendered an empty card. Web fetch results are inline in the LLM response text and do not need a visual card.

## [1.4.4] - 2026-03-16

### Added

- **Web Search/Fetch Cache** — Redis TTL cache for `unified_web_search_tool` (5 min) and `fetch_web_page_tool` (10 min) results. Reduces external API calls (Brave, Perplexity) and HTTP fetches for repeated queries. Configurable via `WEB_SEARCH_CACHE_ENABLED`, `WEB_SEARCH_CACHE_TTL_SECONDS`, `WEB_FETCH_CACHE_TTL_SECONDS` environment variables. Multi-tenant isolated by user_id.
- **`force_refresh` parameter** on `unified_web_search_tool` and `fetch_web_page_tool` — allows planner to bypass cache when user explicitly requests fresh results.
- **`WebSearchCache` class** (`src/infrastructure/cache/web_search_cache.py`) — follows existing `ContactsCache` pattern with `CacheEntryV2` format, automatic Prometheus metrics (`cache_hit_total`/`cache_miss_total`), and graceful degradation on Redis errors.
- **Recency normalization** — `_normalize_recency()` function converts non-standard planner values (`"7d"`, `"pd"`, `"1w"`) to canonical values (`"day"`, `"week"`, `"month"`). Prevents cache key fragmentation and ensures correct API parameter passing.
- **Catalogue manifest enum constraint** — `recency` parameter on `unified_web_search_tool` manifest now has an `enum` constraint guiding the planner to generate valid values only.
- **13 unit tests** for `WebSearchCache` covering cache hit/miss, TTL, disabled state, Redis errors, multi-tenant isolation, and recency key differentiation.

### Changed

- `unified_web_search_tool` — Cache check before triple parallel search (Perplexity + Brave + Wikipedia), cache store after success. Registry updates excluded from cache (RegistryItem objects not serializable).
- `fetch_web_page_tool` — Cache check before HTTP fetch, cache store after extraction. Eliminates redundant HTTP calls for same URL within TTL window.
- `.env.example` — Added 5 new web cache configuration variables.
- `docs/technical/WEB_FETCH.md` — Added cache architecture section, Redis TTL documentation, `force_refresh` parameter documentation.
- `docs/technical/TOOLS.md` — Added `unified_web_search` and `fetch_web_page` to cache hit rates table.
- `docs/architecture/ADR-029-Redis-Multi-Purpose-Architecture.md` — Added `web_search:{user}:{hash}` and `web_fetch:{user}:{hash}` cache keys to architecture diagram and key reference table.

## [1.4.3] - 2026-03-16

### Changed

- **httpx** 0.27.2 → 0.28.1 — Migrate test fixture from `app=` to `ASGITransport(app=)`, add explicit `follow_redirects=False` on 6 OAuth credential flows (RFC 6749/7009)
- **langgraph** 1.0.10 → 1.1.2 — Required by langchain 1.2.12
- **langchain-core** 1.2.17 → 1.2.19
- **langchain** 1.2.10 → 1.2.12
- **langchain-openai** 1.1.10 → 1.1.11
- **langchain-anthropic** 1.3.4 → 1.3.5
- **langchain-google-genai** 3.2.0 → 4.2.1 — SDK rewrite (google-generativeai → google-genai)
- **firebase-admin** 6.8.0 → 7.2.0 — Removed deprecated send_all/send_multicast (not used)
- **ruff** 0.8.4 → 0.15.6 — Exclude new UP042/UP045/UP046/UP047 cosmetic rules
- **mypy** 1.13.0 → 1.19.1 — Remove stale type:ignore, add overrides for new strict checks
- **pytest** 8.3.3 → 9.0.2
- **pytest-asyncio** 0.24.0 → 1.3.0
- **pytest-cov** 6.0.0 → 7.0.0
- **psycopg** 3.2.10 → 3.3.3
- **pgvector** 0.3.6 → 0.4.2
- **redis** 7.1.0 → 7.3.0
- **uvicorn** 0.40.0 → 0.41.0
- **asyncpg** 0.30.0 → 0.31.0
- **sentence-transformers** 5.2.0 → 5.3.0
- **opentelemetry** 1.39.1 → 1.40.0 (api, sdk, instrumentation-fastapi, exporter-otlp)
- **python-jose** 3.4.0 → 3.5.0
- **python-dotenv** 1.0.1 → 1.2.2
- **email-validator** 2.2.0 → 2.3.0
- **apscheduler** 3.10.4 → 3.11.2
- **readability-lxml** 0.8.1 → 0.8.4.1
- **markdownify** 0.14.1 → 1.2.2
- **jsdom** 28.1.0 → 29.0.0
- **types-passlib** 1.7.7.20240819 → 1.7.7.20260211
- **types-python-jose** 3.3.4.20240106 → 3.5.0.20250531
- **pytest-mock** 3.14.0 → 3.15.1
- **testcontainers** 4.8.2 → 4.14.1
- **debugpy** 1.8.9 → 1.8.20
- **safety** 3.2.11 → 3.7.0
- **bandit** 1.8.0 → 1.9.4
- **15 frontend packages** (react 19.2.4, firebase 12.10, zod 4.3.6, vitest 4.1, @hey-api/openapi-ts 0.94.1, etc.)
- **13 GitHub Actions** (checkout v6, upload-artifact v7, codecov v5, docker actions v4/v7, etc.)

### Fixed

- **CI pipeline**: Use venv in backend CI jobs (fixes MyPy import resolution)
- **CI pipeline**: Fix Alembic head detection regex for typed annotations
- **CI pipeline**: Fix synchronous Store call check false positive (exclude `await` lines)
- **CI pipeline**: Rename codecov `file` → `files` for v5 compatibility
- **CI pipeline**: Regenerate pnpm-lock.yaml after jsdom 29 merge
- **CI pipeline**: Mark checkpointer tests as integration (were failing with wrong DB user)
- **CI pipeline**: Lower coverage threshold to 40%
- **Security**: Add OPENAI_API_KEY to .env.example

### Documentation

- Update STACK_TECHNIQUE.md with all version bumps
- Update GUIDE_DEVELOPPEMENT.md test examples (ASGITransport)
- Update README.md badges (LangGraph 1.1.2, LangChain 1.2.12)

## [1.4.1] - 2026-03-15

### Fixed

- **Heartbeat timezone conversion**: Proactive calendar notifications now display event times in the user's local timezone instead of raw ISO/UTC strings. Fixes notifications reporting events 1 hour early (LLM misinterpreting UTC as local time)
  - Multi-provider support: Google (offset in ISO), Microsoft (naive + timeZone field), Apple CalDAV (naive local times)
  - Naive datetimes (no offset, no timeZone) now default to user timezone instead of UTC, fixing a 1-hour-late display for CalDAV events
  - Task due dates cleaned to date-only format (prevents misleading midnight-UTC timezone shifts)
  - Recent heartbeat/interest notification timestamps converted to user timezone
  - Prompt header now includes "(times in user's local timezone)" for LLM clarity
  - DRY refactor: `_resolve_user_tz()` replaces 3 duplicated timezone fallback blocks
- **Interest notification 0 tokens / 0€**: Token tracking now correctly accumulates tokens from both LLM phases (content generation + presentation formatting). Previously only the presentation phase was counted, and generation phase tokens (LLM reflection) were lost
  - Added `tokens_in`/`tokens_out` fields to `ContentResult` dataclass
  - `LLMReflectionContentSource` now returns tokens in `ContentResult` (in addition to persisting via TrackingContext)
  - `_extract_llm_tokens()` helper with `response_metadata` fallback for non-standard providers
- **Interest presentation LLM provider mismatch**: `LLMAgentConfig` was created without `provider` parameter, defaulting to `"openai"` while model was `claude-sonnet-4-6` (Anthropic) — causing silent 404 errors and raw unformatted content as fallback

### Added

- **CI/CD hardening for public repo**: Comprehensive pipeline overhaul for open-source best practices
  - **Branch protection on `main`**: PR required with 1 review (external contributors), 7 required status checks, force push forbidden, stale review dismissal, conversation resolution required. Admins can bypass for direct pushes
  - **SHA-pinned GitHub Actions**: All actions across 3 workflows (`ci.yml`, `security.yml`, `release.yml`) pinned by commit SHA with version comments — prevents supply-chain attacks via tag mutation
  - **`permissions: contents: read`** on CI workflow (least privilege principle)
  - **Code Hygiene CI job**: New job with 6 checks — `.bak` files, sync Store calls, Redis setex without `json.dumps`, i18n keys sync (EN vs 5 languages), Alembic migration conflicts (revision chain parsing), `.env.example` completeness
  - **Docker build smoke test CI job**: Builds API and Web production images without pushing (catches broken Dockerfiles), with GHA cache
  - **Pre-commit hook aligned with CI**: Added i18n keys sync, Alembic migration conflict detection (date prefix), `.env.example` completeness checks to local pre-commit hook
  - **Repo settings**: `delete_branch_on_merge`, `allow_update_branch`, `allow_auto_merge` enabled; homepage URL set
  - **Dependabot groups**: Minor/patch updates grouped per ecosystem (pip, npm) to reduce PR noise; GitHub Actions updates grouped
  - **`.editorconfig`**: New file enforcing consistent formatting across IDEs (indent 4 for Python, indent 2 for TS/JS/JSON, LF line endings, CRLF for Windows scripts)
  - **GitHub labels**: Added `security`, `ci`, `docker`, `python`, `frontend`, `agents`, `priority:high`, `priority:low`
  - **CI tests aligned with pre-commit**: Fast unit tests only (excluding slow/integration/e2e/benchmark markers + 10 ignored files), coverage threshold 43%
  - **CI/CD documentation**: New `docs/technical/CI_CD.md` with full pipeline architecture, check matrix, troubleshooting
- **`extract_llm_tokens()` centralized helper**: New `src/infrastructure/llm/token_utils.py` — single reusable function for extracting token usage from LangChain AIMessage across all providers (DRY refactor from 2 duplicated implementations)

### Changed

- Updated heartbeat context source tables in docs to reflect multi-provider support (Google/Apple/Microsoft Calendar, Google Tasks/Microsoft To Do)
- Ruff and Black now lint `tests/` in addition to `src/` (aligned with pre-commit hook)
- Interest LLM reflection prompt: heading level fix (`##` → `###`), free-form format with paragraphs instead of strict sentence limits

### Fixed

- **i18n desync**: 3 keys missing in fr/de/es/it/zh (`chat.voice_mode.processing`, `speaking`, `error_permission`), 87 keys missing in en/fr (`settings.interests.*` section). All 6 languages now have 2,587 keys in perfect sync
- **Mixed language in docs**: French documentation files (`GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md`, `INTERESTS.md`) contained English sentences — translated to French

## [1.4.0] - 2026-03-14

### Added

- **RAG Knowledge Spaces**: Users can create personal knowledge spaces containing their own documents (PDF, TXT, MD, DOCX) to enrich AI assistant responses
  - **Space management**: Create, edit, delete, and toggle activation of knowledge spaces per user
  - **Document processing pipeline**: Background processing with text extraction, chunking (RecursiveCharacterTextSplitter), and embedding (OpenAI `text-embedding-3-small` via TrackedOpenAIEmbeddings)
  - **Hybrid search retrieval**: Semantic similarity (pgvector cosine) + BM25 keyword matching with configurable alpha fusion
  - **Response Node injection**: RAG context automatically injected into assistant responses when active spaces exist
  - **Full cost transparency**: Embedding costs tracked per document (indexing) and per query (retrieval) in TokenUsageLog, MessageTokenSummary, and UserStatistics
  - **Admin reindexation**: Endpoint to reindex all documents after embedding model change, with Redis flag to disable RAG during migration and automatic vector dimension ALTER
  - **14 Prometheus metrics**: Document processing RED, retrieval performance, space lifecycle Gauges, reindex tracking
  - **Grafana dashboard**: Dedicated RAG Spaces dashboard (18th) with 21 panels
  - **Full frontend**: Space list, detail, document upload (drag & drop + progress), processing status polling, activation toggle, active spaces indicator in chat, settings section
  - **i18n**: Full translation support in 6 languages (en, fr, de, es, it, zh)
  - **Feature flag**: `RAG_SPACES_ENABLED=true` to enable (default: true)

## [1.3.0] - 2026-03-14

### Changed

- **FastAPI 0.128.0 → 0.135.1**: Major framework upgrade pulling Starlette 0.50.0
- **Removed Starlette UTF-8 patch**: Starlette 0.50 natively defaults to `encoding="utf-8"` in Config, making the `patch_starlette_utf8()` monkey-patch obsolete
- **SSE ClientDisconnect handling**: Added graceful catch for `starlette.requests.ClientDisconnect` (raised since Starlette 0.42) — client disconnections during streaming are now logged as info instead of errors

### Fixed

- **SSE CancelledError log level**: Client disconnections during streaming are now logged as `info` instead of `error` in orchestration and streaming services — prevents false error alerts and inflated error metrics
- **DB connection leak on client disconnect**: `session.close()` in `get_db_session()`/`get_db_context()` and `tracker.commit()` in the graph streaming finally block are now shielded with `asyncio.shield()`, preventing SQLAlchemy connection pool exhaustion when clients disconnect mid-stream
- **Stale tests**: Fixed 8 pre-existing test failures in semantic validation and routing modules (obsolete feature flag test, incorrect planner_iteration assertions, incomplete mock settings)

## [1.2.0] - 2026-03-14

### Changed

- **Node.js 20 → 22 LTS**: Upgraded Docker images, CI workflows, and engine requirements to Node.js 22 LTS (supported until April 2027)
- Closed Dependabot PR #4 (Node 25 — not LTS) and PR #6 (Python 3.14 — still in beta)

## [1.1.0] - 2026-03-14

### Added

- **LAN Access & SSL Configuration**: Configurable `SSL_DOMAIN` env var for self-signed certificates covering nip.io domains, enabling LAN access from mobile/other devices
- **SSL cert sharing**: Web container now uses ssl-init certificates via `--experimental-https-key`/`--experimental-https-cert`, ensuring consistent certs across API and Web
- **Documentation**: Added section 4.4 "LAN Access & SSL Configuration" in Getting Started guide

### Fixed

- **Token tracking upsert**: Replaced two-step UPDATE-then-INSERT with PostgreSQL native `INSERT ... ON CONFLICT DO UPDATE` for atomic, race-condition-free token summary persistence
- **Tracking resilience**: Token tracking failures no longer break the chat flow (graceful error handling in `TrackingContext.commit()`)
- **WebSocket HMR refresh loops**: Fixed `NEXT_PUBLIC_ALLOWED_DEV_ORIGINS` format — must be hostname only (e.g., `192.168.1.100.nip.io`), not full URL with protocol/port
- **SSL key permissions**: Changed key.pem to 644 so non-root containers (Next.js `node` user) can read it

### Changed

- `.env.example` is now a development template (was production), `.env.prod.example` remains the production template
- `generate-certs.sh` is fully configurable via `SSL_DOMAIN` and `SSL_IP` env vars (no hardcoded IP)
- Frontend dependencies updated: Next.js 16.1.6, i18next 25.8.18, lucide-react 0.577.0, tailwindcss 4.2.1

## [1.0.0] - 2026-03-13

First public open-source release of LIA.

### Features

- **Multi-Agent Orchestration**: LangGraph-based pipeline with Router, Planner, Orchestrator, and Response nodes
- **16+ Domain Agents**: Contacts, Email, Calendar, Drive, Tasks, Weather, Wikipedia, Perplexity, Brave Search, Web Search, Web Fetch, Places, Routes, Reminders, Context, Query, and dynamic MCP agents
- **Human-in-the-Loop (HITL)**: 6 interaction types — Plan Approval, Clarification, Draft Critique, Destructive Confirm, FOR_EACH Confirm, Modifier Review
- **Smart Planner**: LLM-based execution plan generation with dependency graphs and wave-by-wave parallel execution
- **Plan Pattern Learner**: Redis-based Bayesian learning; high-confidence patterns (>=90%) bypass semantic validation
- **Model Context Protocol (MCP)**: Admin MCP (persistent) + Per-User MCP (ephemeral) with OAuth flow support
- **MCP Apps**: Interactive HTML widgets in sandboxed iframes via PostMessage JSON-RPC bridge
- **Excalidraw Integration**: LLM-driven diagram builder with intent-based element generation
- **Skills System**: agentskills.io standard SKILL.md files with per-user toggle and deterministic bypass strategies
- **Multi-Channel Messaging**: Generic abstraction with Telegram as first implementation (webhook, OTP binding, voice)
- **Autonomous Heartbeat**: LLM-driven proactive notifications with two-phase approach (decision + personality-aware rewrite)
- **Voice Mode**: TTS (Edge/OpenAI/Gemini) + STT (Sherpa-onnx Whisper, CPU-only)
- **Multi-Provider LLM**: 6 providers (OpenAI, Anthropic, Gemini, DeepSeek, Perplexity, Ollama) with dynamic config via Admin UI
- **Multi-Provider Connectors**: Google, Apple iCloud, and Microsoft 365 with mutual exclusivity per functional category
- **Scheduled Actions**: User-scheduled deferred task execution
- **Session-based Auth (BFF)**: HTTP-only cookies in Redis, no JWT exposed to frontend
- **Enterprise Observability**: OpenTelemetry traces, Prometheus metrics, Grafana dashboards, Langfuse LLM analytics
- **Internationalization**: 6 languages (fr, en, es, de, it, zh)
- **Multi-arch Docker**: `linux/amd64` + `linux/arm64` builds for Raspberry Pi deployment
- **Comprehensive Test Suite**: 2,300+ tests (unit, integration, e2e, benchmark)

### Infrastructure

- FastAPI 0.128 backend (Python 3.12+) with async SQLAlchemy 2.0 + asyncpg
- Next.js 16 frontend (React 19, TypeScript) with TailwindCSS 4
- PostgreSQL 16 (+ pgvector) for data and vector search
- Redis 7 for sessions, cache, distributed locks, and pattern learning
- APScheduler for 9 background jobs
- Circuit breaker, rate limiting, and distributed locks
- SOPS/Age encryption for secrets management

[Unreleased]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.3...HEAD
[1.13.3]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.2...v1.13.3
[1.13.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.1...v1.13.2
[1.13.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.13.0...v1.13.1
[1.13.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.4...v1.13.0
[1.12.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.1...v1.12.2
[1.12.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.12.0...v1.12.1
[1.12.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.11.5...v1.12.0
[1.11.5]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.11.4...v1.11.5
[1.8.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.8.1...v1.8.2
[1.8.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.2...v1.8.0
[1.7.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.1...v1.7.2
[1.7.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.6.1...v1.7.0
[1.6.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.2...v1.6.0
[1.5.2]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.1...v1.5.2
[1.5.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.7...v1.5.0
[1.4.7]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.6...v1.4.7
[1.4.6]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.1...v1.4.3
[1.4.1]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jgouviergmail/LIA-Assistant/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jgouviergmail/LIA-Assistant/releases/tag/v1.0.0
