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
