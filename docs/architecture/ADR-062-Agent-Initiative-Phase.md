# ADR-062: Agent Initiative Phase + MCP Iterative Sub-Agent

## Status

Implemented — 2026-03-24 (Phase 1 + Phase 2)

## Context

LIA uses a static planner that pre-generates all execution steps and parameters
before execution. This works well for explicit user requests but has two
limitations:

1. **No post-execution reaction**: The assistant cannot react to execution
   results. Example: fetching emails reveals a meeting proposal for Thursday,
   but the assistant cannot proactively check the user's calendar availability.

2. **MCP multi-step interaction**: Some MCP servers require sequential tool
   calls (e.g., Excalidraw: `read_me` first, then `create_view` with correct
   format). The planner pre-generates all parameters at once, producing
   incoherent results for complex tools.

## Decision

### 1. ReactSubAgentRunner (Phase 1 — Implemented)

A generic, reusable runner for LangGraph ReAct agents, factorizing the pattern
shared by `browser_task_tool` and the new `mcp_server_task_tool`:

- Loads LLM by configurable type (admin LLM Config panel)
- Loads and formats versioned prompt
- Creates `create_react_agent` with tools and parent store
- Executes with nested config (isolated thread, propagated callbacks)
- Collects registry items via extensible `registry_collector` hook

### 2. MCP ReAct Sub-Agent (Phase 1 — Implemented)

When an MCP server is configured with `iterative_mode=true`:

- Individual tools stay in ToolRegistry (for the ReAct agent)
- The catalogue shows a single `mcp_server_task_tool` (for the planner)
- The ReAct agent follows native MCP workflow: call `read_me`, understand
  the API, then execute tools iteratively
- `_MCPReActWrapper` converts `UnifiedToolOutput` to string for the ReAct
  LLM while accumulating registry items (MCP App HTML) for propagation

### 3. Initiative Phase (Phase 2 — Implemented)

A new LangGraph node between task execution and response synthesis:

- Evaluates execution results via a prompt-driven LLM call
- Decides if read-only complementary actions would enrich the response
- Uses memory + interests for user-aware decisions
- Structural pre-filter: only triggers if adjacent read-only tools exist
- Can suggest write actions without executing them

## Architecture

```
Phase 1 (MCP ReAct):
  Planner → mcp_server_task_tool → ReactSubAgentRunner
    → ReAct agent: read_me → create_view → result
    → _MCPReActWrapper captures MCP App registry items
    → Propagated to response via UnifiedToolOutput.registry_updates

Phase 2 (Initiative):
  task_orchestrator → initiative_node → response
    ↑ loop (max 1-2 iterations)
```

## Files Changed (Phase 1)

### New
- `src/domains/agents/tools/react_runner.py` — ReactSubAgentRunner
- `src/domains/agents/tools/mcp_react_tools.py` — _MCPReActWrapper + mcp_server_task_tool
- `src/domains/agents/prompts/v1/mcp_react_agent_prompt.txt`
- `tests/unit/domains/agents/tools/test_react_runner.py`
- `tests/unit/domains/agents/tools/test_mcp_react_tools.py`

### Modified
- `src/core/constants.py` — ADR-062 constants
- `src/core/config/agents.py` — initiative_enabled, mcp_react_enabled settings
- `src/infrastructure/llm/factory.py` — LLMType: initiative, mcp_react_agent
- `src/domains/llm_config/constants.py` — Registry + Defaults
- `src/infrastructure/mcp/schemas.py` — MCPServerConfig.iterative_mode
- `src/infrastructure/mcp/registration.py` — Iterative mode registration
- `src/infrastructure/mcp/tool_adapter.py` — Removed _prepare_excalidraw
- `src/infrastructure/mcp/excalidraw/overrides.py` — Removed SPATIAL_SUFFIX
- `src/domains/agents/tools/browser_tools.py` — Refactored to ReactSubAgentRunner
- `src/domains/agents/tools/tool_registry.py` — _import_tool_modules for mcp_react
- `src/domains/agents/services/smart_planner_service.py` — Filter reference_content
- `src/domains/agents/prompts/prompt_loader.py` — PromptName additions
- `src/infrastructure/observability/metrics_agents.py` — MCP ReAct metrics

### Deleted
- `src/infrastructure/mcp/excalidraw/iterative_builder.py`

## Consequences

- MCP servers can opt into iterative mode for multi-step interactions
- Excalidraw diagrams are generated correctly (agent reads docs first)
- ReactSubAgentRunner is reusable for any future ReAct sub-agent
- Feature flags default to `false` — zero impact when disabled
- Browser task tool refactored with zero functional change
- No new database tables, migrations, or API endpoints

## Post-Implementation Fix (v1.11.1)

**Bug**: `initiative_iteration` was not reset between conversation turns. Since LangGraph state is checkpointed to PostgreSQL, after the first turn the counter persisted at `max_iterations`, causing the initiative node to be skipped on all subsequent turns. **Fix**: Added per-turn reset of `initiative_iteration`, `initiative_results`, `initiative_skipped_reason`, and `initiative_suggestion` in `router_node_v3`'s state clearing block (same pattern as `planner_iteration`).

