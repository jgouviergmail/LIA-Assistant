# ReAct Execution Mode

| Version | Date | ADR |
|---------|------|-----|
| 1.0 | 2026-04-09 | [ADR-070](../architecture/ADR-070-ReAct-Execution-Mode.md) |

## Table of Contents

1. [Overview](#overview)
2. [Pipeline vs ReAct](#pipeline-vs-react)
3. [Architecture](#architecture)
4. [Graph Wiring](#graph-wiring)
5. [Nodes](#nodes)
6. [Tool System](#tool-system)
7. [HITL in ReAct](#hitl-in-react)
8. [Response Synthesis](#response-synthesis)
9. [Initiative enrichment on the nominal path](#initiative-enrichment-on-the-nominal-path-adr-070--adr-062)
10. [Turn isolation & data-precision guidance](#turn-isolation--data-precision-guidance-2026-07)
11. [Token Tracking](#token-tracking)
12. [Skills Integration](#skills-integration)
13. [Configuration](#configuration)
14. [Streaming Step Visibility](#streaming-step-visibility-v1162)
15. [Key Files](#key-files)

---

## Overview

ReAct (Reasoning + Acting, Yao et al. 2022) is an alternative execution mode to the pipeline. Instead of planning all steps upfront then executing them, the LLM iteratively reasons about each tool result and decides the next action autonomously.

The user toggles between modes via a frontend toggle (Zap icon). The preference is persisted in the `users.execution_mode` column (`"pipeline"` or `"react"`).

## Pipeline vs ReAct

| Aspect | Pipeline | ReAct |
|--------|----------|-------|
| **Flow** | Router → Planner → Orchestrator → Agents → Response | Router → ReAct Loop → Response |
| **Planning** | Upfront (ExecutionPlan DSL) | None — LLM decides step by step |
| **Adaptability** | Rigid — follows plan | Adaptive — pivots on tool results |
| **Tool selection** | Planner selects by domain | LLM chooses from all available tools |
| **Token cost** | Lower (1 planner + 1 response LLM call) | Higher (1 LLM call per iteration) |
| **Best for** | Well-structured requests, multi-domain | Exploratory, research, ambiguous queries |
| **HITL** | Plan-level approval + draft confirmation | Tool-level interrupt + draft confirmation (shared flow) |
| **Initiative** | Dedicated `initiative_node` (post-execution LLM evaluation) | Same `initiative_node` on the nominal path when `INITIATIVE_REACT_ENABLED` (ADR-070 amendment 2026-05-21), in addition to the in-loop CROSS-CHECK step |

## Architecture

Custom ReAct loop as **4 nodes in the parent LangGraph graph** (not a `create_react_agent` subgraph — avoided due to LangGraph bugs with dynamic tool interrupts, GitHub #5863/#4796):

```
                          ┌──────────────────────────┐
                          │       Router Node        │
                          └──────────┬───────────────┘
                 execution_mode?     │
              ┌──────────────────────┼──────────────────────┐
              │ "pipeline"           │ "react"               │
              ▼                      ▼                       │
       ┌──────────┐          ┌──────────────┐               │
       │ Planner  │          │ react_setup  │               │
       └────┬─────┘          └──────┬───────┘               │
            │                       │                       │
            ▼                       ▼                       │
     ┌──────────────┐       ┌───────────────┐              │
     │ Orchestrator │       │react_call_model│◄────┐       │
     └──────┬───────┘       └───────┬───────┘     │       │
            │                       │              │       │
            ▼                tool_calls?           │       │
     ┌──────────┐          yes │        no │       │       │
     │ Agents   │              ▼           ▼       │       │
     └────┬─────┘   ┌─────────────────┐ ┌────────┐│       │
          │         │react_exec_tools │ │finalize││       │
          ▼         └────────┬────────┘ └───┬────┘│       │
     ┌──────────┐            │              │      │       │
     │Initiative│            └──────────────┘      │       │
     └────┬─────┘                                  │       │
          │                                        │       │
          ▼                                        ▼       │
       ┌─────────────────────────────────────────────┐     │
       │              Response Node                   │     │
       └─────────────────────────────────────────────┘     │
```

Each node benefits from the parent graph's PostgreSQL checkpointer, so `interrupt()` works natively in `react_execute_tools` (and in the shared `hitl_dispatch` node reached for draft confirmation) — see [HITL in ReAct](#hitl-in-react).

## Graph Wiring

```python
# graph.py — ReAct edges
graph.add_edge(NODE_REACT_SETUP, NODE_REACT_CALL_MODEL)
graph.add_conditional_edges(
    NODE_REACT_CALL_MODEL,
    route_from_react_call_model,  # → execute_tools or finalize
    {
        NODE_REACT_EXECUTE_TOOLS: NODE_REACT_EXECUTE_TOOLS,
        NODE_REACT_FINALIZE: NODE_REACT_FINALIZE,
    },
)
graph.add_edge(NODE_REACT_EXECUTE_TOOLS, NODE_REACT_CALL_MODEL)  # Loop
graph.add_edge(NODE_REACT_FINALIZE, NODE_RESPONSE)
```

Routing from router: when `execution_mode == "react"` and the router classifies the query as actionable, it routes to `NODE_REACT_SETUP` instead of `NODE_PLANNER`.

## Nodes

### react_setup

Prepares tools, system prompt, and context for the ReAct loop:
- Selects ALL available tools via `ReactToolSelector` (filtered by active connectors)
- Builds system prompt from `react_agent_prompt.txt`
- Injects memory context (resolved references + memory facts)
- Injects active skills catalogue (L1, filtered by `active_skills_ctx`)
- Sets `react_start_time` for timeout enforcement
- Stores tool names and HITL map in state (JSON-serializable)

### react_call_model

Calls the ReAct LLM with bound tools:
- Recreates LLM and tool bindings each iteration (~1-2ms)
- Applies message windowing (preserves current turn, windows history)
- Returns AIMessage with or without `tool_calls`

### react_execute_tools

Executes tools from the last AIMessage:
- HITL: tools flagged `hitl_required` trigger `interrupt()` for pre-execution approval; draft-preparing mutation tools (`requires_confirmation`) instead hand off to the shared draft-confirmation flow (see [HITL in ReAct](#hitl-in-react))
- Idempotence: on re-execution after interrupt resume, already-resolved tool calls are skipped
- ToolRuntime injection via `_build_tool_runtime()` (same pattern as pipeline)
- Registry items accumulated across iterations via `current_turn_registry` merge

### react_finalize

Collects iteration count and prepares metadata for the response node:
- Records Prometheus metrics (iterations, duration, executions)
- Sets `react_agent_result` for the response node passthrough

## Tool System

The ReAct agent receives ALL available tools (not domain-filtered like the planner):
- Filtered by active connectors (`get_request_tool_manifests()`)
- Capped by `REACT_AGENT_MAX_TOOLS` (default: 100) — measured on the **resolved** tool count, after iterative expansion
- Wrapped in `ReactToolWrapper` for string conversion + registry collection
- HITL map built from the in-hand tool manifests (`permissions.hitl_required`)

Tools are NOT stored in state (non-serializable). Tool names and HITL map are stored instead, and tools are rebuilt in each node that needs them.

### Tool resolution (shared with the pipeline)

Both `ReactToolSelector` (binding) and `_rebuild_wrapped_tools` (execution) resolve a tool *name* to its instance through the shared `src/domains/agents/tools/tool_resolution.py` — the single source of truth used by the pipeline executor too. Resolution order: global `tool_registry` (native + admin MCP) → hallucinated-suffix strip → per-request `user_mcp_tools_ctx` (exact then fuzzy). Without this fallback the ReAct loop, which consulted only the global registry, silently dropped **user** MCP tools (whose instances live only in the ContextVar) — see ADR-070 amendment 2026-06-02.

### Iterative user MCP expansion

A user MCP server configured `iterative_mode=true` exposes a single opaque `mcp_user_{id}_task` manifest to the planner (it delegates to a ReAct sub-agent — ADR-062). Since the ReAct loop is *itself* iterative, that indirection only hides the descriptive individual tools, so the LLM falls back to generic web search. `ReactToolSelector._expand_iterative_user_mcp` therefore replaces the task manifest with the server's individual tools (read from the ContextVar), letting the model pick them by description. **Exception:** MCP App servers (a tool with `app_resource_uri`) keep the task tool, because they need the dedicated MCP-app prompt and the more capable `mcp_app_react_agent` model. Gated by `REACT_MCP_EXPAND_ITERATIVE_ENABLED` (default `true`); when `false`, the task tool is kept (instant rollback) and still resolves correctly via the shared resolver. The pipeline keeps the task-tool path unchanged.

> Optional MCP parameters left unset are materialised as `None` by the args schema; both MCP adapters drop `None`-valued arguments (`drop_none_values`) before the server call, so strictly-typed (e.g. Go-based) servers don't reject them as `null`.

## HITL in ReAct

ReAct has two HITL paths, both reusing existing infrastructure (no ReAct-specific HITL machinery):

1. **Pre-execution confirmation** — tools flagged `hitl_required` in their manifest (genuinely **non-draft** mutations only: `delegate_to_sub_agent_tool` and user MCP mutation tools) raise a **shared `tool_confirmation` interrupt** from `react_execute_tools` ([ADR-106](../architecture/ADR-106-HITL-Contract-Coherence.md)): the same `action_requests`-typed payload the pipeline uses, rendered by `ToolConfirmationInteraction` and persisted in Redis, then resumed through `_parse_approval_decision` → `{"action": "confirm"|"cancel"}`. The gate executes **only on an explicit confirm** (safe default: any non-approval declines). On resume, LangGraph replays the node; the idempotence pattern skips tool calls that already have a `ToolMessage` in state (matched by `tool_call_id`). *(The legacy bare `react_tool_approval` value carried no `action_requests`, so it never rendered — a silent hang, fixed by ADR-106. Draft-based delete/cancel tools are `hitl_required=False` and go through path 2 below; the `hitl_required` set is locked by `test_hitl_required_consistency.py`.)*

2. **Draft confirmation** — draft-preparing mutation tools (`create_event_tool`, `send_email_tool`, `update_*`, `delete_*`, …) return `requires_confirmation=True` and prepare a **draft** instead of executing. `react_execute_tools` extracts the draft and sets `pending_draft_critique`; `route_from_react_execute_tools` then routes to `hitl_dispatch` (the shared `draft_critique` node) → `initiative` → `response_node` — exactly the path pipeline mode uses. The user confirms/edits/cancels, then `response_node` executes the confirmed draft via `execute_draft_if_confirmed` and synthesizes the real result. Because confirmation happens in a node **downstream** of `react_execute_tools`, resume re-enters `hitl_dispatch` only — the draft tool is never re-run (no duplicate drafts). Completion metrics are still emitted on this short-circuited path (`react_agent_executions_total{status="draft"}`).

> Tools that execute directly without a draft (e.g. `create_reminder_tool`) are not draft-gated and behave identically in both modes.

## Response Synthesis

The ReAct loop never streams its own tokens to the user. `react_finalize` stores the loop's final answer in `react_agent_result.final_message`, and `response_node` delivers it — preserving all post-processing (personality, display mode, voice, registry cards, memory/journal extraction). Three invariants keep that hand-off clean:

1. **Authoritative answer** — `response_node` injects the final answer as `agent_results[…]["data"]["react_synthesis"]`. `_format_status_messages()` (in `formatters/agent_results.py`) surfaces it verbatim as the authoritative current-turn data the response LLM reformulates. Writer and reader use the same `FIELD_REACT_SYNTHESIS` constant, so the contract cannot drift (a missing/renamed key previously dropped the answer into a `"Statut inconnu"` status message, forcing the response LLM to reconstruct one).

2. **No reasoning leak** — `react_setup` injects the `react_agent_prompt` (with its PLAN/ACT/OBSERVE/CROSS-CHECK `<Workflow>` and tool-calling role) as `SystemMessage`s that accumulate in `state["messages"]`. `filter_for_llm_context()` (in `utils/message_filters.py`) **excludes every internal-scaffolding `SystemMessage`** from the response LLM's conversational context, allowlisting only the compaction summary (matched via `COMPACTION_SUMMARY_MARKER`, the message that carries compacted history). Without this, the response LLM mimics the agent's reasoning structure (`PLAN … OBSERVATION … CROSS-CHECK …`) or impersonates its role instead of answering.

3. **Single, de-duplicated stream** — LangGraph `stream_mode="messages"` emits **both** the response LLM's token deltas (`AIMessageChunk`) and the complete post-processed `AIMessage` the node returns to the `messages` channel. `StreamingService._process_messages_chunk()` streams the deltas only and skips the complete message once deltas have been seen (with a non-streaming fallback that emits it when no delta occurred), so the reply is never shown twice. The canonical post-processed content (HTML cards, psyche-tag cleanup) is still delivered by the `content_replacement` chunk after the stream loop.

## Initiative enrichment on the nominal path (ADR-070 / ADR-062)

When `INITIATIVE_ENABLED` **and** `INITIATIVE_REACT_ENABLED` are set, the nominal ReAct path routes `react_finalize → initiative → response` instead of `react_finalize → response`. The conditional edge `route_from_react_finalize` (in `nodes/routing.py`) gates this; the **draft** path (`react_execute_tools → draft_critique → initiative`) is wired independently and is never gated by the flag, so default-off (the default) is byte-identical to the pre-amendment behaviour.

The existing pipeline `initiative_node` is reused almost as-is — its pre-filter reads `query_intelligence.domains`, its execution summary reads `current_turn_registry`, and the per-request tool manifests are all already populated in ReAct. Two ReAct-specific adaptations live outside the node:

- `route_from_initiative` short-circuits to `response` in ReAct (`execution_mode == "react"`): there is no orchestrator loop to re-evaluate against, so exactly one enrichment pass runs.
- `response_node` **merges** the ReAct answer (`{turn}:react_agent`) with any Initiative entry (`{turn}:initiative`) via `_merge_react_synthesis_result` (idempotent on the react key) instead of the previous `if not agent_results` gate, which would otherwise have dropped the answer once Initiative wrote its results first. A ReAct-only `<ProactiveFindings>` prompt directive invites the response LLM to weave the proactive findings (already present via `data_for_filtering`) into the reply; the suggestion uses the existing `<InitiativeSuggestion>` injection.

One node-level fix made this work in ReAct: `_format_execution_summary` now normalizes registry items in both `dict` form (pipeline, after a checkpoint round-trip) and live Pydantic `RegistryItem` form (ReAct, built in-memory by `react_execute_tools`). It previously skipped the latter, so the summary collapsed to `"No execution results."` and the Initiative LLM declined to act.

## Turn isolation & data-precision guidance (2026-07)

Two field bugs fixed on the ReAct path (see [ADR-090](../architecture/ADR-090-Semantic-Layer-Governance.md) §4 for the second):

1. **Cross-turn `current_turn_registry` leak** — nothing purged the per-turn registry at the start of a ReAct turn, so the value restored from the previous turn's checkpoint seeded `react_execute_tools`' intra-turn accumulation, and the response node re-displayed last turn's data (e.g. the previous "4 upcoming events" answer inside a route reply — through BOTH the synthesis text and the SSE data cards). Fixes:
   - `react_setup_node` returns `current_turn_registry: {}` — per-turn purge, mirroring the pipeline where `task_orchestrator` overwrites it ("no merge for display", 2025-12-31 bugfix that had never been ported to ReAct). HITL draft resumes re-enter AFTER setup, so mid-turn items are never dropped; the cross-turn `registry` (merge reducer) is untouched for context resolution.
   - The response node's ReAct passthrough no longer falls back to the cross-turn `registry` when `current_turn_registry` is empty — that fallback tagged EVERY historical item as a registry_update of the current turn, bypassing `_filter_registry_by_current_turn`. A tool-less ReAct turn now legitimately yields no data cards (REFERENCE turns keep their dedicated `resolved_context` path).

2. **Approximate values instead of exact lookups** — the ReAct system prompt now carries a generic PRECISION rule ("memory context tells you WHO, tools give exact values — retrieve the exact value with the lookup tool BEFORE calling the consumer tool") and a `<CrossDomainDataTypes>` section fed by `generate_semantic_dependencies_for_prompt()` (the same ontology ∪ manifests links the pipeline planner receives), so e.g. a route destination is fetched from the contact's exact address rather than a city name recalled from memory.

## Token Tracking

Token tracking works for all providers through the `TokenTrackingCallback`:
- The `node_breakdown` in tracking summary aggregates tokens by node name (sum across iterations)
- For OpenAI models using the Responses API with tools, the call is redirected to Chat Completions which provides `usage_metadata` on the response

Safety limits:
- **Max iterations**: `REACT_AGENT_MAX_ITERATIONS` (default: 15)
- **Hard timeout**: `REACT_AGENT_TIMEOUT_SECONDS` (default: 120s), checked in routing function

## Skills Integration

Skills are available to the ReAct agent through the same mechanism as the pipeline:
- The filtered L1 skills catalogue is injected as a `SystemMessage` in `react_setup`
- The 3 existing skill tools (`activate_skill_tool`, `run_skill_script`, `read_skill_resource`) are in the tool catalogue and available to the ReAct agent
- Active skill filtering uses `active_skills_ctx` (same per-request context as pipeline)

## Configuration

```env
# .env
REACT_AGENT_ENABLED=true              # Feature flag
REACT_AGENT_MAX_ITERATIONS=15         # Max ReAct loop iterations
REACT_AGENT_TIMEOUT_SECONDS=120       # Hard timeout for entire execution
REACT_AGENT_MAX_TOOLS=100             # Max tools bound to LLM (resolved count, post-expansion)
REACT_AGENT_HISTORY_WINDOW_TURNS=5    # Conversation history window
REACT_MCP_EXPAND_ITERATIVE_ENABLED=true  # Expand iterative USER MCP servers into individual tools (false = keep task tool; MCP App servers always keep it)
INITIATIVE_REACT_ENABLED=false        # Run the Initiative phase on the ReAct nominal path (ADR-070; pipeline uses INITIATIVE_ENABLED)
```

LLM type: `react_agent` — configurable in admin LLM config panel.
Default: `qwen3.5-plus`, temperature 0.0, reasoning_effort medium, max_tokens 16000.

## Streaming Step Visibility (v1.16.2)

During ReAct execution, the frontend displays accumulated execution steps in real time:

1. **Node-level steps**: Each ReAct node transition (`react_setup` → `react_call_model` → `react_execute_tools` → `react_finalize`) emits an `execution_step` SSE event via the "updates" stream mode.

2. **Per-tool steps**: When `react_call_model` produces an AIMessage with `tool_calls`, the streaming service inspects the state delta and emits individual `execution_step` events for each tool (e.g., "Retrieving contacts...", "Retrieving events..."), using the tool catalogue's `DisplayMetadata` for emoji and i18n_key.

3. **Reasoning detail**: The AIMessage content (reasoning text) from `react_call_model` is extracted, cleaned of markdown formatting, truncated to 120 characters, and included as a `detail` field in the node-level execution_step event.

4. **Frontend accumulation**: Steps are accumulated in a multi-line progress message (not replaced). All steps remain visible until the first response token arrives. Deduplication by `i18n_key` prevents duplicates.

## Key Files

| File | Purpose |
|------|---------|
| `src/domains/agents/nodes/react_nodes.py` | 4 node functions |
| `src/domains/agents/tools/react_tool_wrapper.py` | Tool wrapper (string output + registry) |
| `src/domains/agents/services/react_tool_selector.py` | Tool selection (all available, capped) |
| `src/domains/agents/prompts/v1/react_agent_prompt.txt` | System prompt |
| `src/domains/agents/nodes/routing.py` | `route_from_react_call_model()` |
| `src/domains/agents/graph.py` | Graph wiring (edges + conditional) |
| `src/domains/agents/models.py` | State fields (react_*, schema 1.2) |
| `src/domains/agents/utils/execution_metadata.py` | Debug panel display metadata |
| `docs/architecture/ADR-070-ReAct-Execution-Mode.md` | Architecture decision record |