## Amendment: Initiative Skip After HITL Resolution (v1.14.5)

When a HITL (Human-in-the-Loop) interaction has just been resolved, the initiative node now short-circuits immediately instead of making a full LLM evaluation call.

**Problem**: After a user approves or refuses a HITL interaction (e.g., confirming a destructive action, accepting a draft, or disambiguating an entity), the flow re-enters the initiative node. The LLM call to evaluate post-execution enrichment opportunities is wasted in this context — the user has already made an explicit decision and expects the response, not additional proactive actions. This added ~8 seconds of unnecessary latency per HITL resolution.

**Solution**: At step 1b of the initiative node (after the feature flag check, before the iteration budget check), a new guard checks for the presence of any HITL resolution state key:

- `draft_action_result` — user accepted/refused a draft
- `entity_disambiguation_result` — user selected a disambiguated entity
- `tool_confirmation_result` — user confirmed/refused a destructive tool call

If any of these keys is present in state, the node returns immediately with `initiative_skipped_reason: "hitl_just_resolved"`, bypassing the LLM evaluation entirely.

**Why this is reliable**: These state keys are set by `hitl_dispatch_node` when routing the user's HITL response back into the graph, and cleared by `response_node` after the final response is synthesized. Their presence in state at the initiative node therefore reliably indicates that the current graph traversal originates from a HITL resolution, not from a fresh user message or a task orchestrator completion.

### Amendment 2026-04-08: Initiative Eligibility & Cross-Domain Only

**Changes:**

1. **`initiative_eligible` field on ToolManifest** — New `bool | None` field replacing the `is_read_only_tool()` heuristic. Allows per-tool opt-out from initiative phase. Auto-determined from tool category when `None` (search/readonly = eligible, system = not eligible). ~30 manifests annotated with `initiative_eligible=False` (web search, browser, context, structural listing tools).

2. **`is_initiative_eligible()` function** — New function in `catalogue.py` that checks `manifest.initiative_eligible` first (explicit override), then falls back to category-based default. Replaces `is_read_only_tool()` for initiative tool selection.

3. **Cross-domain only filtering** — Initiative node now excludes already-executed domains from adjacent tool search (`target_domains -= executed_set`). The initiative's purpose is to check OTHER domains for implications — re-checking executed domains wastes tokens and produces low-value actions since data is already in `execution_summary`.

4. **Turn ID filtering** — `_format_execution_summary()` now filters `agent_results` by `current_turn_id` to prevent stale data from previous turns leaking into the initiative prompt.

5. **Compact tool format** — Initiative tool formatting uses one-line-per-tool with inline params (~70% token reduction vs full parameter format). Non-obvious parameters keep descriptions; obvious ones listed by name only.

**Files changed:** `initiative_node.py`, `catalogue.py`, all `catalogue_manifests.py` files.

### Amendment 2026-04-08: User MCP ReAct Iterative Mode

**Problem**: `iterative_mode` was only implemented for admin MCP servers (registered at startup via `registration.py`). User MCP servers had the `iterative_mode` field in the database and the UI toggle, but the flag was never read at execution time — tools were always registered individually.

**Solution**: Extended the iterative mode support to user MCP servers via `setup_user_mcp_tools()` in `user_context.py`:

1. **Detection**: `react_enabled and server.iterative_mode` checked per server during per-request setup.
2. **Registration**: Individual tools stored in `ctx.tool_instances` (for ReAct agent), single `mcp_user_{id_prefix}_task` task tool + manifest exposed to planner.
3. **Execution**: New `mcp_user_server_task_tool()` delegates to shared `_run_mcp_react_task()`.
4. **Reference content**: Skipped in planner prompt for user MCP iterative servers (tracked via `ctx.iterative_servers`).

**Refactoring**: Extracted shared `build_mcp_react_task_manifest()` factory and `_run_mcp_react_task()` helper to eliminate duplication between admin and user paths. Centralized `MCP_DISPLAY_EMOJI` and `MCP_ITERATIVE_TASK_SUFFIX` constants.

**Bug fix**: `_server_to_response()` in user MCP router was missing `iterative_mode` in the response, always returning `False`.

**Error recovery**: `_MCPReActWrapper._arun()` now catches all exceptions (including `ExceptionGroup` from anyio/MCP SDK) and returns error strings to the ReAct agent. Previously, MCP tool errors crashed the entire ReAct loop. The agent can now reason about errors and retry with corrected parameters.

**MCP App dedicated LLM**: New LLM type `mcp_app_react_agent` (renamed from dead code `mcp_excalidraw`) auto-selected for MCP servers with interactive widgets (`app_resource_uri`). Detection via `_has_mcp_app_tools()`. Defaults to Opus for complex workflows; regular MCP servers use `mcp_react_agent`. Removed ~80 lines of dead `mcp_excalidraw_llm_*` settings and 8 unused constants.

**Files changed:** `mcp_react_tools.py`, `user_context.py`, `context.py`, `registration.py`, `smart_planner_service.py`, `constants.py`, `router.py`, `config/mcp.py`, `llm_config/constants.py`, `llm/factory.py`.
